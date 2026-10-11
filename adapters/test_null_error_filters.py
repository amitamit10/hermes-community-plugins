import unittest
import socket

attempts = []
def denied(kind):
    def reject(*args, **kwargs):
        attempts.append(kind)
        raise AssertionError('offline verification forbids ' + kind)
    return reject
for name in ('getaddrinfo', 'gethostbyname', 'gethostbyname_ex', 'create_connection'):
    setattr(socket, name, denied(name))
socket.socket.connect = denied('socket.connect')
socket.socket.connect_ex = denied('socket.connect_ex')
socket.socket.sendto = denied('socket.sendto')
socket.socket.sendmsg = denied('socket.sendmsg')

from search_filters import URL_BLOCKED, with_search_filters

PAYLOAD = {'ok': True, 'error': None, 'results': [{'url': 'https://denied.example/a', 'language': 'fr', 'published_at': '2020-01-01'}]}

class NullErrorFilterTests(unittest.TestCase):
    def test_null_error_allowed_domain_is_filtered(self):
        actual = with_search_filters(lambda q: PAYLOAD, allowed_domains=['allowed.example'])('q')
        self.assertTrue(actual['ok'])
        self.assertEqual(actual['results'], [])
        self.assertEqual(attempts, [])

    def test_null_error_denied_domain_is_filtered(self):
        actual = with_search_filters(lambda q: PAYLOAD, denied_domains=['denied.example'])('q')
        self.assertTrue(actual['ok'])
        self.assertEqual(actual['results'], [])

    def test_null_error_time_after_is_filtered(self):
        actual = with_search_filters(lambda q: PAYLOAD, time_after='2025-01-01')('q')
        self.assertTrue(actual['ok'])
        self.assertEqual(actual['results'], [])

    def test_null_error_language_is_filtered(self):
        actual = with_search_filters(lambda q: PAYLOAD, language='en')('q')
        self.assertTrue(actual['ok'])
        self.assertEqual(actual['results'], [])

    def test_null_error_malformed_results_fails_closed(self):
        malformed = {'ok': True, 'error': None, 'results': None}
        actual = with_search_filters(lambda q: malformed)('q')
        self.assertEqual(actual, {'ok': False, 'error': {'code': URL_BLOCKED}})
        self.assertEqual(attempts, [])

    def test_actual_error_is_preserved(self):
        payload = {'ok': False, 'error': {'code': 'MISSING_CONFIG'}, 'results': [{'url': 'https://example.com/a'}]}
        actual = with_search_filters(lambda q: payload, language='en')('q')
        self.assertFalse(actual['ok'])
        self.assertEqual(actual['error']['code'], 'MISSING_CONFIG')

    def test_error_with_code_preserved(self):
        payload = {'ok': True, 'error': {'code': 'URL_BLOCKED'}, 'results': [{'url': 'https://example.com/a'}]}
        actual = with_search_filters(lambda q: payload, allowed_domains=['allowed.example'])('q')
        self.assertFalse(actual['ok'])
        self.assertEqual(actual['error']['code'], 'URL_BLOCKED')

    def test_ok_false_is_preserved(self):
        payload = {'ok': False, 'results': [{'url': 'https://example.com/a'}]}
        actual = with_search_filters(lambda q: payload, language='en')('q')
        self.assertFalse(actual['ok'])

    def test_without_error_key_still_filters(self):
        payload = {'ok': True, 'results': [{'url': 'https://denied.example/a', 'language': 'fr', 'published_at': '2020-01-01'}]}
        actual = with_search_filters(lambda q: payload, allowed_domains=['allowed.example'])('q')
        self.assertTrue(actual['ok'])
        self.assertEqual(actual['results'], [])
