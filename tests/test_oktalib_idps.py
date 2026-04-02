"""Tests for Identity Provider (IDP) functionality."""
# pylint: disable=redefined-outer-name

import logging

import pytest
from betamax import Betamax


@pytest.fixture
def idp_cleaner():
    """Fixture that ensures IDPs are cleaned up after tests."""
    idps_to_clean = []

    def register(idp):
        """Register an IDP for cleanup after the test."""
        if idp is not None:
            idps_to_clean.append(idp)
        return idp

    yield register

    logger = logging.getLogger(__name__)
    for idp in idps_to_clean:
        try:
            idp.deactivate()
            idp.delete()
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Ignore 404 errors (IDP already deleted or not found)
            # Catch all exceptions in cleanup to avoid breaking other tests
            error_str = str(e).lower()
            if '404' in error_str or 'not found' in error_str:
                continue
            logger.warning(f'Failed to cleanup IDP {getattr(idp, "id", "unknown")}: {e}')


@pytest.fixture
def idp_factory(okta_service, idp_cleaner):
    """Factory fixture for creating test SAML IDPs with consistent configuration."""

    def _create_idp(name: str, **kwargs):
        """Create a test SAML IDP with default configuration.

        Args:
            name: The name of the IDP
            **kwargs: Additional parameters to override defaults

        Returns:
            IDP: The created IDP instance
        """
        # Default parameters
        # Note: Uses an existing IDP key from the test environment
        # (see test_oktalib_idp_keys for available keys)
        params = {
            'okta_idp_issuer_url': 'http://www.okta.com/exk_test_issuer',
            'okta_idp_sso_url': f'{okta_service.host}/app/test_app/exk_test/sso/saml',
            'kid': '1bc1ad82-2818-4a29-9c1b-945dad3d18eb',  # Existing test key
            'idp_username': 'idpuser.subjectNameId',
            'trust_claims': True,
            'users_regex_filter': '.*@example.com',
        }
        # Override with any provided kwargs
        params.update(kwargs)

        idp = okta_service.create_saml_idp(name=name, **params)
        idp_cleaner(idp)
        return idp

    return _create_idp


@pytest.fixture(scope='module')
def test_saml_idp(okta_service, okta_recorder):  # pylint: disable=unused-argument
    """Module-scoped fixture that provides a test SAML IDP.

    Uses okta_recorder instead of okta_cassette since module-scoped
    fixtures can't use function-scoped fixtures.
    """
    with Betamax(okta_service.session).use_cassette('test_saml_idp'):
        # Try to get existing test IDP, or create one if it doesn't exist
        idp = okta_service.get_idp_by_name('test_saml_idp')
        if idp is None:
            idp = okta_service.create_saml_idp(
                name='test_saml_idp',
                okta_idp_issuer_url='http://www.okta.com/exk_test_issuer',
                okta_idp_sso_url=f'{okta_service.host}/app/test_app/exk_test/sso/saml',
                kid='1bc1ad82-2818-4a29-9c1b-945dad3d18eb',  # Existing test key
                idp_username='idpuser.subjectNameId',
                trust_claims=True,
                users_regex_filter='.*@example.com',
            )
        assert idp is not None, "Test SAML IDP 'test_saml_idp' not found"
        assert idp.name == 'test_saml_idp'
        yield idp


def test_get_idps(okta_cassette, okta_service):
    """Test retrieving all identity providers."""
    with okta_cassette():
        idps = list(okta_service.idps)
        assert idps is not None
        assert len(idps) > 0


def test_get_saml_idp(test_saml_idp):
    """Test that we can retrieve the test SAML IDP."""
    assert test_saml_idp.name == 'test_saml_idp'
    assert test_saml_idp.id is not None
    assert test_saml_idp.type == 'SAML2'


def test_saml_idp_properties(test_saml_idp):
    """Test SAML IDP properties and configuration."""
    assert test_saml_idp.claims is True
    assert test_saml_idp.policy.get('subject', {}).get('filter') == '.*@example.com'


def test_saml_idp_url_property(test_saml_idp):
    """Test that IDP url property is correctly constructed."""
    expected_url = f'{test_saml_idp._okta.api}/idps/{test_saml_idp.id}'
    assert test_saml_idp.url == expected_url


def test_create_saml_idp(okta_cassette, idp_factory):
    """Test creating a SAML identity provider with various configuration options."""
    with okta_cassette():
        idp = idp_factory('test_saml_idp_create')
        assert idp is not None
        assert idp.name == 'test_saml_idp_create'
        assert idp.type == 'SAML2'


def test_replace_saml_idp(okta_cassette, okta_service, idp_factory):
    """Test replacing/updating a SAML identity provider's properties."""
    with okta_cassette():
        idp = idp_factory('test_saml_idp_replace')
        idp.name = 'test_saml_idp_replace_updated'
        idp = okta_service.get_idp_by_name('test_saml_idp_replace_updated')
        assert idp is not None
        assert idp.name == 'test_saml_idp_replace_updated'


def test_activate_idp(okta_cassette, idp_factory):
    """Test activating an identity provider."""
    with okta_cassette():
        idp = idp_factory('test_saml_idp_activate')
        result = idp.activate()
        assert result is True
        assert idp.status == 'ACTIVE'


def test_deactivate_idp(okta_cassette, idp_factory):
    """Test deactivating an identity provider."""
    with okta_cassette():
        idp = idp_factory('test_saml_idp_deactivate')
        idp.activate()
        result = idp.deactivate()
        assert result is True
        assert idp.status == 'INACTIVE'


def test_delete_idp(okta_cassette, idp_factory):
    """Test deleting an identity provider."""
    with okta_cassette():
        idp = idp_factory('test_saml_idp_delete')
        idp.deactivate()
        result = idp.delete()
        assert result is True
