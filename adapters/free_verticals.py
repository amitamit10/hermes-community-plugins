# Keyless official APIs selected for these free verticals:
# Scholar: Crossref REST GET https://api.crossref.org/works (public; no signup/key).
#   Bibliographic metadata is facts/public-domain; Crossref-generated data is CC0.
#   Abstracts may remain publisher/author-copyrighted, so this client does not fetch them.
#   Docs: https://www.crossref.org/documentation/retrieve-metadata/
# News: GDELT DOC 2.0 GET https://api.gdeltproject.org/api/v2/doc/doc (no key).
#   Datasets are free/unrestricted with citation + link to GDELT; linked article content
#   remains with publishers, so this client returns article metadata and links only.
#   Docs: https://gdeltproject.org/about.html and https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
# Images: Wikimedia Commons MediaWiki Action API GET https://commons.wikimedia.org/w/api.php
#   Structured file-namespace metadata is CC0; each image has its own license and reuse
#   conditions. Return the per-file license/credit fields and description-page URL; verify
#   each file page before reuse. Docs: https://commons.wikimedia.org/wiki/Commons:API/MediaWiki
#   and https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia

from collections.abc import Mapping
from html.parser import HTMLParser
import json
from urllib.parse import quote, urlencode

from ssrf_guard import (
    BAD_PORT,
    BAD_SCHEME,
    CREDENTIALS_IN_URL,
    MAX_RESPONSE_BYTES,
    PRIVATE_HOST,
    REDIRECT_BLOCKED,
    URL_BLOCKED,
    check_url,
    pinned_fetch,
)


MISSING_CONFIG = 'MISSING_CONFIG'
PUBLIC_ERROR_CODES = frozenset((URL_BLOCKED, REDIRECT_BLOCKED, MISSING_CONFIG))
MAX_RESULTS = 5
MAX_CONTENT_CHARS = 8000
_UNSET = object()
_CROSSREF_ENDPOINT = 'https://api.crossref.org/works'
_GDELT_ENDPOINT = 'https://api.gdeltproject.org/api/v2/doc/doc'
_COMMONS_ENDPOINT = 'https://commons.wikimedia.org/w/api.php'
_INTERNAL_URL_ERRORS = frozenset((BAD_SCHEME, CREDENTIALS_IN_URL, BAD_PORT, PRIVATE_HOST, URL_BLOCKED))


class _ClientError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def map_error(error):
    # Reduce internal/provider failures to Goat's public error codes only.
    if isinstance(error, Mapping):
        code = error.get('code', error.get('error'))
    else:
        code = getattr(error, 'code', error)
    if code is None:
        return MISSING_CONFIG
    if not isinstance(code, str):
        return URL_BLOCKED
    if code in PUBLIC_ERROR_CODES:
        return code
    if code in _INTERNAL_URL_ERRORS:
        return URL_BLOCKED
    if code in ('MISSING_CONFIG', 'PROVIDER_NOT_CONFIGURED', 'MISSING_PROVIDER_CONFIG'):
        return MISSING_CONFIG
    if code in ('REDIRECT_FAILED', 'TOO_MANY_REDIRECTS', 'INVALID_REDIRECT'):
        return REDIRECT_BLOCKED
    return URL_BLOCKED


def _error_result(error):
    return {'error': {'code': map_error(error)}}


def _transport_or_error(transport, provider_config):
    if provider_config is not _UNSET and provider_config is None:
        raise _ClientError(MISSING_CONFIG)
    if transport is None:
        return pinned_fetch
    if not callable(transport):
        raise _ClientError(URL_BLOCKED)
    return transport


def _response_parts(response):
    if isinstance(response, (str, bytes)):
        status, body, final_url = 200, response, None
    elif isinstance(response, Mapping):
        envelope_fields = frozenset(('status', 'body', 'text', 'url', 'final_url'))
        if envelope_fields.intersection(response):
            status = response.get('status', 200)
            body = response.get('body', response.get('text', ''))
            final_url = response.get('url', response.get('final_url'))
        else:
            status, body, final_url = 200, json.dumps(response, ensure_ascii=False), None
    else:
        status = getattr(response, 'status', 200)
        body = getattr(response, 'body', getattr(response, 'text', ''))
        final_url = getattr(response, 'url', getattr(response, 'final_url', None))
    if isinstance(body, bytes):
        if len(body) > MAX_RESPONSE_BYTES:
            raise _ClientError(URL_BLOCKED)
        text = body.decode('utf-8', errors='replace')
    elif isinstance(body, str):
        text = body
    elif body is None:
        text = ''
    else:
        text = json.dumps(body, ensure_ascii=False) if isinstance(body, (Mapping, list)) else str(body)
    if len(text.encode('utf-8')) > MAX_RESPONSE_BYTES:
        raise _ClientError(URL_BLOCKED)
    try:
        status = int(status)
    except (TypeError, ValueError, OverflowError):
        status = 0
    return status, text, final_url


