import json
import os
import sys
import unittest.mock as mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'agents', 'ubuntu'))

# lock_listener imports dbus/gi at module level; stub them before importing
dbus_stub = mock.MagicMock()
gi_stub = mock.MagicMock()
sys.modules.setdefault('dbus', dbus_stub)
sys.modules.setdefault('dbus.mainloop', mock.MagicMock())
sys.modules.setdefault('dbus.mainloop.glib', mock.MagicMock())
sys.modules.setdefault('gi', gi_stub)
sys.modules.setdefault('gi.repository', mock.MagicMock())
sys.modules.setdefault('gi.repository.GLib', mock.MagicMock())
gi_stub.require_version = mock.MagicMock()

from lock_listener import post_event  # noqa: E402


class TestPostEvent:
    def _mock_response(self, body_dict):
        resp = mock.MagicMock()
        resp.read.return_value = json.dumps(body_dict).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = mock.MagicMock(return_value=False)
        return resp

    def test_posts_login_event(self):
        resp = self._mock_response({'inserted': 1, 'skipped': 0})
        with mock.patch('urllib.request.urlopen', return_value=resp) as m:
            inserted, skipped = post_event('http://server:8000', 'mypc', 'login')

        req = m.call_args[0][0]
        body = json.loads(req.data)
        assert body['computer'] == 'mypc'
        assert len(body['events']) == 1
        assert body['events'][0]['action'] == 'login'
        assert inserted == 1
        assert skipped == 0

    def test_posts_logout_event(self):
        resp = self._mock_response({'inserted': 1, 'skipped': 0})
        with mock.patch('urllib.request.urlopen', return_value=resp):
            post_event('http://server:8000', 'mypc', 'logout')

        resp.read.return_value = json.dumps({'inserted': 1, 'skipped': 0}).encode()
        resp2 = self._mock_response({'inserted': 1, 'skipped': 0})
        with mock.patch('urllib.request.urlopen', return_value=resp2) as m:
            post_event('http://server:8000', 'mypc', 'logout')
        req = m.call_args[0][0]
        body = json.loads(req.data)
        assert body['events'][0]['action'] == 'logout'

    def test_uses_api_sync_endpoint(self):
        resp = self._mock_response({'inserted': 1, 'skipped': 0})
        with mock.patch('urllib.request.urlopen', return_value=resp) as m:
            post_event('http://server:8000', 'mypc', 'login')
        req = m.call_args[0][0]
        assert req.full_url == 'http://server:8000/api/sync'

    def test_http_error_returns_zero_counts(self):
        import urllib.error
        with mock.patch('urllib.request.urlopen',
                        side_effect=urllib.error.HTTPError(
                            url='', code=500, msg='Server Error', hdrs=None, fp=None)):
            inserted, skipped = post_event('http://server:8000', 'mypc', 'login')
        assert inserted == 0
        assert skipped == 0

    def test_connection_error_returns_zero_counts(self):
        import urllib.error
        with mock.patch('urllib.request.urlopen',
                        side_effect=urllib.error.URLError('connection refused')):
            inserted, skipped = post_event('http://server:8000', 'mypc', 'login')
        assert inserted == 0
        assert skipped == 0

    def test_event_has_iso_timestamp(self):
        resp = self._mock_response({'inserted': 1, 'skipped': 0})
        with mock.patch('urllib.request.urlopen', return_value=resp) as m:
            post_event('http://server:8000', 'mypc', 'login')
        req = m.call_args[0][0]
        body = json.loads(req.data)
        from datetime import datetime
        ts = body['events'][0]['timestamp']
        datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S')  # raises if format wrong
