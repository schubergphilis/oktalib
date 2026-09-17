"""A recorded test for a service app, against a real org.

How the library behaves is covered by the unit tests. What this asserts is Okta's half
of the bargain: that it mints a bound token for an assertion signed with a registered
key, and then accepts a call that proves possession of the key the token was bound to.
Both are worth pinning down. The nonce dance at the token endpoint is a required step
rather than an error, and Okta's own guide says the resource side does not *currently*
ask for a nonce -- "currently" being the word that makes a recording worth having.
"""
# pylint: disable=redefined-outer-name

import json
import os
from pathlib import Path

import pytest
from betamax import Betamax

from oktalib.oktasession import RateLimitedSession
from tests.conftest import configure_betamax, extract_pytest_path, okta_base_url, service_app_credentials


@pytest.fixture
def recorded_service_app(request):
    """A session authenticated as a service app, with its token exchange recorded too.

    Two recorders, because minting deliberately happens on a session of its own and
    betamax wraps a session rather than a client. The exchange therefore lands in a
    cassette beside the one holding the api call.

    Skipped when there is neither a service app configured to record with nor a
    recording to replay, rather than reaching for a real org either way.
    """
    host = okta_base_url()
    configure_betamax(token=os.environ.get('OKTA_API_KEY', 'fake_api_key'), base_url=host)
    filename, test_name = extract_pytest_path(request.node.nodeid)
    api_cassette, token_cassette = f'{filename}_{test_name}', f'{filename}_{test_name}_token'
    recorded = all(Path('tests/cassettes', f'{name}.json').exists() for name in (api_cassette, token_cassette))
    if 'OKTA_CLIENT_ID' not in os.environ and not recorded:
        pytest.skip('no service app configured to record with, and nothing recorded to replay')

    token_session = RateLimitedSession()
    api_session = RateLimitedSession()
    minting = Betamax(token_session).use_cassette(token_cassette)
    calling = Betamax(api_session).use_cassette(api_cassette)
    minting.start()
    calling.start()
    try:
        api_session.auth = service_app_credentials().authenticator(host, token_session)
        yield host, api_session
    finally:
        calling.stop()
        minting.stop()


def test_a_service_app_is_granted_a_bound_token_and_may_use_it(recorded_service_app):
    """The exchange Okta's org authorization server is the only issuer of, and a call.

    The assertion is signed with the app's private key; the token comes back bound to a
    second key the client holds; and the call presents that token with a fresh proof
    naming the method and url it was made for and hashing the token it was made with.
    Neither the token nor the proof is worth anything without the other.
    """
    host, api_session = recorded_service_app
    token = api_session.auth.token
    response = api_session.get(f'{host}/api/v1/users', params={'limit': 1})
    sent = response.request.headers

    assert token.token_type == 'DPoP'
    assert response.status_code == 200
    assert len(json.loads(response.text)) == 1
    assert sent['Authorization'].startswith('DPoP ')
    assert 'DPoP' in sent
