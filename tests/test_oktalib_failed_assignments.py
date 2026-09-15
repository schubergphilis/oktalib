"""Tests for the assignments behind the admin console's task categories."""
# pylint: disable=redefined-outer-name

import json
import os

import pytest
from requests import Response

from oktalib.entities.apps import Application
from oktalib.entities.users import UserAssignment, UserAssignmentTask
from oktalib.oktalibexceptions import InvalidTaskStatus

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
            '_links': {'users': {'href': f'{okta_service.session.api}/apps/0oaapp1/users'}},
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


@pytest.mark.parametrize(
    'task',
    [
        pytest.param({}, id='empty task object'),
        pytest.param({'id': 'aat1'}, id='no status key'),
        pytest.param({'id': 'aat1', 'status': None}, id='null status'),
        pytest.param({'id': 'aat1', 'errorString': 'something went wrong'}, id='a reason but no status'),
    ],
)
def test_a_task_with_no_usable_status_raises(okta_service, task):
    """A task that says nothing is not evidence that the assignment is healthy.

    Reporting False here would hide a failure behind a payload nobody can read,
    which is the same silent under-reporting an unknown status would cause.
    """
    with pytest.raises(InvalidTaskStatus):
        _ = UserAssignmentTask(okta_service, task).has_failed


def test_an_assignment_with_no_task_at_all_is_still_healthy(okta_service):
    """The ordinary case is untouched: no task means nothing is wrong."""
    assert UserAssignment(okta_service, make_assignment()).has_failed_task() is False


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


def test_a_task_that_is_not_an_object_is_refused(okta_service):
    """A string where a task should be is not a task, and not a healthy assignment."""
    payload = {'id': '00u1', '_embedded': {'task': 'not-an-object'}}
    with pytest.raises(InvalidTaskStatus):
        _ = UserAssignment(okta_service, payload).task


def test_an_unknown_status_from_okta_raises(okta_service):
    """A status Okta added or renamed is refused, not folded into a bucket.

    Either guess is wrong in a way nobody would notice: counting it as a failure
    inflates every total, counting it as healthy hides a real one.
    """
    assignment = UserAssignment(okta_service, make_assignment(task=make_task('SOMETHING_NEW')))
    with pytest.raises(InvalidTaskStatus, match='SOMETHING_NEW'):
        assignment.has_failed_task()


def test_filtering_on_an_unknown_status_raises(okta_service):
    """A typo'd filter is refused rather than quietly reporting nothing."""
    assignment = UserAssignment(okta_service, make_assignment(task=make_task(PROVISIONING_FAILED)))
    with pytest.raises(InvalidTaskStatus, match='NOT_A_STATUS'):
        assignment.has_failed_task('NOT_A_STATUS')


def test_the_error_names_the_statuses_it_would_accept(okta_service):
    """Whoever hits this needs to know what to write instead, or what to add."""
    assignment = UserAssignment(okta_service, make_assignment(task=make_task(PROVISIONING_FAILED)))
    with pytest.raises(InvalidTaskStatus) as raised:
        assignment.has_failed_task('NOT_A_STATUS')

    assert PROVISIONING_FAILED in str(raised.value)
    assert PROFILE_PUSH_FAILED in str(raised.value)


def test_a_scan_raises_rather_than_returning_a_partial_list(application, monkeypatch):
    """An unknown status stops the scan, so no caller reads a short list as complete."""
    payload = [make_assignment(task=make_task(PROVISIONING_FAILED)), make_assignment(task=make_task('SOMETHING_NEW'))]
    monkeypatch.setattr(application._okta.session, 'get', lambda *a, **k: make_json_response(payload))

    with pytest.raises(InvalidTaskStatus):
        list(application.failed_user_assignments())
