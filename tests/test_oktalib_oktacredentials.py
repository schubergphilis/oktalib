"""Tests for the credentials: what they sign with, what they prove, and what they keep quiet."""
# pylint: disable=redefined-outer-name

import ast
import base64
import json
from pathlib import Path
from urllib.parse import parse_qs

import pytest
from jwskate import Jwk
from requests import PreparedRequest, Request, Response

from oktalib.oktacredentials import ApiTokenCredentials, ServiceAppCredentials
from oktalib.oktalibexceptions import AuthFailed
from oktalib.oktasession import RateLimitedSession

HOST = 'https://example.okta.com'
OAUTH_DEPENDENCIES = ('requests_oauth2client', 'jwskate')
MINTED_TOKEN = {
    'access_token': 'an-access-token',
    'token_type': 'Bearer',
    'expires_in': 3600,
    'scope': 'okta.users.read',
}


def signed(url: str = f'{HOST}/api/v1/users') -> PreparedRequest:
    """A request on its way out, for a handler to sign."""
    return Request(method='GET', url=url).prepare()


def imported_names(node: ast.AST) -> list[str]:
    """The modules one node imports, whichever import form it is."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        return [node.module or '']
    return []


def imports_the_dependency(module: Path) -> bool:
    """Whether a source file reaches for the oauth dependency at all."""
    nodes = ast.walk(ast.parse(module.read_text(encoding='utf-8')))
    return any(name.split('.')[0] in OAUTH_DEPENDENCIES for node in nodes for name in imported_names(node))


def claims_of(token: str, segment: int) -> dict:
    """Read a segment of a JWT without verifying it, for asserting on what we sent."""
    encoded = token.split('.')[segment]
    return json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))


@pytest.fixture
def private_key() -> Jwk:
    """A signing key generated per test, so no key material lives in the repo.

    It carries a kid, as a key uploaded to Okta as a JWK would. A PEM never does, which
    is why the tests that start from one have to say which id Okta knows it by.
    """
    return Jwk.generate(alg='RS256').with_kid_thumbprint()


@pytest.fixture
def token_endpoint(monkeypatch):
    """Answer the token endpoint from a script, recording what was asked of it."""
    requests_made = []

    def install(status_code=200, payload=None):
        body = payload or MINTED_TOKEN

        def send(_adapter, request: PreparedRequest, **_kwargs) -> Response:
            requests_made.append(request)
            response = Response()
            response.status_code = status_code
            response._content = json.dumps(body).encode()
            response.headers['content-type'] = 'application/json'
            response.request = request
            return response

        monkeypatch.setattr('requests.adapters.HTTPAdapter.send', send)
        return requests_made

    return install


def assertion_of(request: PreparedRequest) -> str:
    """The client assertion out of a recorded token request."""
    return parse_qs(request.body)['client_assertion'][0]


def test_an_api_token_is_signed_as_ssws():
    """Okta's own api tokens use a scheme of their own rather than Bearer."""
    request = ApiTokenCredentials('a-token').authenticator(HOST, RateLimitedSession())(signed())

    assert request.headers['authorization'] == 'SSWS a-token'


def test_an_api_token_is_proved_against_the_current_user():
    """Any valid token may read its own user, so it proves the token without a scope."""
    assert ApiTokenCredentials('a-token').probe == '/users/me/'


def test_a_service_app_has_nothing_to_probe(private_key):
    """There is no user to read, and every endpoint needs a scope that may not be granted.

    Minting the token is the proof instead, so a probe could only fail a client that
    is configured correctly but narrowly.
    """
    credentials = ServiceAppCredentials('0oa1', private_key, ['okta.users.read'])

    assert credentials.probe is None


def test_credentials_describe_themselves_without_disclosing_themselves(private_key):
    """Descriptions reach logs, so they carry a client id at most, never key material."""
    token = ApiTokenCredentials('a-secret-token')
    service_app = ServiceAppCredentials('0oa1', private_key, ['okta.users.read'])

    assert 'a-secret-token' not in f'{token} {token!r}'
    assert str(service_app) == 'service app 0oa1'
    assert private_key.to_pem() not in f'{service_app} {service_app!r}'


def test_the_key_id_okta_assigned_is_what_the_assertion_carries(private_key, token_endpoint):
    """Okta finds the key to verify against by kid, and its kid is not the thumbprint.

    Signing under the thumbprint jwskate would otherwise compute leaves Okta unable to
    match the assertion to any key it registered.
    """
    requests_made = token_endpoint()
    credentials = ServiceAppCredentials(
        '0oa1', private_key, ['okta.users.read'], key_id='the-one-okta-assigned', dpop=False
    )
    credentials.authenticator(HOST, RateLimitedSession())

    assert claims_of(assertion_of(requests_made[-1]), 0)['kid'] == 'the-one-okta-assigned'


def test_a_key_the_caller_owns_is_not_relabelled(private_key):
    """The id Okta assigned goes on a copy of the key, not on the key we were given.

    A Jwk permits its kid to be assigned, so the tempting one-liner would reach back
    into an object the caller may keep and use for something else.
    """
    kid_they_gave_us = private_key.kid
    ServiceAppCredentials('0oa1', private_key, ['okta.users.read'], key_id='the-one-okta-assigned')

    assert private_key.kid == kid_they_gave_us


