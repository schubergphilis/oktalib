"""Tests for Application Federated Claims functionality."""

import pytest
from betamax import Betamax


@pytest.fixture(scope='module')
def test_app(okta_service, okta_recorder):  # pylint: disable=unused-argument
    """Module-scoped fixture that provides a test application.

    Uses okta_recorder instead of okta_cassette since module-scoped
    fixtures can't use function-scoped fixtures.
    """

    with Betamax(okta_service.session).use_cassette('federated_claims_test_app'):
        app = okta_service.get_application_by_label('test_app')
        assert app is not None, "Test application 'test_app' not found"
        assert app.label == 'test_app'
        yield app


def test_get_app(test_app):  # pylint: disable=redefined-outer-name
    """Test that we can retrieve the test application."""
    assert test_app.label == 'test_app'
    assert test_app.id is not None


def test_create_federated_claim(okta_cassette, test_app):  # pylint: disable=redefined-outer-name
    """Test creating a federated claim."""
    with okta_cassette():
        created_claim = test_app.create_federated_claim(name='test_amr', expression='session.amr')

        assert created_claim is not None, 'Failed to create federated claim'
        assert created_claim.id, 'Created claim has no ID'
        assert created_claim.name == 'test_amr'
        assert created_claim.expression == 'session.amr'
        assert created_claim.created is not None
        assert created_claim.last_updated is not None

        # Cleanup
        assert created_claim.delete(), 'Failed to delete test claim'


def test_get_federated_claim_by_name(okta_cassette, test_app):  # pylint: disable=redefined-outer-name
    """Test retrieving a federated claim by name."""
    with okta_cassette():
        # Create a claim first using valid appuser property
        created = test_app.create_federated_claim(
            name='test_lookup', expression='user.profile.email'
        )
        assert created is not None, 'Failed to create claim'

        # Retrieve it by name
        claim = test_app.get_federated_claim_by_name('test_lookup')
        assert claim is not None, 'Could not find claim by name'
        assert claim.name == 'test_lookup'
        assert claim.expression == 'user.profile.email'

        # Cleanup
        created.delete()


def test_list_federated_claims(okta_cassette, test_app):  # pylint: disable=redefined-outer-name
    """Test listing all federated claims for an application."""
    with okta_cassette():
        # Create a test claim
        created = test_app.create_federated_claim(name='test_list', expression='user.profile.email')

        # List all claims
        claims = list(test_app.federated_claims())
        assert len(claims) > 0, 'No claims found'
        assert any(c.name == 'test_list' for c in claims), 'Created claim not in list'

        # Cleanup
        created.delete()


def test_replace_federated_claim(okta_cassette, test_app):  # pylint: disable=redefined-outer-name
    """Test replacing/updating a federated claim."""
    with okta_cassette():
        # Create a claim
        created = test_app.create_federated_claim(
            name='test_replace', expression='user.profile.firstName'
        )
        assert created is not None, 'Failed to create claim'

        # Replace it
        success = test_app.replace_federated_claim(
            claim_id=created.id, name='test_replace_updated', expression='user.profile.lastName'
        )
        assert success, 'Failed to replace federated claim'

        # Verify the update
        updated = test_app.get_federated_claim_by_name('test_replace_updated')
        assert updated is not None, 'Could not find updated claim'
        assert updated.expression == 'user.profile.lastName'

        # Cleanup
        updated.delete()


def test_delete_federated_claim(okta_cassette, test_app):  # pylint: disable=redefined-outer-name
    """Test deleting a federated claim."""
    with okta_cassette():
        # Create a claim
        created = test_app.create_federated_claim(
            name='test_delete', expression='user.profile.login'
        )
        assert created is not None, 'Failed to create claim'

        # Delete it
        success = created.delete()
        assert success, 'Failed to delete federated claim'

        # Verify it's gone
        deleted_claim = test_app.get_federated_claim_by_name('test_delete')
        assert deleted_claim is None, 'Claim still exists after deletion'


def test_get_nonexistent_claim(okta_cassette, test_app):  # pylint: disable=redefined-outer-name
    """Test that getting a non-existent claim returns None."""
    with okta_cassette():
        claim = test_app.get_federated_claim_by_name('nonexistent_claim_12345')
        assert claim is None, 'Expected None for non-existent claim'


def test_create_claim_with_empty_name(okta_cassette, test_app):  # pylint: disable=redefined-outer-name
    """Test that creating a claim with empty name fails gracefully."""
    with okta_cassette():
        created = test_app.create_federated_claim(name='', expression='appuser.username')
        # Depending on API behavior, this might return None or raise an error
        # Adjust assertion based on actual behavior
        assert created is None, 'Should not create claim with empty name'