def _fetch(url, transport):
    allowed, code = check_url(url)
    if not allowed:
        raise _ClientError(code)
    response = transport(url)
    status, text, final_url = _response_parts(response)
    if final_url:
        allowed, _code = check_url(final_url)
        if not allowed:
            raise _ClientError(REDIRECT_BLOCKED)
    if not 200 <= status < 300:
        raise _ClientError(URL_BLOCKED)
    return text


def _query_or_error(query):
    if not isinstance(query, str) or not query.strip():
        raise _ClientError(URL_BLOCKED)
    return query.strip()


def _bounded_integer(value, lower=1, upper=MAX_RESULTS):
    if type(value) is not int or not lower <= value <= upper:
        raise _ClientError(URL_BLOCKED)
    return value


def _truncate(value, limit=MAX_CONTENT_CHARS):
    if not isinstance(value, str):
        value = '' if value is None else str(value)
    return value[:limit], len(value) > limit


def _clean_text(value):
    if not isinstance(value, str):
        return ''
    parser = _TextParser()
    parser.feed(value)
    parser.close()
    return ' '.join(' '.join(parser.parts).split())


def _first_text(value):
    if isinstance(value, list):
        value = value[0] if value else ''
    return _clean_text(value)


def _safe_url(value):
    if not isinstance(value, str):
        return None
    allowed, _code = check_url(value)
    return value if allowed else None


def _json_payload(endpoint, params, transport):
    url = endpoint + '?' + urlencode(params)
    text = _fetch(url, transport)
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        raise _ClientError(URL_BLOCKED) from None
    if not isinstance(payload, Mapping):
        raise _ClientError(URL_BLOCKED)
    return payload


def _date_year(record):
    for field in ('published-print', 'published-online', 'issued'):
        date = record.get(field)
        if not isinstance(date, Mapping):
            continue
        date_parts = date.get('date-parts')
        if not isinstance(date_parts, list) or not date_parts or not isinstance(date_parts[0], list):
            continue
        if date_parts[0] and type(date_parts[0][0]) is int:
            return date_parts[0][0]
    return None


def _scholar_results(payload, limit):
    message = payload.get('message')
    items = message.get('items') if isinstance(message, Mapping) else None
    if not isinstance(items, list):
        raise _ClientError(URL_BLOCKED)
    truncated = len(items) > limit
    results = []
    for item in items[:limit]:
        if not isinstance(item, Mapping):
            continue
        title = _first_text(item.get('title'))
        doi_value = item.get('DOI')
        doi = doi_value.strip() if isinstance(doi_value, str) else ''
        url = _safe_url(item.get('URL'))
        if url is None and doi:
            url = _safe_url('https://doi.org/' + quote(doi, safe='/'))
        if not title or not url:
            continue
        title, title_cut = _truncate(title)
        raw_authors = item.get('author', [])
        authors = []
        author_cut = False
        if isinstance(raw_authors, list):
            author_cut = len(raw_authors) > 20
            for author in raw_authors[:20]:
                if not isinstance(author, Mapping):
                    continue
                name = ' '.join(part.strip() for part in (author.get('given', ''), author.get('family', ''))
                                if isinstance(part, str) and part.strip())
                if name:
                    name, name_cut = _truncate(name)
                    author_cut = author_cut or name_cut
                    authors.append(name)
        venue, venue_cut = _truncate(_first_text(item.get('container-title')))
        truncated = truncated or title_cut or author_cut or venue_cut
        results.append({
            'title': title,
            'url': url,
            'doi': doi,
            'authors': authors,
            'year': _date_year(item),
            'venue': venue,
        })
    return {'ok': True, 'results': results, 'truncated': truncated}


def scholar_search(query, transport=None, *, limit=MAX_RESULTS, provider_config=_UNSET):
    try:
        fetch = _transport_or_error(transport, provider_config)
        search_text = _query_or_error(query)
        result_limit = _bounded_integer(limit)
        params = {
            'query': search_text,
            'rows': result_limit,
            'select': 'DOI,title,author,published-print,published-online,issued,container-title,URL',
        }
        payload = _json_payload(_CROSSREF_ENDPOINT, params, fetch)
        return _scholar_results(payload, result_limit)
    except Exception as error:
        return _error_result(error)


