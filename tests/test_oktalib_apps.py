"""Tests for Application functionality."""

import logging

import pytest
from betamax import Betamax

from oktalib.entities import APIServiceApp


@pytest.fixture
def api_service_app_cleaner():
    """Fixture that ensures API service apps are cleaned up after tests."""
    apps_to_clean = []

    def register(app):
        """Register an app for cleanup after the test."""
        if app is not None:
            apps_to_clean.append(app)
        return app

    yield register

    logger = logging.getLogger(__name__)
    for app in apps_to_clean:
        try:
            app.deactivate()
            app.delete()
        except Exception as e:
            # Ignore 404 errors (app already deleted or not found)
            error_str = str(e).lower()
            if '404' in error_str or 'not found' in error_str:
                continue
            logger.warning(f'Failed to cleanup app {getattr(app, "id", "unknown")}: {e}')


# saml_application


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


def test_get_application_by_sign_on_mode_with_none(okta_service):
    """Test that None sign_on_mode is handled gracefully."""
    app = okta_service.get_application_by_sign_on_mode(None)
    assert app is None


# api_service_app


def test_create_api_service_app_client_secret_auth(
    okta_cassette, okta_service, api_service_app_cleaner
):
    """Test creating an API Service application."""
    with okta_cassette():
        app = api_service_app_cleaner(
            okta_service.create_application_with_client_secret(
                label='Test API Service App with Client Secret Auth'
            )
        )
        assert app is not None
        assert app.label == 'Test API Service App with Client Secret Auth'
        assert app.sign_on_mode == 'OPENID_CONNECT'
        # Validate client secret lifecycle: deactivate first, then delete.
        assert app.create_client_secrets() is not None
        secrets = app.client_secrets
        assert len(secrets) >= 1
        secret = secrets[0]
        assert secret.deactivate() is True
        assert secret.delete() is True


def test_create_api_service_app_private_key_jwt_auth_public_key_url(
    okta_cassette, okta_service, api_service_app_cleaner
):
    """Test creating an API Service application with private_key_jwt authentication."""
    with okta_cassette():
        app = api_service_app_cleaner(
            okta_service.create_application_with_jwks_uri(
                label='Test API Service App with JWT Auth and JWKS URI',
                jwks_uri='https://some-service.com/oauth/discovery/keys',
            )
        )
        assert app is not None
        assert app.label == 'Test API Service App with JWT Auth and JWKS URI'
        assert app.sign_on_mode == 'OPENID_CONNECT'
        assert app.jwks_uri == 'https://some-service.com/oauth/discovery/keys'
        assert app.is_public_keys_configured is True
        assert app.jwks is None
        assert app.client_authentication == 'private_key_jwt'
        app.add_grants(['okta.accessRequests.catalog.read', 'okta.agentPools.manage'])
        assert len(list(app.grants)) == 2
        app.add_client_roles(['MOBILE_ADMIN'])
        assert len(list(app.client_roles)) == 1


def test_create_api_service_app_private_key_jwt_auth_public_key_provided(
    okta_cassette, okta_service, api_service_app_cleaner
):
    """Test creating an API Service application with private_key_jwt auth and inline JWKS."""
    with okta_cassette():
        app = api_service_app_cleaner(
            okta_service.create_application_with_jwks(
                label='Test API Service App with JWT Auth and Inline JWKS',
                jwks={
                    'kty': 'RSA',
                    'use': 'sig',
                    'kid': 'VEhN_hsU6SMK2qsuEqHFRQ43qJEjuqqdheGuQl8bkno',
                    'alg': 'RS256',
                    'n': (
                        '0vx7agoebGcQSuuPiLJXZptN9nndrQmbXEps2aiMtjVdOM3iTQ8Yv'
                        'N0yC6W3v8I4Yf6M8hJf9x2xq3rY8f8Q2m7oA7Ww8Q5Q0M8GQY7r8Y8'
                        '8lF3Q6Y9xZ4Q6A7m7c5f8Q6G9w8G4V6h6J6m3d8Q6s9R7n2A9c5p7'
                        '8d6A8g5k8L9h5m7Q6Z8h8u8k7n8V9i8k7Y7z6j5f4s3d2a1q0w9e8'
                        'r7t6y5u4i3o2p1a0s9d8f7g6h5j4k3l2z1x0c9v8b7n6m5a4s3d2f1'
                        'g0h9j8k7l6z5x4c3v2b1n0m9q8w7e6r5t4y3u2i1o0p9a8s7d6f5g4'
                        'h3j2k1l0z9x8c7v6b5n4m3q2w1e0r9t8y7u6i5o4p3a2s1d0f9g8h7'
                        'j6k5l4z3x2c1v0b9n8m7q6w5e4r3t2y1u0i9o8p7a6s5d4f3g2h1'
                    ),
                    'e': 'AQAB',
                },
            )
        )
        assert app is not None
        assert app.label == 'Test API Service App with JWT Auth and Inline JWKS'
        assert app.sign_on_mode == 'OPENID_CONNECT'


# add network zones from where the token can be used


