#!/usr/bin/env python
# File: oktasession.py
#
# Copyright 2026 Yorick Hoorneman
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to
#  deal in the Software without restriction, including without limitation the
#  rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
#  sell copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
#  all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#  FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#  DEALINGS IN THE SOFTWARE.
#

"""
The http transport for oktalib.

Everything about talking to Okta's api lives here: resolving endpoints, recovering
from a token Okta stopped accepting, pagination and the translation of a failed
response into a ``ServerError``. The rest of the library names endpoints and
interprets payloads; it never assembles a url or decides how to retry.

The session doing the talking is not built here. The credentials build it, because
only they know how to authenticate it and how to tell whether that worked, and it
arrives already rate limited and already proven. This wraps it rather than being it.

.. _Google Python Style Guide:
   https://google.github.io/styleguide/pyguide.html

"""

import logging
from collections.abc import Generator
from http import HTTPStatus
from typing import Any

from requests import Response

from .configuration import DEFAULT_PAGE_SIZE, DEFAULT_TIMEOUT
from .oktacredentials import OktaCredentials
from .oktalibexceptions import AuthFailed, ServerError
from .ratelimitedsession import RateLimitedSession

__author__ = 'Yorick Hoorneman <yhoorneman@schubergphilis.com>'
__docformat__ = 'google'
__date__ = '2026-09-15'
__copyright__ = 'Copyright 2026, Yorick Hoorneman'
__credits__ = ['Yorick Hoorneman']
__license__ = 'MIT'
__maintainer__ = 'Yorick Hoorneman'
__email__ = '<yhoorneman@schubergphilis.com>'
__status__ = 'Development'  # "Prototype", "Development", "Production".

LOGGER_BASENAME = 'oktasession'
LOGGER = logging.getLogger(LOGGER_BASENAME)
LOGGER.addHandler(logging.NullHandler())


class OktaSession:
    """An authenticated session against one Okta instance.

    Knows where the instance is, so callers name an endpoint rather than assembling
    a url: ``session.get('/users')`` reaches ``{host}/api/v1/users``. A url that is
    already absolute is sent as it stands, which covers both the pagination links
    Okta hands back and the ``/oauth2/v1`` endpoints that sit outside ``/api/v1``.
    """

    def __init__(
        self,
        host: str,
        credentials: OktaCredentials,
        timeout: float | tuple[float, float] | None = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize the session, authenticated by the credentials.

        Args:
            host: The host of the okta instance, e.g. https://dev.oktapreview.com
            credentials: What to authenticate with, an api token or a service app.
            timeout: The default applied to any request that does not name its own.

        Raises:
            AuthFailed: Okta rejected the credentials.

        """
        logger_name = f'{LOGGER_BASENAME}.{self.__class__.__name__}'
        self._logger = logging.getLogger(logger_name)
        self.host = host
        self._credentials = credentials
        self._logger.debug(f'Authenticating with {credentials.type}.')
        self._session = credentials.authenticated_session(host, timeout)

    @property
    def api(self) -> str:
        """The root of the instance's rest api, for callers that need it spelled out.

        Returns:
            str: The api root, e.g. https://dev.oktapreview.com/api/v1

        """
        return f'{self.host}/api/v1'

    @property
    def http_session(self) -> RateLimitedSession:
        """The requests session underneath, for tooling that has to attach to one.

        Returns:
            RateLimitedSession: The session the credentials authenticated.

        """
        return self._session

    def request(self, method: str, url: str, **kwargs: Any) -> Response:
        """Resolve an endpoint against the instance and make the request.

        A 401 means the credentials stopped being accepted part way through a run, a
        token revoked or expired early, so the credentials are asked to renew and the
        request is made once more. That is safe on any verb: Okta refused the request
        rather than acting on it. A 403 is left alone, since it means a role or scope
        is missing, which no renewal can grant.

        Args:
            method: HTTP verb.
            url: An endpoint such as ``/users``, resolved against :attr:`api`, or an
                absolute url, which is used as it stands.
            kwargs: Keyword arguments passed through to requests.

        Raises:
            AuthFailed: Okta still refused the credentials once they were renewed, or
                they cannot be renewed at all.

        Returns:
            Response: The response.

        """
        if not url.startswith(('http://', 'https://')):
            url = f'{self.api}{url}'
        response = self._session.request(method, url, **kwargs)
        if response.status_code != HTTPStatus.UNAUTHORIZED:
            return response
        self._logger.debug(f'Okta refused {self._credentials.type} for {url}, renewing.')
        self._credentials.renew(self._session)
        response = self._session.request(method, url, **kwargs)
        if response.status_code == HTTPStatus.UNAUTHORIZED:
            raise AuthFailed(f'Okta refused {self._credentials.type} even once they were renewed.')
        return response

    def get(self, url: str, **kwargs: Any) -> Response:
        """Make a GET request.

        Args:
            url: An endpoint or an absolute url, see :meth:`request`.
            kwargs: Keyword arguments passed through to requests.

        Returns:
            Response: The response.

        """
        return self.request('GET', url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> Response:
        """Make a POST request.

        Args:
            url: An endpoint or an absolute url, see :meth:`request`.
            kwargs: Keyword arguments passed through to requests.

        Returns:
            Response: The response.

        """
        return self.request('POST', url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> Response:
        """Make a PUT request.

        Args:
            url: An endpoint or an absolute url, see :meth:`request`.
            kwargs: Keyword arguments passed through to requests.

        Returns:
            Response: The response.

        """
        return self.request('PUT', url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> Response:
        """Make a DELETE request.

        Args:
            url: An endpoint or an absolute url, see :meth:`request`.
            kwargs: Keyword arguments passed through to requests.

        Returns:
            Response: The response.

        """
        return self.request('DELETE', url, **kwargs)

    def get_paginated_url(
        self,
        url: str,
        result_limit: int = DEFAULT_PAGE_SIZE,
        params: dict[str, Any] | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        """Gets the paginated data from a url.

        Args:
            url: The endpoint to get the data from
            result_limit: The number of results to get per page, defaults to 100
            params: Optional extra query parameters for the first request. Entries
                with a None value are dropped, so callers can pass optional
                filters through directly. Subsequent pages are followed by the
                link Okta returns, which already carries these parameters.

        Returns:
            generator: A generator of the data from the url

        """
        query: dict[str, Any] = {'limit': result_limit}
        query.update({key: value for key, value in (params or {}).items() if value is not None})
        response = self.validate_response(url, query)
        yield from response.json()
        next_link = response.links.get('next', {}).get('url')
        while next_link:
            response = self.validate_response(url=next_link)
            yield from response.json()
            next_link = response.links.get('next', {}).get('url')

    def validate_response(self, url: str, params: dict[str, Any] | None = None) -> Response:
        """Validate API response and raise appropriate exceptions on error.

        Args:
            url: The endpoint to request
            params: Optional query parameters for the request

        Returns:
            Response: The validated HTTP response object

        Raises:
            ServerError: If the response indicates an error (not ok status)

        """
        response = self.get(url=url, params=params)
        if not response.ok:
            try:
                error_message = response.json().get('errorSummary')
            except (ValueError, AttributeError):
                error_message = response.text
            raise ServerError(error_message) from None
        return response
