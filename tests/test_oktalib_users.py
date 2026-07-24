"""Tests for Okta user and admin-role functionality."""
# pylint: disable=redefined-outer-name

import pytest


@pytest.mark.parametrize(
    ('call', 'expected'),
    [
        pytest.param(
            lambda okta: okta.create_user('f', 'l', 'e@example.com', 'e@example.com'),
            None,
            id='create_user',
        ),
        pytest.param(
            lambda okta: okta.get_user_by_login('e@example.com'), None, id='get_user_by_login'
        ),
        pytest.param(lambda okta: okta.search_users('value'), [], id='search_users'),
        pytest.param(
            lambda okta: okta.search_users_by_email('e@example.com'), [], id='search_users_by_email'
        ),
        pytest.param(
            lambda okta: okta.get_user_assigned_roles_by_id('usr'),
            None,
            id='get_user_assigned_roles_by_id',
        ),
        pytest.param(
            lambda okta: okta.assign_role_to_user_by_id('usr', 'SUPER_ADMIN'),
            None,
            id='assign_role_to_user_by_id',
        ),
        pytest.param(
            lambda okta: okta.remove_role_from_user_by_id('usr', 'role'),
            False,
            id='remove_role_from_user_by_id',
        ),
    ],
)
def test_user_methods_handle_non_json_error(okta_with_error, call, expected):
    """User/role methods return their error value on a non-JSON error body, not raise."""
    assert call(okta_with_error) == expected
