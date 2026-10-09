import json
import unittest
from urllib.parse import parse_qs, urlsplit

from free_verticals import (
    MAX_CONTENT_CHARS,
    MAX_RESULTS,
    MISSING_CONFIG,
    REDIRECT_BLOCKED,
    URL_BLOCKED,
    image_search,
    news_search,
    scholar_search,
)


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FreeVerticalTests(unittest.TestCase):
    def test_scholar_uses_crossref_public_works_api_and_normalizes_results(self):
        payload = {'message': {'items': [{
            'DOI': '10.1000/demo',
            'title': ['A useful paper'],
            'author': [{'given': 'Ada', 'family': 'Lovelace'}],
            'published-print': {'date-parts': [[2024, 2, 3]]},
            'container-title': ['Journal of Examples'],
            'URL': 'https://doi.org/10.1000/demo',
            'abstract': '<p>Copyrighted publisher abstract must not be requested.</p>',
        }]}}
        transport = FakeTransport({'body': json.dumps(payload)})

        result = scholar_search(' machine learning ', transport=transport)

        self.assertEqual(result, {
            'ok': True,
            'results': [{
                'title': 'A useful paper',
                'url': 'https://doi.org/10.1000/demo',
                'doi': '10.1000/demo',
                'authors': ['Ada Lovelace'],
                'year': 2024,
                'venue': 'Journal of Examples',
            }],
            'truncated': False,
        })
        request = urlsplit(transport.calls[0])
        self.assertEqual((request.scheme, request.netloc, request.path),
                         ('https', 'api.crossref.org', '/works'))
        params = parse_qs(request.query)
        self.assertEqual(params['query'], ['machine learning'])
        self.assertEqual(params['rows'], [str(MAX_RESULTS)])
        self.assertNotIn('abstract', params['select'][0])
        self.assertNotIn('abstract', result['results'][0])

    def test_news_uses_gdelt_doc_api_and_filters_unsafe_article_urls(self):
        payload = {'articles': [
            {'title': 'Headline', 'url': 'https://news.example.org/story',
             'seendate': '20261009T120000Z', 'domain': 'news.example.org',
             'language': 'English', 'sourcecountry': 'United States'},
            {'title': 'Insecure', 'url': 'http://news.example.org/story'},
            {'title': 'Private', 'url': 'https://127.0.0.1/private'},
        ]}
        transport = FakeTransport({'status': 200, 'body': json.dumps(payload)})

        result = news_search(' climate change ', transport=transport)

        self.assertEqual(result, {
            'ok': True,
            'results': [{
                'title': 'Headline',
                'url': 'https://news.example.org/story',
                'snippet': '',
                'published': '20261009T120000Z',
                'source': 'news.example.org',
                'language': 'English',
                'country': 'United States',
            }],
            'truncated': False,
        })
        request = urlsplit(transport.calls[0])
        self.assertEqual((request.scheme, request.netloc, request.path),
                         ('https', 'api.gdeltproject.org', '/api/v2/doc/doc'))
        self.assertEqual(parse_qs(request.query), {
            'query': ['climate change'],
            'mode': ['artlist'],
            'format': ['json'],
            'maxrecords': [str(MAX_RESULTS)],
            'sort': ['hybridrel'],
        })

    def test_images_uses_commons_search_and_returns_per_file_license_metadata(self):
        payload = {'query': {'pages': [{
            'title': 'File:Example.jpg',
            'imageinfo': [{
                'url': 'https://upload.wikimedia.org/wikipedia/commons/e/example.jpg',
                'thumburl': 'https://upload.wikimedia.org/wikipedia/commons/thumb/e/example.jpg/800px-example.jpg',
                'descriptionurl': 'https://commons.wikimedia.org/wiki/File:Example.jpg',
                'extmetadata': {
                    'ImageDescription': {'value': '<p>A scenic view</p>'},
                    'Artist': {'value': '<a href=https://commons.wikimedia.org/wiki/User:Artist>A. Artist</a>'},
                    'LicenseShortName': {'value': 'CC BY-SA 4.0'},
                    'LicenseUrl': {'value': 'https://creativecommons.org/licenses/by-sa/4.0/'},
                },
            }],
        }]}}
        transport = FakeTransport({'body': json.dumps(payload)})

        result = image_search(' scenic view ', transport=transport)

        self.assertEqual(result, {
            'ok': True,
            'results': [{
                'title': 'File:Example.jpg',
                'url': 'https://upload.wikimedia.org/wikipedia/commons/thumb/e/example.jpg/800px-example.jpg',
                'page_url': 'https://commons.wikimedia.org/wiki/File:Example.jpg',
                'description': 'A scenic view',
                'creator': 'A. Artist',
                'license': 'CC BY-SA 4.0',
                'license_url': 'https://creativecommons.org/licenses/by-sa/4.0/',
            }],
            'truncated': False,
        })
        request = urlsplit(transport.calls[0])
        self.assertEqual((request.scheme, request.netloc, request.path),
                         ('https', 'commons.wikimedia.org', '/w/api.php'))
        params = parse_qs(request.query)
        self.assertEqual(params['action'], ['query'])
        self.assertEqual(params['generator'], ['search'])
        self.assertEqual(params['gsrnamespace'], ['6'])
        self.assertEqual(params['gsrsearch'], ['scenic view'])
        self.assertIn('LicenseShortName', params['iiextmetadatafilter'][0])

    def test_images_skips_records_without_license_or_safe_media_url(self):
        payload = {'query': {'pages': [
            {'title': 'File:NoLicense.jpg', 'imageinfo': [{
                'url': 'https://upload.wikimedia.org/no-license.jpg',
                'descriptionurl': 'https://commons.wikimedia.org/wiki/File:NoLicense.jpg',
                'extmetadata': {},
            }]},
            {'title': 'File:Private.jpg', 'imageinfo': [{
                'url': 'https://127.0.0.1/private.jpg',
                'descriptionurl': 'https://commons.wikimedia.org/wiki/File:Private.jpg',
                'extmetadata': {'LicenseShortName': {'value': 'CC0'}},
            }]},
        ]}}
        result = image_search('example', transport=FakeTransport(json.dumps(payload)))
        self.assertEqual(result['results'], [])

    def test_all_verticals_reject_invalid_queries_and_strictly_bound_results(self):
        for search in (scholar_search, news_search, image_search):
            with self.subTest(search=search.__name__):
                transport = FakeTransport({'body': '{}'})
                self.assertEqual(search('  ', transport=transport),
                                 {'error': {'code': URL_BLOCKED}})
                self.assertEqual(search('topic', transport=transport, limit=MAX_RESULTS + 1),
                                 {'error': {'code': URL_BLOCKED}})
                self.assertEqual(search('topic', transport=transport, limit=True),
                                 {'error': {'code': URL_BLOCKED}})
                self.assertEqual(transport.calls, [])

    def test_all_verticals_map_config_provider_transport_and_redirect_errors(self):
        for search in (scholar_search, news_search, image_search):
            with self.subTest(search=search.__name__):
                untouched = FakeTransport({'body': '{}'})
                self.assertEqual(search('topic', transport=untouched, provider_config=None),
                                 {'error': {'code': MISSING_CONFIG}})
                self.assertEqual(untouched.calls, [])
                self.assertEqual(search('topic', transport=object()),
                                 {'error': {'code': URL_BLOCKED}})
                self.assertEqual(search('topic', transport=FakeTransport(RuntimeError('private'))),
                                 {'error': {'code': URL_BLOCKED}})
                self.assertEqual(search('topic', transport=FakeTransport({
                    'body': '{}', 'url': 'http://127.0.0.1/private',
                })), {'error': {'code': REDIRECT_BLOCKED}})

    def test_all_verticals_reject_malformed_json_and_oversized_responses(self):
        for search in (scholar_search, news_search, image_search):
            with self.subTest(search=search.__name__):
                malformed = search('topic', transport=FakeTransport('not json'))
                oversized = search('topic', transport=FakeTransport('x' * (MAX_CONTENT_CHARS * 200)))
                self.assertEqual(malformed, {'error': {'code': URL_BLOCKED}})
                self.assertEqual(oversized, {'error': {'code': URL_BLOCKED}})

    def test_results_are_capped_at_goat_maximum_and_text_bound(self):
        payload = {'message': {'items': [
            {'DOI': f'10.1000/{index}', 'title': ['t' * (MAX_CONTENT_CHARS + 5)],
             'URL': f'https://doi.org/10.1000/{index}'}
            for index in range(MAX_RESULTS + 2)
        ]}}
        result = scholar_search('topic', transport=FakeTransport({'body': json.dumps(payload)}))
        self.assertEqual(len(result['results']), MAX_RESULTS)
        self.assertEqual(len(result['results'][0]['title']), MAX_CONTENT_CHARS)
        self.assertTrue(result['truncated'])


if __name__ == '__main__':
    unittest.main()
