"""Tests for MFA (Multi-Factor Authentication) factors functionality."""
# pylint: disable=redefined-outer-name

import logging

import pyotp
import pytest

from oktalib.entities.users import UserFactorGoogleOTP


@pytest.fixture
def test_user_cleaner():
    """Fixture that ensures test users are cleaned up after tests."""
    users_to_clean = []

    def register(user):
        """Register a user for cleanup after the test."""
        if user is not None:
            users_to_clean.append(user)
        return user

    yield register

    logger = logging.getLogger(__name__)
    for user in users_to_clean:
        try:
            user.delete()
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Ignore 404 errors (user already deleted or not found)
            # Catch all exceptions in cleanup to avoid breaking other tests
            error_str = str(e).lower()
            if '404' in error_str or 'not found' in error_str:
                continue
            logger.warning(f'Failed to cleanup user {getattr(user, "id", "unknown")}: {e}')


def test_supported_factors(okta_cassette, okta_service, test_user_cleaner):
    """Test retrieving supported (but not enrolled) MFA factors from catalog."""
    with okta_cassette():
        # Create a test user
        test_user = test_user_cleaner(
            okta_service.create_user(
                first_name='Test',
                last_name='Supported Factors',
                email='test.mfa.supported@example.com',
                login='test.mfa.supported@example.com',
            )
        )
        assert test_user is not None

        # Test: Retrieve supported factors from catalog
        supported_factors = list(test_user.supported_factors())
        assert supported_factors is not None
        assert len(supported_factors) > 0
        assert supported_factors[0].factor_type == 'token:software:totp'
        assert supported_factors[0].provider == 'GOOGLE'
        assert supported_factors[0].vendor_name == 'GOOGLE'
        assert supported_factors[0].enroll_link == f'{test_user._okta.host}/api/v1/users/{test_user.id}/factors'


def test_enroll_and_remove_google_otp(okta_cassette, okta_service, test_user_cleaner):
    """Test enrolling a Google OTP factor and then removing it."""
    with okta_cassette():
        # Create a test user
        test_user = test_user_cleaner(
            okta_service.create_user(
                first_name='Test',
                last_name='Google OTP',
                email='test.mfa.google@example.com',
                login='test.mfa.google@example.com',
            )
        )
        assert test_user is not None

        # Step 1: Enroll a Google OTP factor
        factor = test_user.enroll_factor('token:software:totp', 'GOOGLE', {})

        assert factor is not None, 'Failed to enroll Google OTP factor'
        assert factor.factor_type == 'token:software:totp'
        assert factor.provider == 'GOOGLE'
        assert factor.status == 'PENDING_ACTIVATION'

        # Step 2: Get the shared secret and generate a TOTP code
        shared_secret = factor.shared_secret
        assert shared_secret, 'Shared secret should not be empty'

        totp = pyotp.TOTP(shared_secret)
        passcode = totp.now()

        # Step 3: Activate the factor
        activation_result = factor.activate(passcode)
        assert activation_result is True, 'Failed to activate Google OTP factor'
        assert factor.status == 'ACTIVE'

        # Step 4: Verify the factor is now in enrolled factors
        enrolled_factors = list(test_user.enrolled_factors())
        factor_ids = [f.id for f in enrolled_factors]
        assert factor.id in factor_ids, 'Factor should be in enrolled factors list'

        # Step 4a: Verify we get the correct subtype from enrolled_factors()
        google_factor = next(f for f in enrolled_factors if f.id == factor.id)
        assert isinstance(google_factor, UserFactorGoogleOTP), (
            'enrolled_factors() should return UserFactorGoogleOTP subtype for Google TOTP'
        )
        # Verify subtype-specific properties are NOT accessible after activation
        # (shared_secret is only available during PENDING_ACTIVATION)
        assert google_factor.shared_secret == '', 'Shared secret should be empty after activation'

        # Step 5: Delete the factor
        deletion_result = factor.delete()
        assert deletion_result is True, 'Failed to delete Google OTP factor'

        # Step 6: Verify the factor is no longer enrolled
        enrolled_factors_after = list(test_user.enrolled_factors())
        factor_ids_after = [f.id for f in enrolled_factors_after]
        assert factor.id not in factor_ids_after, 'Factor should not be in enrolled factors list after deletion'
