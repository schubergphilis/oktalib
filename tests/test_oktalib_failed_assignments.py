"""Tests for the assignments behind the admin console's task categories."""
# pylint: disable=redefined-outer-name

import json
import os

import pytest
from requests import Response

from oktalib.entities.apps import Application
from oktalib.entities.users import UserAssignmentTask

PROVISIONING_FAILED = 'PROVISIONING_FAILED'
PROFILE_PUSH_FAILED = 'PROFILE_PUSH_FAILED'


@pytest.fixture
def application(okta_service):
    """An Application whose user listing link is set, making no requests of its own."""
    return Application(
        okta_service,
        {
            'id': '0oaapp1',
            'label': 'An app',
            'signOnMode': 'SAML_2_0',
            '_links': {'users': {'href': f'{okta_service.api}/apps/0oaapp1/users'}},
        },
    )


def make_assignment(sync_state='SYNCHRONIZED', task=None):
    """Build one app user, optionally with a task embedded as expand=task returns it."""
    data = {
        'id': '00uuser1',
        'scope': 'USER',
        'status': 'PROVISIONED',
        'syncState': sync_state,
        'profile': {'email': 'someone@example.com'},
    }
    if task is not None:
        data['_embedded'] = {'task': task}
    return data


def make_task(status, error_string='Automatic provisioning of user X to app Y failed: nope'):
    """Build the task payload Okta embeds in a failing assignment."""
    return {
        'id': 'aat1',
        'status': status,
        'errorString': error_string,
        'assignmentType': 'SINGLE',
        'createdDate': '2026-03-25 08:28:23.0',
    }


def make_json_response(payload):
    """Build an ok Response carrying the provided JSON payload."""
    response = Response()
    response.status_code = 200
    response._content = json.dumps(payload).encode()
    return response


def test_a_completed_task_has_not_failed(okta_service):
    """The console counts by status, and COMPLETED is not outstanding."""
    task = UserAssignmentTask(okta_service, make_task('COMPLETED'))
    assert task.has_error is True
    assert task.has_failed is False


def test_a_task_without_a_status_has_not_failed(okta_service):
    """A payload with no status is not evidence of a failure."""
    assert UserAssignmentTask(okta_service, {'id': 'aat1'}).has_failed is False


@pytest.mark.parametrize('status', [PROVISIONING_FAILED, PROFILE_PUSH_FAILED, 'VALIDATION_FAILED'])
def test_every_failure_status_counts_as_failed(okta_service, status):
    """Every failure status is outstanding, not just the two the console names."""
    assert UserAssignmentTask(okta_service, make_task(status)).has_failed is True


def test_completed_tasks_are_not_returned(application, monkeypatch):
    """A COMPLETED task keeps its reason, so filtering on the reason would over-report."""
    payload = [
        make_assignment(task=make_task('COMPLETED')),
        make_assignment(task=make_task(PROVISIONING_FAILED)),
    ]
    monkeypatch.setattr(application._okta.session, 'get', lambda *a, **k: make_json_response(payload))

    failing = list(application.failed_user_assignments())

    assert len(failing) == 1
    assert failing[0].task.status == PROVISIONING_FAILED


def test_assignments_without_a_task_are_not_returned(application, monkeypatch):
    """Okta attaches a task to the failing assignments only."""
    payload = [make_assignment(), make_assignment(task=make_task(PROFILE_PUSH_FAILED))]
    monkeypatch.setattr(application._okta.session, 'get', lambda *a, **k: make_json_response(payload))

    assert len(list(application.failed_user_assignments())) == 1


def test_the_status_selects_one_console_category(application, monkeypatch):
    """Each console category is one task status, so the filter reproduces one list."""
    payload = [
        make_assignment(task=make_task(PROVISIONING_FAILED)),
        make_assignment(task=make_task(PROFILE_PUSH_FAILED)),
        make_assignment(task=make_task(PROFILE_PUSH_FAILED)),
    ]
    monkeypatch.setattr(application._okta.session, 'get', lambda *a, **k: make_json_response(payload))

    assert len(list(application.failed_user_assignments(task_status=PROFILE_PUSH_FAILED))) == 2
    assert len(list(application.failed_user_assignments(task_status=PROVISIONING_FAILED))) == 1
    assert len(list(application.failed_user_assignments())) == 3


