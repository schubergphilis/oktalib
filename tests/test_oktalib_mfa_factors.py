"""Tests for MFA (Multi-Factor Authentication) factors functionality."""
# pylint: disable=redefined-outer-name

import pytest
from betamax import Betamax


@pytest.fixture(scope='module')
def test_user(okta_service, okta_recorder):  # pylint: disable=unused-argument
    """Module-scoped fixture that provides a test user for MFA testing.

    Uses okta_recorder instead of okta_cassette since module-scoped
    fixtures can't use function-scoped fixtures.

    Note: This fixture expects a user 'test_user@example.com' to exist
    in the Okta instance with MFA factors enrolled. Tests will be skipped
    if the user is not found.
    """
    with Betamax(okta_service.session).use_cassette('test_mfa_user'):
        user = okta_service.get_user_by_login('test_user@example.com')
        if user is None:
            pytest.skip("Test user 'test_user@example.com' not found in Okta instance")
        yield user


def test_get_mfa_enrolled_factors(okta_cassette, test_user):
    """Test retrieving enrolled MFA factors for a user."""
    with okta_cassette():
        factors = list(test_user.enrolled_factors())
        assert factors is not None
        assert len(factors) > 0
        assert factors[0].factor_type == 'signed_nonce'
        assert factors[0].provider == 'OKTA'
        assert factors[0].vendor_name == 'OKTA'
        assert factors[0].status == 'ACTIVE'
        assert factors[0].profile is not None


def test_supported_factors(okta_cassette, test_user):
    """Test retrieving supported (but not enrolled) MFA factors from catalog."""
    with okta_cassette():
        supported_factors = list(test_user.supported_factors())
        assert supported_factors is not None
        assert len(supported_factors) > 0
        assert supported_factors[0].factor_type == 'token:software:totp'
        assert supported_factors[0].provider == 'GOOGLE'
        assert supported_factors[0].vendor_name == 'GOOGLE'
        assert (
            supported_factors[0].enroll_link
            == f'{test_user._okta.host}/api/v1/users/{test_user.id}/factors'
        )
