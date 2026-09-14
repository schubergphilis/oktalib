"""Tests for the assignments behind the admin console's task categories."""
# pylint: disable=redefined-outer-name

import json
import logging
import os

import pytest
from requests import Response

from oktalib.entities.apps import Application
from oktalib.entities.users import UserAssignment, UserAssignmentTask

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


def test_an_unknown_status_matches_nothing_but_says_so(application, monkeypatch, caplog):
    """A typo still matches nothing, but no longer passes for "no failures".

    Returning an empty list quietly is the dangerous outcome: it reads as a clean
    app. The filter is not rejected, because Okta may add a status this library has
    not seen, so the caller is warned rather than blocked.
    """
    payload = [make_assignment(task=make_task(PROVISIONING_FAILED))]
    monkeypatch.setattr(application._okta.session, 'get', lambda *a, **k: make_json_response(payload))

    with caplog.at_level(logging.WARNING):
        assert not list(application.failed_user_assignments(task_status='NOT_A_STATUS'))

    assert any('unrecognised task status' in record.message.lower() for record in caplog.records)


def test_an_unknown_status_from_okta_is_still_treated_as_a_failure(okta_service, caplog):
    """A status Okta added is counted as outstanding, and reported once.

    Under-reporting is the dangerous direction, so an unrecognised status counts as a
    failure. The warning is what makes a benign new status noticeable rather than
    silently inflating every count.
    """
    assignment = UserAssignment(okta_service, make_assignment(task=make_task('SOMETHING_NEW')))
    with caplog.at_level(logging.WARNING):
        assert assignment.has_failed_task() is True

    assert any('treating as a failure' in record.message for record in caplog.records)


def test_an_unknown_status_is_reported_only_once(okta_service, caplog):
    """A renamed status must not log once per assignment on a large app."""
    with caplog.at_level(logging.WARNING):
        for _ in range(5):
            UserAssignment(okta_service, make_assignment(task=make_task('SEEN_REPEATEDLY'))).has_failed_task()

    warnings = [r for r in caplog.records if 'SEEN_REPEATEDLY' in r.getMessage()]
    assert len(warnings) == 1


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


def test_has_failed_task_is_false_without_a_task(okta_service):
    """An assignment Okta attached no task to is healthy, not failing."""
    assert UserAssignment(okta_service, make_assignment()).has_failed_task() is False


def test_has_failed_task_is_false_for_a_completed_task(okta_service):
    """A COMPLETED task keeps its reason, so the reason cannot be the test."""
    assignment = UserAssignment(okta_service, make_assignment(task=make_task('COMPLETED')))
    assert assignment.task.has_error is True
    assert assignment.has_failed_task() is False


def test_has_failed_task_is_false_while_still_provisioning(okta_service):
    """A task Okta is still working is not an outstanding failure."""
    assignment = UserAssignment(okta_service, make_assignment(task=make_task('PROVISIONING')))
    assert assignment.has_failed_task() is False


@pytest.mark.parametrize('status', [PROVISIONING_FAILED, PROFILE_PUSH_FAILED, 'VALIDATION_FAILED'])
def test_has_failed_task_accepts_any_failure_without_a_status(okta_service, status):
    """Omitting the status accepts every failure category."""
    assert UserAssignment(okta_service, make_assignment(task=make_task(status))).has_failed_task() is True


def test_has_failed_task_matches_one_status(okta_service):
    """Naming a status selects a single console category."""
    assignment = UserAssignment(okta_service, make_assignment(task=make_task(PROFILE_PUSH_FAILED)))
    assert assignment.has_failed_task(PROFILE_PUSH_FAILED) is True
    assert assignment.has_failed_task(PROVISIONING_FAILED) is False


@pytest.mark.parametrize(
    ('payload', 'reason'),
    [
        ({'id': '00u1'}, 'no _embedded at all'),
        ({'id': '00u1', '_embedded': None}, 'Okta sent an explicit null'),
        ({'id': '00u1', '_embedded': {}}, 'nothing embedded'),
        ({'id': '00u1', '_embedded': {'task': None}}, 'task is null'),
    ],
)
def test_task_is_none_when_nothing_is_embedded(okta_service, payload, reason):
    """A missing or null task means a healthy assignment, and must never raise.

    The null cases matter because a ``get`` default only applies to an absent key;
    a key present with a null value returns that null, and chaining onto it raises.
    """
    assert UserAssignment(okta_service, payload).task is None, reason


def test_a_malformed_task_is_logged_rather_than_silently_dropped(okta_service, caplog):
    """A task that is not an object is discarded, but said out loud first.

    Discarding it quietly would make a broken payload indistinguishable from a
    healthy assignment, so a failure would vanish from failed_user_assignments
    with nothing in the log to explain it.
    """
    payload = {'id': '00u1', '_embedded': {'task': 'not-an-object'}}
    with caplog.at_level(logging.ERROR):
        task = UserAssignment(okta_service, payload).task

    assert task is None
    assert any('Malformed task' in record.message for record in caplog.records)
