"""Tests for application group push mapping functionality."""
# pylint: disable=redefined-outer-name

import json
import os
from datetime import datetime

import pytest
from requests import Response

from oktalib.entities import Group, GroupPushMapping
from oktalib.entities.apps import Application


@pytest.fixture
def saml_app_data():
    """The application data a mapping hangs off, fresh per test."""
    return {'id': '0oaapp1', 'label': 'An app', 'signOnMode': 'SAML_2_0'}


@pytest.fixture
def application(okta_service, saml_app_data):
    """An Application backed by static data, making no requests of its own."""
    return Application(okta_service, saml_app_data)


def make_mapping(mapping_id, status='ACTIVE', **extra):
    """Build the payload Okta returns for one group push mapping."""
    return {
        'id': mapping_id,
        'status': status,
        'sourceGroupId': f'00gsrc{mapping_id}',
        'targetGroupId': f'tgt{mapping_id}',
        'lastPush': '2026-07-01T10:00:00.000Z',
        'created': '2026-01-01T00:00:00.000Z',
        **extra,
    }


def make_json_response(payload):
    """Build an ok Response carrying the provided JSON payload."""
    response = Response()
    response.status_code = 200
    response._content = json.dumps(payload).encode()
    return response


def test_mapping_properties(okta_service, saml_app_data):
    """The mapping exposes the fields the group push task is built on."""
    mapping = GroupPushMapping(okta_service, saml_app_data, make_mapping('gpm1', status='ERROR'))
    assert mapping.id == 'gpm1'
    assert mapping.status == 'ERROR'
    assert mapping.source_group_id == '00gsrcgpm1'
    assert mapping.target_group_id == 'tgtgpm1'


def test_error_summary_carries_the_reason(okta_service, saml_app_data):
    """Unlike sync_state, a failed mapping carries its own reason."""
    mapping = GroupPushMapping(
        okta_service,
        saml_app_data,
        make_mapping('gpm1', status='ERROR', errorSummary='Group not found in application'),
    )
    assert mapping.error_summary == 'Group not found in application'


def test_healthy_mapping_has_no_error_summary(okta_service, saml_app_data):
    """An active mapping reports no error summary."""
    assert GroupPushMapping(okta_service, saml_app_data, make_mapping('gpm1')).error_summary is None


def test_last_push_is_parsed(okta_service, saml_app_data):
    """The last push timestamp is exposed as a datetime."""
    mapping = GroupPushMapping(okta_service, saml_app_data, make_mapping('gpm1'))
    assert mapping.last_push.year == 2026
    assert mapping.last_push.month == 7


def test_never_pushed_mapping(okta_service, saml_app_data):
    """A mapping that has never been pushed reports no last push."""
    data = make_mapping('gpm1')
    del data['lastPush']
    assert GroupPushMapping(okta_service, saml_app_data, data).last_push is None


def test_url_is_built_from_the_parent_app(okta_service, saml_app_data):
    """The mapping payload carries no app id, so the url comes from the parent app."""
    mapping = GroupPushMapping(okta_service, saml_app_data, make_mapping('gpm1'))
    assert mapping.url == f'{okta_service.session.api}/apps/0oaapp1/group-push/mappings/gpm1'


def test_source_group_is_resolved(okta_service, saml_app_data, monkeypatch):
    """The source group is resolved by id, on demand."""
    group = Group(okta_service, {'id': '00gsrcgpm1', 'profile': {'name': 'A group'}})
    monkeypatch.setattr(okta_service, 'get_group_by_id', lambda group_id: group if group_id == '00gsrcgpm1' else None)
    mapping = GroupPushMapping(okta_service, saml_app_data, make_mapping('gpm1'))
    assert mapping.source_group.name == 'A group'


def test_source_group_without_an_id(okta_service, saml_app_data, monkeypatch):
    """No source group id means no request is made and None is returned."""

    def fail(_group_id):
        raise AssertionError('should not resolve a group without an id')

    monkeypatch.setattr(okta_service, 'get_group_by_id', fail)
    data = make_mapping('gpm1')
    del data['sourceGroupId']
    assert GroupPushMapping(okta_service, saml_app_data, data).source_group is None