# Error scenario tests


def test_create_api_service_app_cleanup_on_configuration_failure(
    okta_cassette, okta_service, api_service_app_cleaner, monkeypatch
):
    """Test that app is cleaned up if configuration fails after creation."""
    with okta_cassette():
        app = api_service_app_cleaner(
            okta_service.create_application_with_client_secret(
                label='Test API Service App - Cleanup Test'
            )
        )
        assert app is not None

        def mock_add_public_keys_failure(*args, **kwargs):
            raise RuntimeError('Simulated failure during public key configuration')

        monkeypatch.setattr(
            APIServiceApp, 'add_public_keys_by_public_url', mock_add_public_keys_failure
        )

        failed_app = okta_service.create_application_with_jwks_uri(
            label='Test API Service App - Should Be Cleaned Up',
            jwks_uri='https://some-service.com/oauth/discovery/keys',
        )

        assert failed_app is None


def test_create_api_service_app_with_client_secret_no_keys_required(
    okta_cassette, okta_service, api_service_app_cleaner
):
    """Test that client_secret auth doesn't require jwks_uri or jwks."""
    with okta_cassette():
        # This should succeed - client_secret doesn't need keys
        app = api_service_app_cleaner(
            okta_service.create_application_with_client_secret(
                label='Test API Service App - Client Secret No Keys',
                # No jwks_uri or jwks provided, and that's OK for client_secret
            )
        )
        assert app is not None
        assert app.label == 'Test API Service App - Client Secret No Keys'
        assert app.client_authentication == 'client_secret_basic'


def test_create_api_service_app_add_and_remove_client_role(
    okta_cassette, okta_service, api_service_app_cleaner
):
    """Test adding and removing a client role (Okta admin role) from an API Service app."""
    with okta_cassette():
        app = api_service_app_cleaner(
            okta_service.create_application_with_client_secret(
                label='Test API Service App - Client Role Lifecycle',
            )
        )
        assert app is not None

        # Add a client role (Okta admin role)
        client_role = app.add_client_role('MOBILE_ADMIN')
        assert client_role is not None
        assert client_role.type == 'MOBILE_ADMIN'

        # Verify it was added
        roles = list(app.client_roles)
        assert len(roles) == 1
        assert roles[0].type == 'MOBILE_ADMIN'

        # Remove the client role
        assert client_role.delete() is True

        # Verify it was removed
        roles_after_delete = list(app.client_roles)
        assert len(roles_after_delete) == 0


def test_create_api_service_app_add_and_remove_client_secrets(
    okta_cassette, okta_service, api_service_app_cleaner
):
    """Test adding and removing client secrets from an API Service app."""
    with okta_cassette():
        app = api_service_app_cleaner(
            okta_service.create_application_with_client_secret(
                label='Test API Service App - Client Secret Lifecycle',
            )
        )
        assert app is not None

        # Initially should have no client secrets (or only the default one)
        initial_secrets = app.client_secrets
        initial_count = len(initial_secrets) if initial_secrets else 0

        # Create a new client secret
        new_secret = app.create_client_secrets()
        assert new_secret is not None
        assert new_secret.client_secret is not None  # Should have the secret value
        assert new_secret.status == 'ACTIVE'

        # Verify it was added
        secrets_after_create = app.client_secrets
        assert len(secrets_after_create) == initial_count + 1

        # Deactivate the client secret
        assert new_secret.deactivate() is True

        # Verify it was deactivated by checking status
        secrets_after_deactivate = app.client_secrets
        deactivated_secret = next(s for s in secrets_after_deactivate if s.id == new_secret.id)
        assert deactivated_secret.status == 'INACTIVE'

        # Delete the deactivated client secret
        assert new_secret.delete() is True

        # Verify it was deleted
        secrets_after_delete = app.client_secrets
        assert len(secrets_after_delete) == initial_count
        # Verify the specific secret is gone
        assert not any(s.id == new_secret.id for s in secrets_after_delete)


def test_create_api_service_app_max_client_secrets_limit(
    okta_cassette, okta_service, api_service_app_cleaner, caplog
):
    """Test that creating more than 2 client secrets fails with appropriate error message."""
    with okta_cassette():
        app = api_service_app_cleaner(
            okta_service.create_application_with_client_secret(
                label='Test API Service App - Max Secrets Limit',
            )
        )
        assert app is not None

        # Get initial secrets count
        initial_secrets = app.client_secrets
        initial_count = len(initial_secrets) if initial_secrets else 0

        # Create secrets until we have 2 total
        secrets_to_create = 2 - initial_count
        for _ in range(secrets_to_create):
            secret = app.create_client_secrets()
            assert secret is not None

        # Verify we now have 2 secrets
        current_secrets = app.client_secrets
        assert len(current_secrets) == 2

        # Try to create a third secret - should fail
        third_secret = app.create_client_secrets()
        assert third_secret is None

        # Verify the error log mentions the maximum of 2 secrets
        assert any('Maximum of 2 client secrets' in record.message for record in caplog.records), (
            'Error message should mention the maximum of 2 client secrets'
        )
