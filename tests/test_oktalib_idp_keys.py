"""Tests for Identity Provider signing keys functionality."""
# pylint: disable=redefined-outer-name


def test_get_idp_keys(okta_cassette, okta_service):
    """Test retrieving all IDP signing keys."""
    with okta_cassette():
        keys = list(okta_service.get_idp_keys())
        assert keys is not None
        assert len(keys) > 0
        # Verify key has expected properties
        assert keys[0].kid is not None
        assert keys[0].kty in ('RSA', 'EC')
