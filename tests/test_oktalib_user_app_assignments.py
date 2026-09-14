"""Tests for listing a user's application assignments in one filtered call."""
# pylint: disable=redefined-outer-name

import json
import os

import pytest
from requests import Response

from oktalib.entities import User
from oktalib.entities.apps import Application, SAMLApplication
from oktalib.entities.users import UserAssignment


@pytest.fixture
def user_id():
    """The id of the user whose assignments the unit tests describe."""
    return '00uuser1'


@pytest.fixture
def user(okta_service, user_id):
    """A User backed by static data, making no requests of its own."""
    return User(okta_service, {'id': user_id, 'profile': {'email': 'someone@example.com'}})


def make_app_user(user_id, **extra):
    """Build the app user Okta embeds under ``_embedded.user``."""
    return {
        'id': user_id,
        'scope': 'GROUP',
        'status': 'ACTIVE',
        'syncState': 'DISABLED',
        'profile': {'email': 'someone@example.com'},
        '_links': {'app': {'href': 'https://example.com/api/v1/apps/0oaapp1'}},
        **extra,
    }


def make_assigned_app(app_id, app_user, **extra):
    """Build one application as the filtered listing returns it, assignment embedded."""
    return {
        'id': app_id,
        'label': f'App {app_id}',
        'signOnMode': 'SAML_2_0',
        '_embedded': {'user': app_user},
        **extra,
    }


def make_json_response(payload):
    """Build an ok Response carrying the provided JSON payload."""
    response = Response()
    response.status_code = 200
    response._content = json.dumps(payload).encode()
    return response


def test_the_filter_and_expand_name_the_same_user(user, user_id, monkeypatch):
    """Okta rejects the expand unless the filter names the same user, so both are sent."""
    requested = {}

    def record(url=None, params=None, **_kwargs):
        requested['url'] = url
        requested['params'] = params
        return make_json_response([])

    monkeypatch.setattr(user._okta.session, 'get', record)
    assert not list(user.app_assignments())
    assert requested['url'] == f'{user._okta.api}/apps'
    assert requested['params']['filter'] == f'user.id eq "{user_id}"'
    assert requested['params']['expand'] == f'user/{user_id}'


def test_assignments_come_from_the_embedded_app_user(user, user_id, monkeypatch):
    """Each application in the listing yields the assignment embedded in it."""
    payload = [
        make_assigned_app('0oaapp1', make_app_user(user_id)),
        make_assigned_app(
            '0oaapp2',
            make_app_user(user_id, scope='USER', status='PROVISIONED', syncState='ERROR'),
        ),
    ]
    monkeypatch.setattr(user._okta.session, 'get', lambda *a, **k: make_json_response(payload))

    assignments = list(user.app_assignments())

    assert [assignment.scope for assignment in assignments] == ['GROUP', 'USER']
    assert [assignment.sync_state for assignment in assignments] == ['DISABLED', 'ERROR']


def test_an_application_without_an_assignment_is_skipped(user, user_id, monkeypatch):
    """An application carrying no embedded app user is not an assignment to report."""
    payload = [
        {'id': '0oaapp1', 'label': 'No embed', 'signOnMode': 'SAML_2_0'},
        make_assigned_app('0oaapp2', make_app_user(user_id)),
    ]
    monkeypatch.setattr(user._okta.session, 'get', lambda *a, **k: make_json_response(payload))

    assert len(list(user.app_assignments())) == 1


def test_the_application_costs_no_request(user, user_id, monkeypatch):
    """The listing already carries the application, so reading it makes no call."""
    payload = [make_assigned_app('0oaapp1', make_app_user(user_id))]
    calls = []

    def record(*_args, **_kwargs):
        calls.append(1)
        return make_json_response(payload)

    monkeypatch.setattr(user._okta.session, 'get', record)
    assignment = next(iter(user.app_assignments()))
    application = assignment.application

    assert len(calls) == 1
    assert isinstance(application, SAMLApplication)
    assert application.id == '0oaapp1'


def test_the_application_is_fetched_when_it_was_not_provided(okta_service, monkeypatch):
    """An assignment from an app user listing follows its own link to the application."""
    assignment = UserAssignment(okta_service, make_app_user('00uuser1'))
    requested = {}

    def record(url=None, **_kwargs):
        requested['url'] = url
        return make_json_response({'id': '0oaapp1', 'label': 'An app', 'signOnMode': 'BOOKMARK'})

    monkeypatch.setattr(okta_service.session, 'get', record)
    application = assignment.application

    assert requested['url'] == 'https://example.com/api/v1/apps/0oaapp1'
    assert isinstance(application, Application)
    assert application.id == '0oaapp1'


def test_an_assignment_with_no_application_link(okta_service):
    """An app user payload without a link to its application reports None."""
    app_user = make_app_user('00uuser1')
    del app_user['_links']
    assert UserAssignment(okta_service, app_user).application is None


@pytest.fixture
def assigned_user_id():
    """A user in the recording org that has application assignments.

    Pinned rather than discovered, because the point of the call is to answer for
    one named user. Override to re-record against a different org.
    """
    return os.environ.get('OKTALIB_ASSIGNED_USER_ID', '00u21yckgdebrSdhy0h8')


def test_live_a_users_assignments_arrive_with_their_applications(
    okta_cassette,
    okta_service,
    assigned_user_id,
):
    """Real call: the filter and expand pairing works despite the spec omitting user.id.

    The ``filter`` parameter's documentation lists neither ``user.id`` nor any
    other app user property, while the ``expand`` documentation requires pairing
    with exactly this filter. This test pins which of the two is right.
    """
    with okta_cassette():
        user = User(okta_service, {'id': assigned_user_id})
        assignments = list(user.app_assignments())

    assert assignments
    for assignment in assignments:
        assert assignment.application is not None
        assert assignment.application.id
        assert assignment.scope in {'USER', 'GROUP'}
        assert assignment.status
        assert assignment.sync_state


def test_live_assignments_carry_no_task(okta_cassette, okta_service, assigned_user_id):
    """Real call: expand cannot also carry task, so no reason for a failure is available.

    Okta answers 400 to a second ``expand``, whether repeated or comma joined, so
    a per-user read reports that an assignment is in ERROR without saying why.
    """
    with okta_cassette():
        user = User(okta_service, {'id': assigned_user_id})
        assignments = list(user.app_assignments())

    assert assignments
    assert all(assignment.task is None for assignment in assignments)
