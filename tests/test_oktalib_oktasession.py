"""Tests for the http transport: the retry policy, the timeouts and the endpoint resolution."""
# pylint: disable=redefined-outer-name

import logging
import time
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any, NamedTuple
from uuid import uuid4

import pytest
from requests import PreparedRequest, Response
from requests.auth import AuthBase
from requests.exceptions import ReadTimeout

from oktalib.oktacredentials import ApiTokenCredentials
from oktalib.oktalibexceptions import ApiLimitReached, AuthFailed
from oktalib.oktasession import (
    DEFAULT_TIMEOUT,
    LOGGER_BASENAME,
    RATE_LIMIT_STATUS,
    RETRY_BACKOFF_FACTOR,
    RETRY_BACKOFF_JITTER,
    RETRY_BACKOFF_MAX,
    RETRY_TOTAL,
    OktaSession,
    RateLimitedSession,
    retry_delay,
    should_retry,
)


class Attempt(NamedTuple):
    """One request as the adapter saw it."""

    url: str
    timeout: float | tuple[float, float] | None
    headers: dict[str, Any] = {}  # noqa: RUF012
    body: Any = None


class Served(NamedTuple):
    """One request as the real server saw it."""

    method: str
    headers: dict[str, str] = {}  # noqa: RUF012


class FreshProof(AuthBase):  # pylint: disable=too-few-public-methods
    """Stand in for a DPoP handler: stamp a proof that is unique per preparation.

    The real handler derives its proof from the request, so a replay that never runs
    the auth layer again reuses the jti Okta has already seen. A uuid per call makes
    that reuse visible without needing a key, the dependency or a cassette.
    """

    def __call__(self, request: PreparedRequest) -> PreparedRequest:
        """Sign the request as a DPoP handler would."""
        request.headers['DPoP'] = str(uuid4())
        return request


@pytest.fixture
def responder(monkeypatch):
    """Answer with a scripted list of status codes, recording each attempt.

    This patches the adapter, which sits *above* urllib3, so nothing here is
    retried. It is for the behaviour that surrounds retrying -- timeouts, endpoint
    resolution, authentication. Retry behaviour itself needs ``okta_answering``.
    """
    attempts = []

    def install(status_codes, headers=None):
        codes = list(status_codes)

        def send(_adapter, request: PreparedRequest, **kwargs) -> Response:
            attempts.append(
                Attempt(
                    url=request.url,
                    timeout=kwargs.get('timeout'),
                    headers=dict(request.headers),
                    body=request.body,
                )
            )
            response = Response()
            response.status_code = codes[len(attempts) - 1] if len(attempts) <= len(codes) else codes[-1]
            response._content = b'{}'
            response.request = request
            response.headers.update(headers or {})
            return response

        monkeypatch.setattr('requests.adapters.HTTPAdapter.send', send)
        return attempts

    return install


@pytest.fixture
def instant_retries(monkeypatch):
    """Keep the real retry policy but take the sleeping out, so the suite stays quick."""
    monkeypatch.setattr('oktalib.oktasession.RETRY_BACKOFF_FACTOR', 0)
    monkeypatch.setattr('oktalib.oktasession.RETRY_BACKOFF_JITTER', 0)


