"""Tests for Okta user and admin-role functionality."""
# pylint: disable=redefined-outer-name

import json
import os
from datetime import datetime
from itertools import islice

import pytest
from requests import Response

from oktalib.entities import User, UserAssignment


@pytest.mark.parametrize(
    ('call', 'expected'),
    [
        pytest.param(
            lambda okta: okta.create_user('f', 'l', 'e@example.com', 'e@example.com'),
            None,
            id='create_user',
        ),
        pytest.param(lambda okta: okta.get_user_by_login('e@example.com'), None, id='get_user_by_login'),
        pytest.param(lambda okta: okta.search_users('value'), [], id='search_users'),
        pytest.param(lambda okta: okta.search_users_by_email('e@example.com'), [], id='search_users_by_email'),
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


@pytest.fixture
def assignment_data():
    """The app user data Okta returns for one application assignment."""
    return {
        'id': '0uauser1',
        'status': 'PROVISIONED',
        'syncState': 'ERROR',
        'scope': 'USER',
        'lastSync': '2026-07-10T07:37:22.000Z',
        'profile': {'email': 'e@example.com'},
        '_links': {'self': {'href': 'https://example.com/api/v1/apps/0oaapp1/users/0uauser1'}},
    }


@pytest.fixture
def assignment(okta_service, assignment_data):
    """A user assignment backed by static data, making no requests of its own."""
    return UserAssignment(okta_service, assignment_data)


def test_assignment_provisioning_fields(assignment):
    """The assignment exposes the app user fields the provisioning tasks are built on."""
    assert assignment.status == 'PROVISIONED'
    assert assignment.sync_state == 'ERROR'
    assert assignment.scope == 'USER'
    assert assignment.last_sync.year == 2026


def test_assignment_fields_absent(okta_service):
    """An assignment payload without these fields reports None rather than failing."""
    assignment = UserAssignment(okta_service, {'id': '0uauser1'})
    assert assignment.status is None
    assert assignment.sync_state is None
    assert assignment.scope is None
    assert assignment.last_sync is None


def test_assignment_status_is_not_the_user_status(assignment):
    """The assignment status is the app user's, distinct from the Okta user's own."""
    assert assignment.status == 'PROVISIONED'
    assert User(assignment._okta, {'status': 'ACTIVE'}).status == 'ACTIVE'


def test_assignment_fields_follow_a_refresh(assignment, monkeypatch):
    """After a refresh the fields report the new data, not the data built from.

    The assignment keeps its live payload separate from the entity data it was
    constructed with, so reading a stale value here would be a real bug.
    """
    refreshed = {'id': '0uauser1', 'syncState': 'SYNCHRONIZED', 'lastSync': '2026-08-01T00:00:00.000Z'}
    response = Response()
    response.status_code = 200
    response._content = json.dumps(refreshed).encode()
    monkeypatch.setattr(assignment._okta.session, 'get', lambda *a, **k: response)

    assert assignment._update()
    assert assignment.sync_state == 'SYNCHRONIZED'
    assert assignment.last_sync.month == 8


@pytest.fixture
def assigned_app_id():
    """An app in the recording org that has users assigned to it.

    Override to re-record against a different org.
    """
    return os.environ.get('OKTALIB_ASSIGNED_APP_ID', '0oapibfoozclBDPRc0h7')


def test_live_assignment_provisioning_fields(okta_cassette, okta_service, assigned_app_id):
    """Real call: the app user fields the provisioning tasks are built on.

    ``last_sync`` is absent from the assignments of the recording org, so this
    asserts only that it parses when present rather than that it has a value.
    """
    with okta_cassette():
        application = okta_service.get_application_by_id(assigned_app_id)
        assignments = list(islice(application.user_assignments, 3))

    assert assignments
    for assignment in assignments:
        assert assignment.status
        assert assignment.sync_state
        assert assignment.scope in {'USER', 'GROUP'}
        assert assignment.last_sync is None or isinstance(assignment.last_sync, datetime)
