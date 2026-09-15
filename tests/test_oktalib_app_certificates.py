"""Tests for application signing certificate functionality."""
# pylint: disable=redefined-outer-name

import json
from datetime import UTC, datetime, timedelta

import pytest
from requests import Response

from oktalib.entities import AppKey, AppSigningCertificate
from oktalib.entities.apps import Application

APP_DATA = {'id': '0oaapp1', 'label': 'An app', 'signOnMode': 'SAML_2_0'}


def make_key(kid, expires_at=None, **extra):
    """Build the key payload Okta returns for one application key credential."""
    data = {'kid': kid, 'kty': 'RSA', 'use': 'sig', 'created': '2020-01-01T00:00:00.000Z', **extra}
    if expires_at is not None:
        data['expiresAt'] = expires_at
    return data


def iso_in(days):
    """An ISO 8601 UTC timestamp the given number of days from now."""
    return (datetime.now(tz=UTC) + timedelta(days=days)).isoformat().replace('+00:00', 'Z')


def make_json_response(payload):
    """Build an ok Response carrying the provided JSON payload."""
    response = Response()
    response.status_code = 200
    response._content = json.dumps(payload).encode()
    return response


@pytest.fixture
def application(okta_service):
    """An Application backed by static data, making no requests of its own."""
    return Application(okta_service, dict(APP_DATA))


def test_id_is_the_kid(okta_service):
    """Okta identifies keys by kid, so that is what the entity exposes as its id."""
    certificate = AppSigningCertificate(okta_service, APP_DATA, make_key('abc123'))
    assert certificate.id == 'abc123'


def test_distinct_kids_do_not_collide(okta_service):
    """Two different keys must not compare equal nor collapse in a set.

    The base entity reads a non-existent 'id' field for these, which would make
    every key hash to hash('') and compare equal to every other key.
    """
    first = AppSigningCertificate(okta_service, APP_DATA, make_key('kid-one'))
    second = AppSigningCertificate(okta_service, APP_DATA, make_key('kid-two'))
    assert first != second
    assert len({first, second}) == 2


def test_same_kid_is_the_same_certificate(okta_service):
    """Equality still holds for two entities describing the same key."""
    assert AppSigningCertificate(okta_service, APP_DATA, make_key('kid-one')) == AppSigningCertificate(
        okta_service, APP_DATA, make_key('kid-one')
    )


def test_url_is_built_from_the_parent_app(okta_service):
    """The key payload carries no app id, so the url comes from the parent app."""
    certificate = AppSigningCertificate(okta_service, APP_DATA, make_key('abc123'))
    assert certificate.url == f'{okta_service.session.api}/apps/0oaapp1/credentials/keys/abc123'


def test_inherited_entity_properties(okta_service):
    """The base entity's date parsing works, since 'created' matches its contract."""
    certificate = AppSigningCertificate(okta_service, APP_DATA, make_key('abc123'))
    assert certificate.created_at == datetime(2020, 1, 1, tzinfo=UTC)
    assert certificate.key_type == 'RSA'
    assert certificate.use == 'sig'


def test_x509_fields(okta_service):
    """The certificate chain and thumbprint are exposed when present."""
    certificate = AppSigningCertificate(
        okta_service, APP_DATA, make_key('abc123', x5c=['MIIDcert'], **{'x5t#S256': 'thumb'})
    )
    assert certificate.x509_chain == ['MIIDcert']
    assert certificate.thumbprint == 'thumb'


def test_x509_fields_default_when_absent(okta_service):
    """A key without x509 material reports an empty chain and no thumbprint."""
    certificate = AppSigningCertificate(okta_service, APP_DATA, make_key('abc123'))
    assert certificate.x509_chain == []
    assert certificate.thumbprint is None


def test_expired_certificate(okta_service):
    """A certificate whose expiry has passed is expired."""
    certificate = AppSigningCertificate(okta_service, APP_DATA, make_key('abc123', expires_at=iso_in(-1)))
    assert certificate.is_expired
    assert certificate.expires_within(30)


def test_valid_certificate(okta_service):
    """A certificate expiring beyond the window is neither expired nor expiring."""
    certificate = AppSigningCertificate(okta_service, APP_DATA, make_key('abc123', expires_at=iso_in(90)))
    assert not certificate.is_expired
    assert not certificate.expires_within(30)
    assert certificate.expires_within(120)


