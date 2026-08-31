"""Tests for Directory Integrations agent pool functionality.

The payload factories here mirror what an AD agent pool actually returns, which
differs from the API spec in two ways worth knowing: ``lastConnection`` is
milliseconds since the epoch rather than an ISO 8601 string, and the documented
``updateStatus``/``updateMessage`` fields are simply absent.
"""
# pylint: disable=redefined-outer-name

import json
from datetime import UTC, datetime

import pytest
from requests import Response

from oktalib.entities import DirectoryIntegrationsAgent, DirectoryIntegrationsAgentPool


def make_agent(agent_id, operational_status='OPERATIONAL', **extra):
    """Build the payload Okta embeds for one agent of a pool.

    ``lastConnection`` is milliseconds since the epoch, copied from a real agent;
    1783348010000 is 2026-07-06T14:26:50Z.
    """
    data = {
        'id': agent_id,
        'name': f'AGENT-{agent_id}',
        'type': 'AD',
        'poolId': 'poolid1',
        'lastConnection': 1783348010000,
        'version': '3.22.0',
        'isLatestGAedVersion': False,
        'isHidden': False,
        **extra,
    }
    if operational_status is not None:
        data['operationalStatus'] = operational_status
    return data


def make_pool(pool_id='poolid1', operational_status='OPERATIONAL', agents=None, **extra):
    """Build the payload Okta returns for one agent pool.

    The three agent counts default to describing the single operational agent in
    the default pool, so they reconcile with the embedded list.
    """
    return {
        'id': pool_id,
        'name': 'An AD pool',
        'type': 'AD',
        'operationalStatus': operational_status,
        'disruptedAgents': 0,
        'inactiveAgents': 0,
        'operationalAgents': 1,
        'agents': agents if agents is not None else [make_agent('one')],
        **extra,
    }


def make_json_response(payload):
    """Build an ok Response carrying the provided JSON payload."""
    response = Response()
    response.status_code = 200
    response._content = json.dumps(payload).encode()
    return response


@pytest.fixture
def pool_data():
    """The agent pool data as Okta returns it, fresh per test."""
    return make_pool()


@pytest.fixture
def pool(okta_service, pool_data):
    """A pool backed by static data, making no requests of its own."""
    return DirectoryIntegrationsAgentPool(okta_service, pool_data)


def test_pool_properties(pool):
    """The pool exposes the fields the console's Directory Integrations page shows."""
    assert pool.id == 'poolid1'
    assert pool.name == 'An AD pool'
    assert pool.type == 'AD'
    assert pool.operational_status == 'OPERATIONAL'
    assert pool.disrupted_agents == 0
    assert pool.inactive_agents == 0
    assert pool.operational_agents == 1


def test_pool_url(pool, okta_service):
    """The pool url is built from its id."""
    assert pool.url == f'{okta_service.api}/agentPools/poolid1'


def test_pool_has_no_timestamps(pool):
    """The pool payload carries no created/lastUpdated, so the inherited dates are None."""
    assert pool.created_at is None
    assert pool.last_updated_at is None


@pytest.mark.parametrize(
    ('status', 'expected'),
    [('OPERATIONAL', True), ('DEGRADED', False), ('DISRUPTED', False), ('INACTIVE', False), (None, False)],
)
def test_pool_is_operational(okta_service, status, expected):
    """Only an OPERATIONAL pool is reported as operational."""
    pool = DirectoryIntegrationsAgentPool(okta_service, make_pool(operational_status=status))
    assert pool.is_operational is expected


def test_agents_are_embedded(okta_service, monkeypatch):
    """The pool listing embeds its agents, so reading them makes no request."""

    def fail(*_args, **_kwargs):
        raise AssertionError('reading embedded agents must not make a request')

    monkeypatch.setattr(okta_service.session, 'get', fail)
    pool = DirectoryIntegrationsAgentPool(
        okta_service, make_pool(agents=[make_agent('one'), make_agent('two', 'DISRUPTED')])
    )
    assert [agent.id for agent in pool.agents] == ['one', 'two']


def test_pool_without_agents(okta_service):
    """A pool with no agents reports an empty list rather than failing."""
    pool = DirectoryIntegrationsAgentPool(okta_service, make_pool(agents=[]))
    assert pool.agents == []
    assert pool.down_agents == []


def test_down_agents_are_the_non_operational_ones(okta_service):
    """The agents behind an "Agent down" task are the ones that are not operational."""
    pool = DirectoryIntegrationsAgentPool(
        okta_service,
        make_pool(
            agents=[
                make_agent('healthy'),
                make_agent('degraded', 'DEGRADED'),
                make_agent('disrupted', 'DISRUPTED'),
                make_agent('inactive', 'INACTIVE'),
            ]
        ),
    )
    assert [agent.id for agent in pool.down_agents] == ['degraded', 'disrupted', 'inactive']


