"""Tests for the credentials: what they sign with, what they prove, and what they keep quiet."""
# pylint: disable=redefined-outer-name

import ast
import base64
import json
import traceback
from pathlib import Path
from urllib.parse import parse_qs

import pytest
from jwskate import Jwk, to_jwk
from requests import PreparedRequest, Request, RequestException, Response
from requests.auth import AuthBase

from oktalib.oktacredentials import ApiTokenCredentials, ServiceAppAuth, ServiceAppCredentials
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


@pytest.fixture(scope='module')
def private_key() -> Jwk:
    """A signing key generated once per module, so no key material lives in the repo.

    It carries a kid, as a key uploaded to Okta as a JWK would. A PEM never does, which
    is why the tests that start from one have to say which id Okta knows it by.

    Generating one costs over a second, and nothing here mutates it -- the code under
    test copies the key before labelling it, which test_a_key_the_caller_owns_is_not_
    relabelled exists to prove -- so one key serves the module.
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


@pytest.mark.parametrize(
    ('curve', 'algorithm'),
    [('P-256', 'ES256'), ('P-384', 'ES384'), ('P-521', 'ES512')],
)
def test_the_signing_algorithm_follows_an_ec_curve(curve, algorithm, token_endpoint):
    """For an elliptic curve key the algorithm is fixed by the curve, not the key type.

    Reading it off the type instead signs every EC key as ES256, which P-384 and P-521
    cannot do at all, so a legitimately registered key could never authenticate -- and
    the refusal came from the signer, reading as though Okta had rejected the client.
    """
    requests_made = token_endpoint()
    # Generated by algorithm, then stripped of it, so the curve is all there is to go on.
    generated = dict(Jwk.generate(alg=algorithm).with_kid_thumbprint())
    key = to_jwk({name: value for name, value in generated.items() if name != 'alg'})
    assert key.crv == curve
    ServiceAppCredentials('0oa1', key, ['okta.users.read'], dpop=False).authenticator(HOST, RateLimitedSession())

    assert claims_of(assertion_of(requests_made[-1]), 0)['alg'] == algorithm


def test_an_explicit_algorithm_beats_the_one_on_the_key(private_key, token_endpoint):
    """A key carrying its own alg would otherwise outrank the algorithm asked for.

    The signer reads the key first and falls back to its argument, so passing the
    algorithm alongside the key had no effect at all: the caller asked for RS512, every
    assertion went out as RS256, and nothing said so.
    """
    requests_made = token_endpoint()
    key = to_jwk(dict(private_key) | {'alg': 'RS256'})
    ServiceAppCredentials('0oa1', key, ['okta.users.read'], algorithm='RS512', dpop=False).authenticator(
        HOST, RateLimitedSession()
    )

    assert claims_of(assertion_of(requests_made[-1]), 0)['alg'] == 'RS512'


def test_a_key_that_cannot_sign_an_assertion_does_not_blame_okta(token_endpoint):
    """Building the signer asks Okta nothing, so its complaints are not Okta's.

    Handing over the public half of the pair is an easy mistake, since the public half
    is what gets registered. Reporting that as Okta refusing the credentials sends the
    caller to the admin console to check scopes that were never the problem.
    """
    token_endpoint()
    public_key = Jwk.generate(alg='RS256').with_kid_thumbprint().public_jwk()
    credentials = ServiceAppCredentials('0oa1', public_key, ['okta.users.read'])

    with pytest.raises(AuthFailed, match='cannot sign a client assertion'):
        credentials.authenticator(HOST, RateLimitedSession())


def test_dpop_is_not_proved_when_it_is_declined(private_key, token_endpoint):
    """dpop=False is used throughout the suite, so it has to be worth something."""
    requests_made = token_endpoint()
    ServiceAppCredentials('0oa1', private_key, ['okta.users.read'], dpop=False).authenticator(
        HOST, RateLimitedSession()
    )

    assert 'DPoP' not in requests_made[-1].headers


def test_a_refused_renewal_is_reported_as_a_failed_authentication(private_key):
    """Renewal happens an hour in, lazily, while an ordinary call is being prepared.

    Okta can refuse it by then -- a scope withdrawn, the app deactivated -- and without
    translation the caller gets an exception from a library it never imported, raised
    from a call site whose documented failures are ServerError and ApiLimitReached.
    """

    class Refusing(AuthBase):  # pylint: disable=too-few-public-methods
        """Stand in for a renewal that fails while a request is being prepared."""

        def __call__(self, request: PreparedRequest) -> PreparedRequest:
            """Fail the way the signer does when the token endpoint refuses."""
            raise RequestException('the token endpoint refused to renew')

    credentials = ServiceAppCredentials('0oa1', private_key, ['okta.users.read'])

    with pytest.raises(AuthFailed, match='would not renew'):
        ServiceAppAuth(Refusing(), credentials)(signed())


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


def test_scopes_are_accepted_as_one_string_as_well_as_a_sequence(private_key, token_endpoint):
    """A string is a sequence of strings, so taking one apart asks for it by the letter.

    Okta spells scopes space delimited and that is how they arrive from the environment,
    so a caller passing the string straight through is the expected mistake. It used to
    reach Okta as 32 single character scopes, reported back as a request for custom
    scopes, which names neither the cause nor the caller's error.
    """
    requests_made = token_endpoint()
    ServiceAppCredentials('0oa1', private_key, 'okta.users.read okta.groups.read', dpop=False).authenticator(
        HOST, RateLimitedSession()
    )

    assert parse_qs(requests_made[-1].body)['scope'] == ['okta.users.read okta.groups.read']


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


def test_a_key_that_cannot_be_read_is_not_quoted_in_the_failure(private_key):
    """The reason a key was refused must not be repeated, because it is the key.

    jwskate reports a JWK it will not accept by passing the whole mapping as the
    exception's argument, so its str() is the key, private parameters included. A
    message or traceback carrying that hands over enough to mint org tokens, which is
    the opposite of what an error about a rejected key should cost.
    """
    # Structurally a JWK, but cryptography will not build a key from it.
    unusable = dict(private_key) | {'d': private_key['d'][:-8]}

    with pytest.raises(AuthFailed) as raised:
        ServiceAppCredentials('0oa1', unusable, ['okta.users.read'])

    rendered = f'{raised.value}{raised.value.__cause__}'.join(
        traceback.format_exception(type(raised.value), raised.value, raised.value.__traceback__)
    )
    assert not [name for name in ('d', 'p', 'q', 'dp', 'dq', 'qi') if unusable[name] in rendered]


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
