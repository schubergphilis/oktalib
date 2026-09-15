"""Tests for the http transport: the retry policy, the timeouts and the endpoint resolution."""
# pylint: disable=redefined-outer-name

import logging
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import NamedTuple

import pytest
from requests import PreparedRequest, Response
from requests.exceptions import ReadTimeout

from oktalib.oktalibexceptions import ApiLimitReached, AuthFailed
from oktalib.oktasession import (
    DEFAULT_TIMEOUT,
    IDEMPOTENT_METHODS,
    LOGGER_BASENAME,
    RETRY_TOTAL,
    SERVER_ERROR_STATUSES,
    OktaRetry,
    OktaSession,
    RateLimitedSession,
)


class Attempt(NamedTuple):
    """One request as the adapter saw it."""

    url: str
    timeout: float | tuple[float, float] | None


@pytest.fixture
def responder(monkeypatch):
    """Answer with a scripted list of status codes, recording each attempt.

    This patches the adapter, which sits *above* urllib3, so nothing here is
    retried. It is for the behaviour that surrounds retrying -- timeouts, endpoint
    resolution, authentication. Retry behaviour itself needs ``okta_answering``.
    """
    attempts = []

    def install(status_codes):
        codes = list(status_codes)

        def send(_adapter, request: PreparedRequest, **kwargs) -> Response:
            attempts.append(Attempt(url=request.url, timeout=kwargs.get('timeout')))
            response = Response()
            response.status_code = codes[len(attempts) - 1] if len(attempts) <= len(codes) else codes[-1]
            response._content = b'{}'
            response.request = request
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
                served.append(self.command)
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
    assert served == ['GET', 'GET', 'GET']


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
    assert served == ['POST', 'POST']


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
    assert served == ['GET', 'GET', 'GET']


@pytest.mark.usefixtures('instant_retries')
def test_a_server_error_on_a_post_is_not_retried(okta_answering):
    """A 503 leaves it unknown whether Okta acted, so a POST must not be replayed."""
    url, served = okta_answering([503, 200])
    response = RateLimitedSession().post(url, data='{}')

    assert response.status_code == 503
    assert served == ['POST']


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
    """The policy exempts 429 from allowed_methods; everything else obeys it."""
    retry = OktaRetry(status_forcelist=SERVER_ERROR_STATUSES, allowed_methods=IDEMPOTENT_METHODS)

    assert retry.is_retry('POST', 429)
    assert retry.is_retry('GET', 429)
    assert not retry.is_retry('POST', 503)
    assert retry.is_retry('GET', 503)


def test_the_mounted_policy_restricts_server_errors_to_the_safe_verbs():
    """A dropped connection on a POST leaves it unknown whether Okta acted on it."""
    retries = RateLimitedSession().get_adapter('https://example.com').max_retries

    assert 'GET' in retries.allowed_methods
    assert 'POST' not in retries.allowed_methods
    assert 'PATCH' not in retries.allowed_methods


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
        return OktaSession('https://example.okta.com', 'a-token'), attempts

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
    """Authentication is installed once on the session, not per call."""
    session, _ = okta_session()

    assert session.headers['authorization'] == 'SSWS a-token'


def test_a_rejected_token_fails_at_construction(responder):
    """A session that cannot authenticate is never handed to the caller."""
    responder([200, 401])

    with pytest.raises(AuthFailed):
        OktaSession('https://example.okta.com', 'a-bad-token')
