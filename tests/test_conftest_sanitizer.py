"""Regression tests for the betamax cassette sanitizer in conftest.

These guard the security-critical redaction that keeps real Okta hosts and TOTP
shared secrets out of committed cassettes.
"""

import base64
import gzip
import json

from tests.conftest import _sanitize_cassette_file, sanitize_response_body

REAL_HOST = 'schubergphilis.oktapreview.com'
SECRET = 'C25GYBREALSECRET7'
_BODY = {
    'id': 'x',
    '_embedded': {'activation': {'sharedSecret': SECRET}},
    '_links': {'self': {'href': f'https://{REAL_HOST}/api/v1/x'}},
}


def _gzip_b64(text: str) -> str:
    return base64.b64encode(gzip.compress(text.encode(), mtime=0)).decode()


def _decode(body: dict) -> str:
    if 'base64_string' in body:
        return gzip.decompress(base64.b64decode(body['base64_string'])).decode()
    return body['string']


def test_sanitize_gzip_body_redacts_secret_and_host():
    body = {'base64_string': _gzip_b64(json.dumps(_BODY))}
    sanitize_response_body(body, REAL_HOST)
    out = _decode(body)
    assert json.loads(out)['_embedded']['activation']['sharedSecret'] == 'REDACTED'
    assert REAL_HOST not in out
    assert SECRET not in out
    assert '"id": "x"' in out  # unrelated content preserved


def test_sanitize_plaintext_body_redacts_secret_and_host():
    body = {'string': json.dumps(_BODY)}
    sanitize_response_body(body, REAL_HOST)
    assert 'REDACTED' in body['string']
    assert REAL_HOST not in body['string']
    assert SECRET not in body['string']


def test_sanitize_is_noop_without_sensitive_data():
    body = {'base64_string': _gzip_b64('{"x": 1}')}
    before = body['base64_string']
    sanitize_response_body(body, REAL_HOST)
    assert body['base64_string'] == before


def test_sanitize_cassette_file_scrubs_all_interactions(tmp_path):
    cassette = tmp_path / 'c.json'
    cassette.write_text(
        json.dumps(
            {
                'http_interactions': [
                    {'response': {'body': {'base64_string': _gzip_b64(json.dumps(_BODY))}}},
                    {'response': {'body': {'string': json.dumps(_BODY)}}},
                ]
            }
        )
    )
    _sanitize_cassette_file(cassette, REAL_HOST)
    data = json.loads(cassette.read_text())
    for interaction in data['http_interactions']:
        raw = _decode(interaction['response']['body'])
        assert SECRET not in raw
        assert REAL_HOST not in raw
        assert 'REDACTED' in raw