def test_the_signing_algorithm_follows_the_key(private_key, token_endpoint):
    """An algorithm that can be derived is one more thing that can be set wrong."""
    requests_made = token_endpoint()
    ServiceAppCredentials('0oa1', private_key, ['okta.users.read'], dpop=False).authenticator(
        HOST, RateLimitedSession()
    )

    assert claims_of(assertion_of(requests_made[-1]), 0)['alg'] == 'RS256'


def test_a_pem_is_accepted_as_well_as_a_jwk(private_key, token_endpoint):
    """A key arrives from a secret manager as a PEM at least as often as a JWK."""
    requests_made = token_endpoint()
    ServiceAppCredentials(
        '0oa1', private_key.to_pem(), ['okta.users.read'], key_id='the-one-okta-assigned', dpop=False
    ).authenticator(HOST, RateLimitedSession())

    assert claims_of(assertion_of(requests_made[-1]), 1)['iss'] == '0oa1'


def test_a_key_with_no_id_says_where_to_find_one(private_key):
    """A PEM carries no kid, so the failure has to name what is missing and where it is.

    The dependency refuses such a key before a request is ever made, reporting only
    that a key id is required, which leaves the caller no way to find out which one.
    """
    with pytest.raises(AuthFailed, match='key_id'):
        ServiceAppCredentials('0oa1', private_key.to_pem(), ['okta.users.read'])


def test_a_jwk_is_accepted_as_json_too(private_key, token_endpoint):
    """A secret manager hands back a string, and a JWK is as likely a shape as a PEM."""
    requests_made = token_endpoint()
    ServiceAppCredentials('0oa1', json.dumps(dict(private_key)), ['okta.users.read'], dpop=False).authenticator(
        HOST, RateLimitedSession()
    )

    assert claims_of(assertion_of(requests_made[-1]), 0)['kid'] == private_key.kid


def test_the_token_is_asked_for_at_the_org_authorization_server(private_key, token_endpoint):
    """Only the org authorization server mints tokens carrying okta.* scopes."""
    requests_made = token_endpoint()
    ServiceAppCredentials('0oa1', private_key, ['okta.users.read', 'okta.groups.read'], dpop=False).authenticator(
        HOST, RateLimitedSession()
    )
    body = parse_qs(requests_made[-1].body)

    assert requests_made[-1].url == f'{HOST}/oauth2/v1/token'
    assert body['grant_type'] == ['client_credentials']
    assert body['scope'] == ['okta.users.read okta.groups.read']


def test_possession_of_the_key_is_proved_when_dpop_is_asked_for(private_key, token_endpoint):
    """A bound token is useless to anyone who captures it without the key."""
    requests_made = token_endpoint(payload={'access_token': 'a-token', 'token_type': 'DPoP', 'expires_in': 3600})
    ServiceAppCredentials('0oa1', private_key, ['okta.users.read']).authenticator(HOST, RateLimitedSession())

    assert 'DPoP' in requests_made[-1].headers


def test_okta_refusing_to_mint_a_token_fails_at_construction(private_key, token_endpoint):
    """Credentials Okta will not accept should fail while the caller is still looking at them."""
    token_endpoint(status_code=400, payload={'error': 'invalid_client'})
    credentials = ServiceAppCredentials('0oa1', private_key, ['okta.users.read'], dpop=False)

    with pytest.raises(AuthFailed):
        credentials.authenticator(HOST, RateLimitedSession())


def test_a_key_that_cannot_be_read_is_refused_before_anything_is_asked_of_okta():
    """Reading the key needs nothing but the key, so it fails where the caller wrote it."""
    with pytest.raises(AuthFailed):
        ServiceAppCredentials('0oa1', 'this is not a key', ['okta.users.read'], key_id='irrelevant')


def test_nothing_from_the_oauth_dependency_escapes_the_credentials(private_key, token_endpoint):
    """The failure must be ours, or callers end up importing the dependency to catch it."""
    token_endpoint(status_code=400, payload={'error': 'invalid_scope'})
    credentials = ServiceAppCredentials('0oa1', private_key, ['okta.users.read'], dpop=False)

    with pytest.raises(AuthFailed) as raised:
        credentials.authenticator(HOST, RateLimitedSession())

    assert isinstance(raised.value, AuthFailed)
    assert raised.value.__cause__ is not None


def test_the_oauth_dependency_lives_in_one_module_only():
    """Swapping the dependency should stay a change to one method in one file.

    The research behind this work left two fallbacks and a maintainer of one, so the
    seam is worth asserting rather than trusting: everything else in the package talks
    to credentials through an AuthBase, which is a requests type we already depend on.
    """
    source = Path(__file__).parent.parent / 'src' / 'oktalib'
    importers = {module.name for module in source.rglob('*.py') if imports_the_dependency(module)}

    assert importers == {'oktacredentials.py'}
