"""Tests for Okta group functionality."""
# pylint: disable=redefined-outer-name

import pytest


@pytest.mark.parametrize(
    ('call', 'expected'),
    [
        pytest.param(lambda okta: okta.create_group('name', 'desc'), None, id='create_group'),
        pytest.param(lambda okta: okta.get_group_by_id('grp'), None, id='get_group_by_id'),
        pytest.param(
            lambda okta: okta.search_groups_by_name('name'), [], id='search_groups_by_name'
        ),
        pytest.param(
            lambda okta: okta.search_groups_by_query('name'), [], id='search_groups_by_query'
        ),
    ],
)
def test_group_methods_handle_non_json_error(okta_with_error, call, expected):
    """Group methods return their error value on a non-JSON error body, not raise."""
    assert call(okta_with_error) == expected
