"""Tests for Okta feature-flag functionality."""
# pylint: disable=redefined-outer-name

import pytest
from requests import Response

from oktalib.entities import Feature

FEATURE_NAME = 'Authentication Activity report'
# 'Authentication Activity report' has no dependencies/dependents, so a feature
# that does is used to exercise those relationships.
DEPENDENT_FEATURE = 'Front-channel Single Logout for IdPs'
DEPENDENCY_FEATURE = 'Front-channel Single Logout'


def test_get_feature_by_name_and_id(okta_cassette, okta_service):
    """Look up a known org feature by name, then round-trip it by id."""
    with okta_cassette():
        feature = okta_service.get_feature_by_name(FEATURE_NAME)
        assert feature is not None, f'Feature {FEATURE_NAME!r} not found'
        assert feature.name == FEATURE_NAME
        assert feature.id
        assert feature.type == 'self-service'
        assert feature.status in ('ENABLED', 'DISABLED')
        assert isinstance(feature.stage, dict)
        assert feature.stage_value == 'EA'

        # the same feature is retrievable by its id
        same = okta_service.get_feature_by_id(feature.id)
        assert same is not None
        assert same.id == feature.id
        assert same.name == feature.name


def test_enable_and_disable_feature(okta_cassette, okta_service):
    """Enable then disable a feature, restoring its original state on exit."""
    with okta_cassette():
        feature = okta_service.get_feature_by_name(FEATURE_NAME)
        assert feature is not None
        original = feature.status
        try:
            assert feature.update_feature('enable', force=False) is True
            assert feature.status == 'ENABLED'

            assert feature.update_feature('disable', force=False) is True
            assert feature.status == 'DISABLED'
        finally:
            if feature.status != original:
                lifecycle = 'enable' if original == 'ENABLED' else 'disable'
                feature.update_feature(lifecycle, force=False)


def test_feature_dependencies_and_dependents(okta_cassette, okta_service):
    """A feature's dependency lists it back as a dependent (both directions)."""
    with okta_cassette():
        feature = okta_service.get_feature_by_name(DEPENDENT_FEATURE)
        assert feature is not None

        dependencies = list(feature.dependencies())
        assert DEPENDENCY_FEATURE in [d.name for d in dependencies]

        # inverse relationship: the dependency lists our feature as a dependent
        dependency = next(d for d in dependencies if d.name == DEPENDENCY_FEATURE)
        assert DEPENDENT_FEATURE in [d.name for d in dependency.dependents()]


def test_update_feature_rejects_invalid_lifecycle(okta_service):
    """An invalid lifecycle fails fast with ValueError before any request."""
    feature = Feature(okta_service, {'id': 'ftr_x'})
    with pytest.raises(ValueError, match='enable'):
        feature.update_feature('activate', force=False)


def test_get_feature_by_id_survives_non_json_error(okta_service, monkeypatch):
    """A non-JSON error body (e.g. an HTML 502) yields None, not a JSONDecodeError."""
    error = Response()
    error.status_code = 502
    error._content = b'<html>502 Bad Gateway</html>'
    monkeypatch.setattr(okta_service.session, 'get', lambda *a, **k: error)
    assert okta_service.get_feature_by_id('bogus') is None
