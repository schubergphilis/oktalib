#!/usr/bin/env python
# File: configuration.py
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
The settings oktalib talks to Okta with.

Endpoints, timeouts, retry and backoff limits and token lifetimes, gathered in one
place so they can be read and tuned without searching the modules that use them.

.. _Google Python Style Guide:
   https://google.github.io/styleguide/pyguide.html

"""

from http import HTTPStatus

__author__ = 'Yorick Hoorneman <yhoorneman@schubergphilis.com>'
__docformat__ = 'google'
__date__ = '2026-10-22'
__copyright__ = 'Copyright 2026, Yorick Hoorneman'
__credits__ = ['Yorick Hoorneman']
__license__ = 'MIT'
__maintainer__ = 'Yorick Hoorneman'
__email__ = '<yhoorneman@schubergphilis.com>'
__status__ = 'Development'  # "Prototype", "Development", "Production".

# Only the org authorization server mints tokens carrying okta.* scopes, so this sits at
# the org root rather than under a custom authorization server's id.
TOKEN_ENDPOINT = '/oauth2/v1/token'
CURRENT_USER_ENDPOINT = '/users/me/'
# Okta refuses an assertion that expires more than an hour out. A minute is plenty for
# one request and leaves nothing worth replaying if it is ever captured.
ASSERTION_LIFETIME = 60
# Renew this long before expiry, so a token cannot lapse between the check and the call.
EXPIRY_LEEWAY = 20

DEFAULT_TIMEOUT = (5, 30)  # (connect, read)
RATE_LIMIT_STATUS = HTTPStatus.TOO_MANY_REQUESTS
RETRY_TOTAL = 3
RETRY_BACKOFF_FACTOR = 1.0
RETRY_BACKOFF_JITTER = 0.5
RETRY_BACKOFF_MAX = 60
SERVER_ERROR_STATUSES = (
    HTTPStatus.INTERNAL_SERVER_ERROR,
    HTTPStatus.BAD_GATEWAY,
    HTTPStatus.SERVICE_UNAVAILABLE,
    HTTPStatus.GATEWAY_TIMEOUT,
)
IDEMPOTENT_METHODS = frozenset({'DELETE', 'GET', 'HEAD', 'OPTIONS', 'PUT'})
DEFAULT_PAGE_SIZE = 100