def test_down_agents_reconcile_with_oktas_own_counts(okta_service):
    """Okta's counts and the embedded list must agree, as they do on a real pool.

    Mirrors an observed pool: three agents, one inactive, counted 2 operational
    and 1 inactive by Okta.
    """
    pool = DirectoryIntegrationsAgentPool(
        okta_service,
        make_pool(
            agents=[make_agent('one'), make_agent('two'), make_agent('three', 'INACTIVE')],
            operationalAgents=2,
            inactiveAgents=1,
        ),
    )
    assert len(pool.agents) == pool.operational_agents + pool.inactive_agents + pool.disrupted_agents
    assert len(pool.down_agents) == pool.inactive_agents


def test_agent_without_a_status_counts_as_down(okta_service):
    """A missing status is surfaced rather than silently treated as healthy."""
    pool = DirectoryIntegrationsAgentPool(okta_service, make_pool(agents=[make_agent('unknown', None)]))
    agent = pool.agents[0]
    assert agent.operational_status is None
    assert not agent.is_operational
    assert [down.id for down in pool.down_agents] == ['unknown']


def test_agent_properties(okta_service, pool_data):
    """The agent exposes the fields needed to chase down a broken agent."""
    agent = DirectoryIntegrationsAgent(okta_service, pool_data, make_agent('one', 'DISRUPTED'))
    assert agent.id == 'one'
    assert agent.name == 'AGENT-one'
    assert agent.type == 'AD'
    assert agent.operational_status == 'DISRUPTED'
    assert agent.version == '3.22.0'
    assert agent.is_latest_version is False
    assert agent.is_hidden is False


def test_agent_pool_id_comes_from_the_agent(okta_service, pool_data):
    """The agent carries its own poolId, which is preferred over the parent's."""
    agent = DirectoryIntegrationsAgent(okta_service, pool_data, make_agent('one', poolId='poolid-own'))
    assert agent.pool_id == 'poolid-own'


def test_agent_pool_id_falls_back_to_the_parent(okta_service, pool_data):
    """Without its own poolId the agent reports the pool it was read from."""
    data = make_agent('one')
    del data['poolId']
    assert DirectoryIntegrationsAgent(okta_service, pool_data, data).pool_id == 'poolid1'


def test_agent_last_connection_is_epoch_millis(okta_service, pool_data):
    """Okta reports this as milliseconds since the epoch, not an ISO 8601 string.

    The expected value is stated outright rather than computed from the input, so
    the assertion does not simply restate the conversion it is checking.
    """
    agent = DirectoryIntegrationsAgent(okta_service, pool_data, make_agent('one'))
    assert agent.last_connection == datetime(2026, 7, 6, 14, 26, 50, tzinfo=UTC)


def test_agent_that_never_connected(okta_service, pool_data):
    """An agent that has never connected reports no last connection."""
    data = make_agent('one')
    del data['lastConnection']
    assert DirectoryIntegrationsAgent(okta_service, pool_data, data).last_connection is None


def test_agent_update_fields_absent_for_ad_agents(okta_service, pool_data):
    """AD agents omit the spec's update fields, which must read as None not crash."""
    agent = DirectoryIntegrationsAgent(okta_service, pool_data, make_agent('one'))
    assert agent.update_status is None
    assert agent.update_message is None


def test_agent_update_fields_when_present(okta_service, pool_data):
    """Agent types that do report the update fields have them exposed."""
    agent = DirectoryIntegrationsAgent(
        okta_service,
        pool_data,
        make_agent('one', updateStatus='UPDATE_FAILED', updateMessage='Could not reach the update host'),
    )
    assert agent.update_status == 'UPDATE_FAILED'
    assert agent.update_message == 'Could not reach the update host'


def test_pools_are_listed(okta_service, monkeypatch):
    """The client yields a pool per entry the agent pools endpoint returns."""
    requested = {}

    def record(url=None, params=None, **_kwargs):
        requested['url'] = url
        requested['params'] = params
        return make_json_response([make_pool('poolid1'), make_pool('poolid2')])

    monkeypatch.setattr(okta_service.session, 'get', record)
    assert [pool.id for pool in okta_service.directory_integrations_agent_pools] == ['poolid1', 'poolid2']
    assert requested['url'] == f'{okta_service.api}/agentPools'


def test_pool_by_id(okta_service, monkeypatch):
    """A pool is found by id from the listing, since Okta serves no single pool."""
    monkeypatch.setattr(
        okta_service.session, 'get', lambda *a, **k: make_json_response([make_pool('poolid1'), make_pool('poolid2')])
    )
    assert okta_service.get_directory_integrations_agent_pool_by_id('poolid2').id == 'poolid2'


def test_pool_by_id_not_found(okta_service, monkeypatch):
    """An id matching nothing yields None rather than raising."""
    monkeypatch.setattr(okta_service.session, 'get', lambda *a, **k: make_json_response([make_pool('poolid1')]))
    assert okta_service.get_directory_integrations_agent_pool_by_id('nope') is None


