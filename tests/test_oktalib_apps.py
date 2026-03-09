"""Tests for Application functionality."""

import pytest
from betamax import Betamax

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


# api_service_app

def test_create_api_service_app_client_secret_auth(okta_cassette, okta_service):
    """Test creating an API Service application."""
    with okta_cassette():
        app = okta_service.create_application_api_services(
            label='Test API Service App with Client Secret Auth', auth_method='client_secret'
        )
        assert app is not None
        assert app.label == 'Test API Service App with Client Secret Auth'
        assert app.sign_on_mode == 'OPENID_CONNECT'


def test_create_api_service_app_private_key_jwt_auth_public_key_url(okta_cassette, okta_service):
    """Test creating an API Service application with private_key_jwt authentication."""
    with okta_cassette():
        app = okta_service.create_application_api_services(
            label='Test API Service App with JWT Auth and JWKS URI',
            auth_method='private_key_jwt',
            jwks_uri='https://some-service.com/oauth/discovery/keys',
        )
        assert app is not None
        assert app.label == 'Test API Service App with JWT Auth and JWKS URI'
        assert app.sign_on_mode == 'OPENID_CONNECT'
        assert app.jwks_uri == 'https://some-service.com/oauth/discovery/keys'
        assert app.is_public_keys_enabled is True
        assert app.jwks is None
        assert app.client_authentication_method == 'private_key_jwt'


def test_create_api_service_app_private_key_jwt_auth_public_key_provided(
    okta_cassette, okta_service
):
    """Test creating an API Service application with private_key_jwt auth and inline JWKS."""
    with okta_cassette():
        # app = create simple app
        # add jwks via app.add_public_keys_by_jwks
        # then set auth method to private_key_jwt
        app = okta_service.create_application_api_services(
            label='Test API Service App with JWT Auth and Inline JWKS',
            auth_method='private_key_jwt',
            jwks={
                'keys': [
                    {
                        'kty': 'RSA',
                        'use': 'sig',
                        'kid': 'VEhN_hsU6SMK2qsuEqHFRQ43qJEjuqqdheGuQl8bkno',
                        'alg': 'RS256',
                        'n': (
                            'xjlJFq8sv_5hg7ZP8uJhM2KdRlZqmM7VvG9LmZ4B3Q8jH9xwEw3_vYm9Ck3LQ7PzF8YH'
                            '1M3TmH8R7VqB_x8jN9JmP8vYQ3H5jL8M6B_8H2N7Z9Q8J6L_3M8B7H_1P8K9YmH5N8L_'
                            '7Q6J8M_3B7H9P_8K5L6N_2M7J9Q8H3B6P7L_9K8M5N_3J6Q7H_2B8L9M_8P5K6N7Q_3H'
                            '9J8B_2M7L6P_8K9N5Q_3J7H8M_2B6L9P_8K5N7Q_3H8J9B_2M6L7P_8K9N5Q_3J8H7M_'
                            '2B9L6P_8K5N7Q_3H9J8B_2M7L6P_8K9N5Q_3J7H8M_2B6L9P_8K5N7Q_3H8J9B_2M6L7P'
                            '_8K9N5Q_3J8H7M_2B9L6P_8K5N7Q'
                        ),
                        'e': 'AQAB',
                    }
                ]
            },
        )
        assert app is not None
        assert app.label == 'Test API Service App with JWT Auth and Inline JWKS'
        assert app.sign_on_mode == 'OPENID_CONNECT'


# what if only private_key_jwt is provided without kid/jwks_uri/jwks? should it raise an error? should we test that?
# what if an invalid auth_method is provided? should it raise an error? should we test that?

# def create_application_api_services(
#     self,
#     label: str,
#     *,
#     auth_method: Literal['client_secret', 'private_key_jwt'] = 'client_secret',
#     kid: str | None = None,
#     jwks_uri: str | None = None,
#     jwks: dict[str, Any] | None = None,
#     auto_key_rotation: bool = True,
#     pkce_required: bool = False,
#     grant_types: list[str] | None = None,
#     response_types: list[str] | None = None,
#     issuer_mode: str = 'ORG_URL',
#     client_uri: str | None = None,
#     logo_uri: str | None = None,
#     redirect_uris: list[str] | None = None,
#     dpop_bound_access_tokens: bool = True,
#     consent_method: str = 'REQUIRED',
# ) -> Application | None:

# {
#     "credentials": {
#         "oauthClient": {
#             "token_endpoint_auth_method": "client_secret_basic"
#         }
#     },
#     "label": "My API Services App",
#     "name": "oidc_client",
#     "signOnMode": "OPENID_CONNECT",
#     "settings": {
#         "oauthClient": {
#             "application_type": "service",
#             "consent_method": "REQUIRED",
#             "grant_types": [
#                 "client_credentials"
#             ],
#             "response_types": [
#                 "token"
#             ],
#             "dpop_bound_access_tokens": true
#         }
#     }
# }