def test_mappings_are_listed(application, monkeypatch):
    """The application yields a mapping per entry the endpoint returns."""
    payload = [make_mapping('gpm1'), make_mapping('gpm2', status='ERROR')]
    monkeypatch.setattr(application._okta.session, 'get', lambda *a, **k: make_json_response(payload))
    assert [mapping.id for mapping in application.group_push_mappings()] == ['gpm1', 'gpm2']


def test_status_is_filtered_server_side(application, monkeypatch):
    """Asking for the failures sends the status to Okta rather than filtering locally."""
    requested = {}

    def record(url=None, params=None, **_kwargs):
        requested['url'] = url
        requested['params'] = params
        return make_json_response([make_mapping('gpm2', status='ERROR')])

    monkeypatch.setattr(application._okta.session, 'get', record)
    assert [mapping.id for mapping in application.group_push_mappings(status='ERROR')] == ['gpm2']
    assert requested['url'] == '/apps/0oaapp1/group-push/mappings'
    assert requested['params']['status'] == 'ERROR'


def test_omitted_status_sends_no_filter(application, monkeypatch):
    """Without a status, no status parameter is sent at all."""
    requested = {}

    def record(params=None, **_kwargs):
        requested['params'] = params
        return make_json_response([])

    monkeypatch.setattr(application._okta.session, 'get', record)
    assert not list(application.group_push_mappings())
    assert 'status' not in requested['params']


def test_expand_task_is_requested(application, monkeypatch):
    """The task expansion is sent, since the plain listing carries no task."""
    requested = {}

    def record(params=None, **_kwargs):
        requested['params'] = params
        return make_json_response([])

    monkeypatch.setattr(application._okta.session, 'get', record)
    application._data['_links'] = {'users': {'href': f'{application._okta.session.api}/apps/0oaapp1/users'}}
    assert not list(application.user_assignments_with_tasks())
    assert requested['params']['expand'] == 'task'


@pytest.fixture
def group_push_app_id():
    """The app in the recording org that has group push configured.

    Group push has to be set up per app, and there is no way to find such an app
    without asking every app in turn, so the recording is pinned to a known one.
    Override to re-record against a different org.
    """
    return os.environ.get('OKTALIB_GROUP_PUSH_APP_ID', '0oa2bp8qwxuTtJbNy0h8')


def test_live_mappings_are_listed(okta_cassette, okta_service, group_push_app_id):
    """Real call: an app with group push configured returns its mappings."""
    with okta_cassette():
        application = okta_service.get_application_by_id(group_push_app_id)
        mappings = list(application.group_push_mappings())

    assert mappings
    for mapping in mappings:
        assert mapping.id
        assert mapping.status in {'ACTIVE', 'ERROR', 'INACTIVE'}
        assert mapping.source_group_id
        assert mapping.target_group_id
        assert mapping.last_push is None or isinstance(mapping.last_push, datetime)


def test_live_status_filter_returns_only_failures(okta_cassette, okta_service, group_push_app_id):
    """Real call: Okta honours the status filter, so only failures come back."""
    with okta_cassette():
        application = okta_service.get_application_by_id(group_push_app_id)
        errored = list(application.group_push_mappings(status='ERROR'))

    assert errored
    assert {mapping.status for mapping in errored} == {'ERROR'}


def test_live_failing_mapping_carries_no_reason(okta_cassette, okta_service, group_push_app_id):
    """Real call: Okta omits errorSummary even on a mapping that has failed.

    The field is in the API spec, which is why the property exists, but a real
    ERROR mapping does not populate it. This test pins that finding so nobody
    builds on a reason that is not there.
    """
    with okta_cassette():
        application = okta_service.get_application_by_id(group_push_app_id)
        errored = list(application.group_push_mappings(status='ERROR'))

    assert errored
    assert all(mapping.error_summary is None for mapping in errored)
