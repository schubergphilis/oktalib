"""Tests for Okta user and admin-role functionality."""
# pylint: disable=redefined-outer-name

import json
import os
from datetime import UTC, datetime
from itertools import islice

import pytest
from requests import Response

from oktalib.entities import User, UserAssignment, UserAssignmentTask


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
def task_data():
    """The provisioning task Okta embeds in an app user read with expand=task."""
    return {
        'id': 'aat1wixote4zo2V9n0h8',
        'status': 'PROVISIONING_FAILED',
        'errorString': 'Automatic provisioning of user A Person to app Active Directory failed: '
        'Error provisioning active_directory user: The object already exists.',
        'assignmentType': 'GROUP',
        'groupId': '00g9t98twmjMO6oU10h7',
        'createdDate': '2023-11-08T14:12:13.000Z',
        'lastUpdate': '2024-11-14T10:46:09.000Z',
    }


def test_task_properties(okta_service, task_data):
    """The task exposes the reason the assignment failed, which sync_state cannot."""
    task = UserAssignmentTask(okta_service, task_data)
    assert task.id == 'aat1wixote4zo2V9n0h8'
    assert task.status == 'PROVISIONING_FAILED'
    assert 'The object already exists' in task.error_string
    assert task.assignment_type == 'GROUP'
    assert task.group_id == '00g9t98twmjMO6oU10h7'
    assert task.has_error


def test_task_timestamps_use_their_own_spellings(okta_service, task_data):
    """The task payload uses createdDate and lastUpdate, not created and lastUpdated."""
    task = UserAssignmentTask(okta_service, task_data)
    assert task.created_at == datetime(2023, 11, 8, 14, 12, 13, tzinfo=UTC)
    assert task.last_updated_at == datetime(2024, 11, 14, 10, 46, 9, tzinfo=UTC)


def test_a_completed_task_can_still_carry_an_error(okta_service, task_data):
    """status is not a failure flag: a COMPLETED task was observed with an error.

    Verified against a real org, which is why has_error reads the reason rather
    than the status.
    """
    task = UserAssignmentTask(okta_service, {**task_data, 'status': 'COMPLETED'})
    assert task.status == 'COMPLETED'
    assert task.has_error


def test_a_task_without_an_error(okta_service, task_data):
    """A task recording no failure reports none."""
    data = {**task_data}
    del data['errorString']
    task = UserAssignmentTask(okta_service, data)
    assert task.error_string is None
    assert not task.has_error


def test_assignment_exposes_an_embedded_task(okta_service, assignment_data, task_data):
    """An assignment read with expand=task carries the task."""
    assignment = UserAssignment(okta_service, {**assignment_data, '_embedded': {'task': task_data}})
    assert assignment.task.id == 'aat1wixote4zo2V9n0h8'
    assert assignment.task.has_error


def test_assignment_without_an_expanded_task(assignment):
    """Without the expand there is no task, so the accessor reports None."""
    assert assignment.task is None


def test_assignment_ignores_a_malformed_embedded_task(okta_service, assignment_data):
    """A task that is not an object is ignored rather than blowing up."""
    assignment = UserAssignment(okta_service, {**assignment_data, '_embedded': {'task': 'nonsense'}})
    assert assignment.task is None


@pytest.fixture
def assigned_app_id():
    """An app in the recording org that has users assigned to it.

    Override to re-record against a different org.
    """
    return os.environ.get('OKTALIB_ASSIGNED_APP_ID', '0oapibfoozclBDPRc0h7')


@pytest.fixture
def provisioning_app_id():
    """An app in the recording org with provisioning tasks on its assignments.

    This is the Active Directory integration, whose Provisioning tab is where the
    console shows these tasks. Override to re-record against a different org.
    """
    return os.environ.get('OKTALIB_PROVISIONING_APP_ID', '0oa9h3vbsr7tqyvN50h7')


def test_live_assignments_carry_their_provisioning_task(okta_cassette, okta_service, provisioning_app_id):
    """Real call: expand=task embeds the reason an assignment failed.

    The reason itself is redacted out of the cassette, since it names the affected
    person, so this asserts on the task's shape rather than its text.
    """
    with okta_cassette():
        application = okta_service.get_application_by_id(provisioning_app_id)
        assignments = list(islice(application.user_assignments_with_tasks(), 10))

    assert assignments
    with_tasks = [assignment for assignment in assignments if assignment.task]
    assert with_tasks, 'expected at least one assignment carrying a task'
    for assignment in with_tasks:
        assert assignment.task.id.startswith('aat')
        assert assignment.task.status
        assert assignment.task.assignment_type in {'GROUP', 'USER'}
        assert assignment.task.created_at is not None


def test_live_tasks_attach_only_to_unhealthy_assignments(okta_cassette, okta_service, provisioning_app_id):
    """Real call: a SYNCHRONIZED assignment carries no task, an OUT_OF_SYNC one does.

    This is what makes the presence of a task a usable signal.
    """
    with okta_cassette():
        application = okta_service.get_application_by_id(provisioning_app_id)
        assignments = list(islice(application.user_assignments_with_tasks(), 20))

    by_state = {}
    for assignment in assignments:
        by_state.setdefault(assignment.sync_state, set()).add(bool(assignment.task))
    assert by_state.get('SYNCHRONIZED') == {False}
    assert by_state.get('OUT_OF_SYNC') == {True}


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