def test_pool_by_name_is_case_insensitive(okta_service, monkeypatch):
    """Names are matched case insensitively, as they are for application labels."""
    monkeypatch.setattr(okta_service.session, 'get', lambda *a, **k: make_json_response([make_pool()]))
    assert okta_service.get_directory_integrations_agent_pool_by_name('an ad pool').id == 'poolid1'


def test_pool_by_name_not_found(okta_service, monkeypatch):
    """A name matching nothing yields None rather than raising."""
    monkeypatch.setattr(okta_service.session, 'get', lambda *a, **k: make_json_response([make_pool()]))
    assert okta_service.get_directory_integrations_agent_pool_by_name('Some other pool') is None


def test_pools_by_type_filters_server_side(okta_service, monkeypatch):
    """The pool type is sent to Okta rather than filtered locally."""
    requested = {}

    def record(url=None, params=None, **_kwargs):
        requested['url'] = url
        requested['params'] = params
        return make_json_response([make_pool()])

    monkeypatch.setattr(okta_service.session, 'get', record)
    assert [pool.id for pool in okta_service.get_directory_integrations_agent_pools_by_type('AD')] == ['poolid1']
    assert requested['url'] == f'{okta_service.api}/agentPools'
    assert requested['params']['poolType'] == 'AD'


def test_pool_refreshes_from_the_listing(pool, monkeypatch):
    """Refreshing re-reads the listing, because a single pool cannot be fetched.

    The inherited implementation would GET the pool's own url, which Okta rejects
    with 405.
    """
    requested = []

    def record(url=None, **_kwargs):
        requested.append(url)
        return make_json_response([make_pool('poolid1', operational_status='DEGRADED')])

    monkeypatch.setattr(pool._okta.session, 'get', record)
    assert pool._update()
    assert requested == [f'{pool._okta.api}/agentPools']
    assert pool.operational_status == 'DEGRADED'


def test_pool_refresh_fails_when_the_pool_is_gone(pool, monkeypatch):
    """A pool that has left the listing reports a failed refresh."""
    monkeypatch.setattr(pool._okta.session, 'get', lambda *a, **k: make_json_response([make_pool('another')]))
    assert not pool._update()


def test_live_agent_pools_are_listed(okta_cassette, okta_service):
    """Real call: the org's agent pools come back with their agents embedded."""
    with okta_cassette():
        pools = list(okta_service.directory_integrations_agent_pools)

    assert pools
    for pool in pools:
        assert pool.id
        assert pool.type
        assert pool.operational_status
        assert pool.agents


def test_live_agent_counts_reconcile(okta_cassette, okta_service):
    """Real call: Okta's own counts agree with the embedded agent list.

    This is the check that says the pool payload is complete rather than a
    filtered view of it.
    """
    with okta_cassette():
        pools = list(okta_service.directory_integrations_agent_pools)

    assert pools
    for pool in pools:
        counted = pool.operational_agents + pool.inactive_agents + pool.disrupted_agents
        assert len(pool.agents) == counted
        assert len(pool.down_agents) == len(pool.agents) - pool.operational_agents


def test_live_last_connection_parses(okta_cassette, okta_service):
    """Real call: the epoch-millisecond timestamp Okta sends becomes a datetime.

    Regression test for reading ``lastConnection`` as an ISO 8601 string, which
    silently returned None for every agent.
    """
    with okta_cassette():
        pools = list(okta_service.directory_integrations_agent_pools)

    connections = [agent.last_connection for pool in pools for agent in pool.agents]
    assert connections
    assert any(connection is not None for connection in connections)
    assert all(connection is None or connection.tzinfo is not None for connection in connections)


def test_live_pools_by_type(okta_cassette, okta_service):
    """Real call: Okta honours poolType, and rejects a type it does not know."""
    with okta_cassette():
        matching = list(okta_service.get_directory_integrations_agent_pools_by_type('AD'))
        absent = list(okta_service.get_directory_integrations_agent_pools_by_type('LDAP'))

    assert matching
    assert all(pool.type == 'AD' for pool in matching)
    assert not absent


def test_live_pool_by_name(okta_cassette, okta_service):
    """Real call: a pool found by name is the same pool the listing yields."""
    with okta_cassette():
        first = next(iter(okta_service.directory_integrations_agent_pools))
        found = okta_service.get_directory_integrations_agent_pool_by_name(first.name)

    assert found is not None
    assert found.id == first.id


def test_live_single_pool_cannot_be_fetched(okta_cassette, okta_service):
    """Real call: Okta answers 405 for a single pool, which is why url is not fetched.

    Pins the reason ``_update`` re-reads the listing instead of the pool's own url.
    """
    with okta_cassette():
        pool = next(iter(okta_service.directory_integrations_agent_pools))
        response = okta_service.session.get(pool.url)

    assert response.status_code == 405
