"""Tests for the session that backs off on Okta's rate limit."""
# pylint: disable=redefined-outer-name

import logging

import pytest
from requests import PreparedRequest, Response

from oktalib.oktalib import RateLimitedSession
from oktalib.oktalibexceptions import ApiLimitReached


@pytest.fixture
def responder(monkeypatch):
    """Drive the adapter with a scripted list of status codes, recording each attempt.

    Patching the adapter rather than ``Session.request`` leaves the class under test
    untouched, so the override, the backoff decorator and requests' own dispatch all
    still run.
    """
    attempts = []

    def install(status_codes):
        codes = list(status_codes)

        def send(_adapter, request: PreparedRequest, **_kwargs) -> Response:
            attempts.append(request.url)
            response = Response()
            response.status_code = codes[len(attempts) - 1] if len(attempts) <= len(codes) else codes[-1]
            response._content = b'{}'
            response.request = request
            return response

        monkeypatch.setattr('requests.adapters.HTTPAdapter.send', send)
        return attempts

    return install


def test_a_normal_response_is_returned_untouched(responder):
    """Nothing is retried when Okta does not report a rate limit."""
    attempts = responder([200])
    response = RateLimitedSession().get('https://example.com/api/v1/users')

    assert response.status_code == 200
    assert len(attempts) == 1


def test_a_429_is_retried_until_it_succeeds(responder):
    """The rate limit is transient, so the request is repeated rather than failed."""
    attempts = responder([429, 429, 200])
    response = RateLimitedSession().get('https://example.com/api/v1/users')

    assert response.status_code == 200
    assert len(attempts) == 3


def test_every_verb_backs_off_not_just_get(responder):
    """Session.post and friends route through request(), so the override covers them."""
    attempts = responder([429, 200])
    response = RateLimitedSession().post('https://example.com/api/v1/groups', data='{}')

    assert response.status_code == 200
    assert len(attempts) == 2


def test_an_unrelated_error_status_is_not_retried(responder):
    """Only 429 means rate limited; a 500 is the caller's problem to handle."""
    attempts = responder([500])
    response = RateLimitedSession().get('https://example.com/api/v1/users')

    assert response.status_code == 500
    assert len(attempts) == 1


def test_a_rate_limit_raises_so_backoff_can_catch_it(responder):
    """The 429 is turned into the exception the decorator retries on.

    Called through ``__wrapped__``, the undecorated implementation, because that is
    the behaviour this class owns; whether backoff then retries or gives up at
    max_time is backoff's contract, covered by the retry test above.
    """
    attempts = responder([429])
    session = RateLimitedSession()

    with pytest.raises(ApiLimitReached):
        RateLimitedSession.request.__wrapped__(session, 'GET', 'https://example.com/api/v1/users')
    assert len(attempts) == 1


def test_the_backing_off_warning_names_the_session_logger(responder, caplog):
    """The operator needs to know a run is slow because Okta throttled it."""
    responder([429, 200])
    logger = logging.getLogger('a-caller')
    with caplog.at_level(logging.WARNING, logger='a-caller'):
        RateLimitedSession(logger=logger).get('https://example.com/api/v1/users')

    assert any('backing off' in record.message for record in caplog.records)