def _news_results(payload, limit):
    articles = payload.get('articles')
    if not isinstance(articles, list):
        raise _ClientError(URL_BLOCKED)
    truncated = len(articles) > limit
    results = []
    for article in articles[:limit]:
        if not isinstance(article, Mapping):
            continue
        title = _clean_text(article.get('title'))
        url = _safe_url(article.get('url'))
        if not title or not url:
            continue
        title, title_cut = _truncate(title)
        snippet, snippet_cut = _truncate(_clean_text(article.get('snippet', '')))
        published, published_cut = _truncate(_clean_text(article.get('seendate', '')))
        source, source_cut = _truncate(_clean_text(article.get('domain', '')))
        language, language_cut = _truncate(_clean_text(article.get('language', '')))
        country, country_cut = _truncate(_clean_text(article.get('sourcecountry', '')))
        truncated = truncated or title_cut or snippet_cut or published_cut or source_cut or language_cut or country_cut
        results.append({
            'title': title,
            'url': url,
            'snippet': snippet,
            'published': published,
            'source': source,
            'language': language,
            'country': country,
        })
    return {'ok': True, 'results': results, 'truncated': truncated}


def news_search(query, transport=None, *, limit=MAX_RESULTS, provider_config=_UNSET):
    try:
        fetch = _transport_or_error(transport, provider_config)
        search_text = _query_or_error(query)
        result_limit = _bounded_integer(limit)
        params = {
            'query': search_text,
            'mode': 'artlist',
            'format': 'json',
            'maxrecords': result_limit,
            'sort': 'hybridrel',
        }
        payload = _json_payload(_GDELT_ENDPOINT, params, fetch)
        return _news_results(payload, result_limit)
    except Exception as error:
        return _error_result(error)


def _metadata_text(metadata, key):
    value = metadata.get(key, '') if isinstance(metadata, Mapping) else ''
    if isinstance(value, Mapping):
        value = value.get('value', '')
    return _clean_text(value)


def _commons_pages(payload):
    query = payload.get('query')
    pages = query.get('pages') if isinstance(query, Mapping) else None
    if isinstance(pages, list):
        return pages
    if isinstance(pages, Mapping):
        return list(pages.values())
    raise _ClientError(URL_BLOCKED)


def _image_results(payload, limit):
    pages = _commons_pages(payload)
    truncated = len(pages) > limit
    results = []
    for page in pages[:limit]:
        if not isinstance(page, Mapping):
            continue
        title = _clean_text(page.get('title'))
        infos = page.get('imageinfo')
        if not title or not isinstance(infos, list) or not infos or not isinstance(infos[0], Mapping):
            continue
        info = infos[0]
        extmetadata = info.get('extmetadata', {})
        if not isinstance(extmetadata, Mapping):
            extmetadata = {}
        image_url = _safe_url(info.get('thumburl')) or _safe_url(info.get('url'))
        page_url = _safe_url(info.get('descriptionurl'))
        license_name = _metadata_text(extmetadata, 'LicenseShortName')
        if not image_url or not page_url or not license_name:
            continue
        title, title_cut = _truncate(title)
        description, description_cut = _truncate(_metadata_text(extmetadata, 'ImageDescription'))
        creator, creator_cut = _truncate(_metadata_text(extmetadata, 'Artist') or _metadata_text(extmetadata, 'Credit'))
        license_name, license_cut = _truncate(license_name)
        license_url = _safe_url(_metadata_text(extmetadata, 'LicenseUrl')) or ''
        truncated = truncated or title_cut or description_cut or creator_cut or license_cut
        results.append({
            'title': title,
            'url': image_url,
            'page_url': page_url,
            'description': description,
            'creator': creator,
            'license': license_name,
            'license_url': license_url,
        })
    return {'ok': True, 'results': results, 'truncated': truncated}


def image_search(query, transport=None, *, limit=MAX_RESULTS, provider_config=_UNSET):
    try:
        fetch = _transport_or_error(transport, provider_config)
        search_text = _query_or_error(query)
        result_limit = _bounded_integer(limit)
        params = {
            'action': 'query',
            'generator': 'search',
            'gsrsearch': search_text,
            'gsrnamespace': 6,
            'gsrlimit': result_limit,
            'prop': 'imageinfo',
            'iiprop': 'url|extmetadata',
            'iiextmetadatafilter': 'LicenseShortName|LicenseUrl|Artist|Credit|ImageDescription',
            'iiurlwidth': 800,
            'format': 'json',
            'formatversion': 2,
        }
        payload = _json_payload(_COMMONS_ENDPOINT, params, fetch)
        return _image_results(payload, result_limit)
    except Exception as error:
        return _error_result(error)


# Goat tool names are available for callers that use the existing registry style.
goat_scholar = scholar_search
goat_news = news_search
goat_images = image_search


def register():
    return {
        'goat_scholar': scholar_search,
        'goat_news': news_search,
        'goat_images': image_search,
    }


__all__ = [
    'MAX_CONTENT_CHARS',
    'MAX_RESULTS',
    'MISSING_CONFIG',
    'PUBLIC_ERROR_CODES',
    'REDIRECT_BLOCKED',
    'URL_BLOCKED',
    'goat_images',
    'goat_news',
    'goat_scholar',
    'image_search',
    'map_error',
    'news_search',
    'register',
    'scholar_search',
]