def test_sync_state_does_not_select_the_category(application, monkeypatch):
    """Both categories can share a sync state, so only the task separates them."""
    payload = [
        make_assignment(sync_state='ERROR', task=make_task(PROVISIONING_FAILED)),
        make_assignment(sync_state='ERROR', task=make_task(PROFILE_PUSH_FAILED)),
        make_assignment(sync_state='OUT_OF_SYNC', task=make_task(PROVISIONING_FAILED)),
    ]
    monkeypatch.setattr(application._okta.session, 'get', lambda *a, **k: make_json_response(payload))

    provisioning = list(application.failed_user_assignments(task_status=PROVISIONING_FAILED))

    assert {assignment.sync_state for assignment in provisioning} == {'ERROR', 'OUT_OF_SYNC'}


def test_the_reason_is_the_console_sentence(application, monkeypatch):
    """The failing assignment carries the text the console shows, unchanged."""
    reason = (
        'Automatic provisioning of user A Name to app Okta Org2Org failed: Error while '
        'trying to push profile update for someone@example.com: Operation failed because '
        'user profile is mastered under another system'
    )
    payload = [make_assignment(task=make_task(PROVISIONING_FAILED, error_string=reason))]
    monkeypatch.setattr(application._okta.session, 'get', lambda *a, **k: make_json_response(payload))

    assert next(iter(application.failed_user_assignments())).task.error_string == reason


def test_an_unknown_status_matches_nothing(application, monkeypatch):
    """An unrecognised status is filtered client side, so it simply returns nothing."""
    payload = [make_assignment(task=make_task(PROVISIONING_FAILED))]
    monkeypatch.setattr(application._okta.session, 'get', lambda *a, **k: make_json_response(payload))

    assert not list(application.failed_user_assignments(task_status='NOT_A_STATUS'))


@pytest.fixture
def failing_app_id():
    """A small app in the recording org that has a failing task.

    Pinned rather than discovered: finding one means scanning every app, which is
    the cost this method exists to let callers pay deliberately. Override to
    re-record against a different org.
    """
    return os.environ.get('OKTALIB_FAILING_APP_ID', '0oa2bp8qwxuTtJbNy0h8')


def test_live_failing_assignments_carry_a_reason(okta_cassette, okta_service, failing_app_id):
    """Real call: a failing assignment reports a status and a reason.

    Only the presence of the reason is asserted, not its text: ``errorString`` is
    free-form operator-facing text that names the affected person, so the
    sanitizer replaces it before the cassette is written.
    """
    with okta_cassette():
        application = okta_service.get_application_by_id(failing_app_id)
        failing = list(application.failed_user_assignments())

    assert failing
    for assignment in failing:
        assert assignment.task.has_failed
        assert assignment.task.error_string


def test_live_healthy_assignments_are_left_out(okta_cassette, okta_service, failing_app_id):
    """Real call: the app has assignments the console does not list as tasks."""
    with okta_cassette():
        application = okta_service.get_application_by_id(failing_app_id)
        everything = list(application.user_assignments_with_tasks())
        failing = list(application.failed_user_assignments())

    assert 0 < len(failing) < len(everything)


def test_an_in_flight_task_has_not_failed(okta_service):
    """A task Okta is still working is not an outstanding failure."""
    assert UserAssignmentTask(okta_service, make_task('PROVISIONING')).has_failed is False


def test_an_unknown_status_counts_as_failed(okta_service):
    """An unrecognised status surfaces rather than being silently dropped."""
    assert UserAssignmentTask(okta_service, make_task('SOME_NEW_STATUS')).has_failed is True


def test_in_flight_assignments_are_not_returned(application, monkeypatch):
    """Re-driving an assignment already being provisioned would duplicate work."""
    payload = [
        make_assignment(task=make_task('PROVISIONING')),
        make_assignment(task=make_task(PROVISIONING_FAILED)),
    ]
    monkeypatch.setattr(application._okta.session, 'get', lambda *a, **k: make_json_response(payload))

    failing = list(application.failed_user_assignments())

    assert len(failing) == 1
    assert failing[0].task.status == PROVISIONING_FAILED