@pytest.fixture
def okta_answering():
    """Serve a scripted list of status codes from a real socket, counting requests.

    The retry policy lives inside urllib3, below the adapter the ``responder``
    fixture patches, so reaching it at all means going through a real connection.
    The last code in the list repeats once the list runs out.
    """
    server = None

    def install(status_codes, delay=0):
        nonlocal server
        codes = list(status_codes)
        served = []

        class Handler(BaseHTTPRequestHandler):
            """Answer every verb from the scripted list, recording what was asked."""

            protocol_version = 'HTTP/1.1'

            def respond(self):
                """Serve the next scripted status, after the configured delay."""
                headers = {name.lower(): value for name, value in self.headers.items()}
                served.append(Served(method=self.command, headers=headers))
                # Drain the body, or keep-alive would parse it as the next request line.
                self.rfile.read(int(self.headers.get('content-length') or 0))
                if delay:
                    time.sleep(delay)
                status = codes[len(served) - 1] if len(served) <= len(codes) else codes[-1]
                body = b'{}'
                self.send_response(status)
                self.send_header('content-type', 'application/json')
                self.send_header('content-length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = do_POST = respond

            def log_message(self, *_args):
                """Keep the scripted failures out of the test output."""

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        Thread(target=server.serve_forever, daemon=True).start()
        return f'http://127.0.0.1:{server.server_port}/api/v1/users', served

    yield install
    if server is not None:
        server.shutdown()
        server.server_close()


def test_a_normal_response_is_returned_untouched(responder):
    """Nothing is retried when Okta answers successfully."""
    attempts = responder([200])
    response = RateLimitedSession().get('https://example.com/api/v1/users')

    assert response.status_code == 200
    assert len(attempts) == 1


def test_a_client_error_is_not_retried(responder):
    """A 404 is an answer, not a failure to get one; repeating it changes nothing."""
    attempts = responder([404])
    response = RateLimitedSession().get('https://example.com/api/v1/users')

    assert response.status_code == 404
    assert len(attempts) == 1


@pytest.mark.usefixtures('instant_retries')
def test_a_rate_limit_is_retried_until_it_succeeds(okta_answering):
    """The rate limit is transient, so the request is repeated rather than failed."""
    url, served = okta_answering([429, 429, 200])
    response = RateLimitedSession().get(url)

    assert response.status_code == 200
    assert [record.method for record in served] == ['GET', 'GET', 'GET']


@pytest.mark.usefixtures('instant_retries')
def test_a_rate_limit_is_retried_on_a_post_too(okta_answering):
    """Okta rejected the request rather than acting on it, so a replay cannot duplicate.

    This is the case urllib3's own ``allowed_methods`` would refuse, and it is the
    one that matters most: creating users and groups goes out as POSTs, and that is
    the bulk work that exhausts a rate limit in the first place.
    """
    url, served = okta_answering([429, 200])
    response = RateLimitedSession().post(url, data='{}')

    assert response.status_code == 200
    assert [record.method for record in served] == ['POST', 'POST']


@pytest.mark.usefixtures('instant_retries')
def test_a_retried_request_is_signed_again(okta_answering):
    """A retry must carry a new proof, not a replay of the one Okta already saw.

    Retrying below the auth layer resends the serialized bytes, so a DPoP proof goes
    out a second time with a jti the server has already recorded and rejects, and an
    iat that has aged by however long the backoff lasted. See
    okta/terraform-provider-okta#2598 for the same failure in the wild. This is the
    defect that passes every happy-path test and then fails during a bulk run, so the
    signing has to happen above whatever repeats the request.
    """
    url, served = okta_answering([429, 200])
    session = RateLimitedSession()
    session.auth = FreshProof()
    response = session.post(url, data='{}')

    assert response.status_code == 200
    assert len(served) == 2
    assert served[0].headers['dpop'] != served[1].headers['dpop']


@pytest.mark.usefixtures('instant_retries')
def test_a_rate_limit_that_outlasts_the_retries_is_reported(okta_answering):
    """Callers document an except ApiLimitReached, so exhaustion must still raise it."""
    url, served = okta_answering([429])

    with pytest.raises(ApiLimitReached):
        RateLimitedSession().get(url)

    assert len(served) == RETRY_TOTAL + 1


@pytest.mark.usefixtures('instant_retries')
def test_the_giving_up_warning_is_logged_under_the_class(okta_answering, caplog):
    """The operator needs to know a run failed because Okta throttled it.

    The logger is named for the class rather than injected, so a subclass is filterable
    on its own and the message is attributed to the transport that emitted it.
    """
    url, _ = okta_answering([429])
    with caplog.at_level(logging.WARNING, logger=LOGGER_BASENAME), pytest.raises(ApiLimitReached):
        RateLimitedSession().get(url)

    assert [record.name for record in caplog.records] == ['oktasession.RateLimitedSession']
    assert any('giving up' in record.message for record in caplog.records)


@pytest.mark.usefixtures('instant_retries')
def test_a_server_error_on_a_get_is_retried(okta_answering):
    """A 503 is Okta being briefly unavailable, and a GET costs nothing to repeat."""
    url, served = okta_answering([503, 503, 200])
    response = RateLimitedSession().get(url)

    assert response.status_code == 200
    assert [record.method for record in served] == ['GET', 'GET', 'GET']


@pytest.mark.usefixtures('instant_retries')
def test_a_server_error_on_a_post_is_not_retried(okta_answering):
    """A 503 leaves it unknown whether Okta acted, so a POST must not be replayed."""
    url, served = okta_answering([503, 200])
    response = RateLimitedSession().post(url, data='{}')

    assert response.status_code == 503
    assert [record.method for record in served] == ['POST']


@pytest.mark.usefixtures('instant_retries')
def test_an_exhausted_server_error_comes_back_as_a_response(okta_answering):
    """raise_on_status off keeps validate_response the single place errors surface."""
    url, served = okta_answering([503])
    response = RateLimitedSession().get(url)

    assert response.status_code == 503
    assert len(served) == RETRY_TOTAL + 1


@pytest.mark.usefixtures('instant_retries')
def test_a_hung_endpoint_is_not_retried(okta_answering):
    """Retrying a read timeout would multiply it by the budget and block for minutes."""
    url, served = okta_answering([200], delay=2)

    with pytest.raises(ReadTimeout):
        RateLimitedSession(timeout=(5, 0.5)).get(url)

    assert len(served) == 1


def test_a_rate_limit_is_retryable_on_every_verb():
    """A 429 is safe on any verb; a server error is only safe on the idempotent ones."""
    assert should_retry('POST', RATE_LIMIT_STATUS)
    assert should_retry('GET', RATE_LIMIT_STATUS)
    assert not should_retry('POST', 503)
    assert should_retry('GET', 503)


def test_a_client_error_is_never_retryable():
    """A 404 is an answer, and the policy has to say so rather than rely on the caller."""
    assert not should_retry('GET', 404)
    assert not should_retry('GET', 200)


def test_okta_is_waited_for_as_long_as_it_asks(responder, monkeypatch):
    """Okta knows when the limit resets, so its Retry-After beats our own guess."""
    slept = []
    monkeypatch.setattr('oktalib.oktasession.time.sleep', slept.append)
    responder([429, 200], headers={'retry-after': '2'})
    response = RateLimitedSession().get('https://example.com/api/v1/users')

    assert response.status_code == 200
    assert slept == [2]


def test_a_retry_after_date_is_understood():
    """Okta may answer with an HTTP date rather than a number of seconds."""
    in_thirty_seconds = formatdate(time.time() + 30, usegmt=True)

    assert 25 <= retry_delay(1, in_thirty_seconds) <= 30


def test_a_long_retry_after_is_capped():
    """An hour-long wait would hang a caller that asked for a timeout of seconds."""
    assert retry_delay(1, '3600') == RETRY_BACKOFF_MAX


def test_an_unparseable_retry_after_falls_back_to_the_backoff():
    """A header we cannot read is not a reason to give up on retrying."""
    assert RETRY_BACKOFF_FACTOR <= retry_delay(1, 'in a little while') <= RETRY_BACKOFF_FACTOR + RETRY_BACKOFF_JITTER


def test_the_wait_grows_with_each_attempt():
    """A limit that survived one wait is unlikely to clear within the same again."""
    assert retry_delay(3, None) > retry_delay(1, None)


def test_no_retrying_happens_inside_urllib3():
    """Retrying below the auth layer would replay a signature the server has seen.

    urllib3 resends the bytes it was handed, so a DPoP proof or a client assertion
    would go out again with a jti Okta has already recorded. The repeating therefore
    belongs in request(), and this asserts the adapter was left with none of it.
    """
    for scheme in ('https://', 'http://'):
        assert RateLimitedSession().get_adapter(f'{scheme}example.com').max_retries.total == 0


def test_a_request_that_names_no_timeout_gets_the_default(responder):
    """requests applies no timeout of its own, so a hung endpoint would block forever."""
    attempts = responder([200])
    RateLimitedSession().get('https://example.com/api/v1/users')

    assert attempts[0].timeout == DEFAULT_TIMEOUT


def test_the_session_default_is_configurable(responder):
    """A caller with slower endpoints sets it once rather than at every call site."""
    attempts = responder([200])
    RateLimitedSession(timeout=90).get('https://example.com/api/v1/users')

    assert attempts[0].timeout == 90


def test_a_timeout_on_the_call_wins(responder):
    """One slow endpoint should not have to raise the default for everything."""
    attempts = responder([200])
    RateLimitedSession().get('https://example.com/api/v1/users', timeout=120)

    assert attempts[0].timeout == 120


def test_an_explicit_none_still_means_no_timeout(responder):
    """Waiting forever stays available, but only when it is asked for."""
    attempts = responder([200])
    RateLimitedSession().get('https://example.com/api/v1/users', timeout=None)

    assert attempts[0].timeout is None


@pytest.fixture
def okta_session(responder):
    """An OktaSession whose authentication is answered, so construction succeeds."""

    def install(status_codes=(200,)):
        attempts = responder(status_codes)
        return OktaSession('https://example.okta.com', ApiTokenCredentials('a-token')), attempts

    return install


def test_an_endpoint_is_resolved_against_the_instance(okta_session):
    """The business logic names /users; only the session knows where that lives."""
    session, attempts = okta_session()
    session.get('/users')

    assert attempts[-1].url == 'https://example.okta.com/api/v1/users'


def test_an_absolute_url_is_left_alone(okta_session):
    """Okta's own pagination links come back absolute and must not be prefixed."""
    session, attempts = okta_session()
    session.get('https://example.okta.com/api/v1/users?after=00u2')

    assert attempts[-1].url == 'https://example.okta.com/api/v1/users?after=00u2'


def test_an_endpoint_outside_the_api_root_stays_absolute(okta_session):
    """The oauth2 endpoints sit beside /api/v1 rather than under it."""
    session, attempts = okta_session()
    session.get(f'{session.host}/oauth2/v1/clients/0oa1/roles')

    assert attempts[-1].url == 'https://example.okta.com/oauth2/v1/clients/0oa1/roles'


def test_the_api_root_is_spelled_out_for_the_callers_that_need_it(okta_session):
    """An entity's canonical url is output rather than a request, so it stays absolute."""
    session, _ = okta_session()

    assert session.api == 'https://example.okta.com/api/v1'


def test_the_token_is_sent_on_every_request(okta_session):
    """The credentials are applied as each request is prepared rather than pinned once.

    An api token would work either way, but installing it the same way as a credential
    that has to sign per request is what keeps one code path for both.
    """
    session, attempts = okta_session()
    session.get('/users')

    assert attempts[-1].headers['authorization'] == 'SSWS a-token'
    assert 'authorization' not in session.headers


def test_a_rejected_token_fails_at_construction(responder):
    """A session that cannot authenticate is never handed to the caller."""
    responder([200, 401])

    with pytest.raises(AuthFailed):
        OktaSession('https://example.okta.com', ApiTokenCredentials('a-bad-token'))
