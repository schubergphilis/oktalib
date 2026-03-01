"""Tests for Application functionality."""

import pytest
from betamax import Betamax


@pytest.fixture(scope='module')
def test_saml_app(okta_service, okta_recorder):  # pylint: disable=unused-argument
    """Module-scoped fixture that provides a test application.

    Uses okta_recorder instead of okta_cassette since module-scoped
    fixtures can't use function-scoped fixtures.
    """

    with Betamax(okta_service.session).use_cassette('saml_test_app'):
        app = okta_service.get_application_by_label('test_app')
        assert app is not None, "Test application 'test_app' not found"
        assert app.label == 'test_app'
        yield app


def test_get_app(test_saml_app):  # pylint: disable=redefined-outer-name
    """Test that we can retrieve the test application."""
    assert test_saml_app.label == 'test_app'
    assert test_saml_app.id is not None


def test_get_saml_application_metadata(okta_cassette, test_saml_app):
    """Test retrieving application metadata."""
    with okta_cassette():
        metadata = test_saml_app.metadata()
        sso = metadata.single_sign_on_services
        cert = metadata.x509_certificate

        assert metadata is not None
        assert metadata.entity_id == 'http://www.okta.com/exk2nq5bkqm3wrGtg0h8'
        assert sso is not None
        expected_post_url = (
            f'{test_saml_app._okta.host}/app/schubergphilis_testapp_1/exk2nq5bkqm3wrGtg0h8/sso/saml'
        )
        assert sso.http_post == expected_post_url
        assert (
            cert is not None and 'MIIDrDCCApSgAwIBAgIGAZyKxMVNMA0GCSqGSIb3DQEBCwUAMIGWMQsw' in cert
        )


def test_get_application_by_sign_on_mode_saml(okta_cassette, okta_service):
    """Test retrieving an application by SAML sign-on mode."""
    with okta_cassette():
        app = okta_service.get_application_by_sign_on_mode('SAML_2_0')
        assert app is not None
        assert app.sign_on_mode == 'SAML_2_0'


def test_get_application_by_sign_on_mode_case_insensitive(okta_cassette, okta_service):
    """Test that sign-on mode search is case-insensitive."""
    with okta_cassette():
        app = okta_service.get_application_by_sign_on_mode('saml_2_0')
        assert app is not None
        assert app.sign_on_mode == 'SAML_2_0'


def test_get_application_by_sign_on_mode_not_found(okta_cassette, okta_service):
    """Test that non-existent sign-on mode returns None."""
    with okta_cassette():
        app = okta_service.get_application_by_sign_on_mode('NONEXISTENT_MODE')
        assert app is None


# TODO: add tests for
#   application
#      get_application_by_sign_on_mode
#      create