def test_certificate_without_expiry_never_expires(okta_service):
    """A key with no expiresAt is never reported as expired or expiring."""
    certificate = AppSigningCertificate(okta_service, APP_DATA, make_key('abc123'))
    assert certificate.expires_at is None
    assert not certificate.is_expired
    assert not certificate.expires_within(3650)


def test_app_key_base_has_no_expiry_concept(okta_service):
    """The base key models the shared JWK fields only; expiry is the subclass's.

    JSON Web Keys used for private_key_jwt client authentication have no expiry,
    which is why the split exists.
    """
    key = AppKey(okta_service, APP_DATA, make_key('abc123'))
    assert key.id == 'abc123'
    assert not hasattr(key, 'expires_at')


def test_signing_certificates_are_listed(application, monkeypatch):
    """The application yields a certificate per key the endpoint returns."""
    payload = [make_key('kid-one', expires_at=iso_in(10)), make_key('kid-two', expires_at=iso_in(400))]
    monkeypatch.setattr(application._okta.session, 'get', lambda *a, **k: make_json_response(payload))
    assert [certificate.id for certificate in application.signing_certificates] == ['kid-one', 'kid-two']


def test_expiring_signing_certificates_filters(application, monkeypatch):
    """Only the certificates inside the window are yielded."""
    payload = [
        make_key('expired', expires_at=iso_in(-5)),
        make_key('soon', expires_at=iso_in(10)),
        make_key('later', expires_at=iso_in(400)),
        make_key('no-expiry'),
    ]
    monkeypatch.setattr(application._okta.session, 'get', lambda *a, **k: make_json_response(payload))
    found = [certificate.id for certificate in application.expiring_signing_certificates(30)]
    assert found == ['expired', 'soon']


def test_signing_certificates_survives_error(application, monkeypatch):
    """A non-JSON error body yields nothing instead of raising."""
    error = Response()
    error.status_code = 502
    error._content = b'<html>502 Bad Gateway</html>'
    monkeypatch.setattr(application._okta.session, 'get', lambda *a, **k: error)
    assert not list(application.signing_certificates)


def test_org_wide_scan_skips_non_signing_apps(okta_service, monkeypatch):
    """Only apps whose sign-on mode signs assertions cost an extra request.

    The sign-on mode is already in the application listing, so narrowing is
    free; an OIDC app must not be asked for signing certificates at all.
    """
    apps = [
        Application(okta_service, {'id': '0oasaml', 'label': 'SAML app', 'signOnMode': 'SAML_2_0'}),
        Application(okta_service, {'id': '0oaoidc', 'label': 'OIDC app', 'signOnMode': 'OPENID_CONNECT'}),
        Application(okta_service, {'id': '0oawsfed', 'label': 'WS-Fed app', 'signOnMode': 'WS_FEDERATION'}),
    ]
    monkeypatch.setattr(type(okta_service), 'applications', property(lambda self: iter(apps)))

    requested = []

    def record(url, *_args, **_kwargs):
        requested.append(url)
        return make_json_response([make_key('kid-of-' + url.split('/apps/')[1].split('/')[0], expires_at=iso_in(5))])

    monkeypatch.setattr(okta_service.session, 'get', record)

    found = list(okta_service.get_expiring_app_certificates(days=30))
    assert [app.id for app, _ in found] == ['0oasaml', '0oawsfed']
    assert not any('0oaoidc' in url for url in requested)


def test_expired_app_certificates_is_a_zero_day_window(okta_service, monkeypatch):
    """The expired helper is the expiring helper with a zero-day window."""
    app = Application(okta_service, dict(APP_DATA))
    monkeypatch.setattr(type(okta_service), 'applications', property(lambda self: iter([app])))
    payload = [make_key('expired', expires_at=iso_in(-1)), make_key('soon', expires_at=iso_in(10))]
    monkeypatch.setattr(okta_service.session, 'get', lambda *a, **k: make_json_response(payload))
    assert [certificate.id for _, certificate in okta_service.get_expired_app_certificates()] == ['expired']
