#!/usr/bin/env python
# File: oktacredentials.py
#
# Copyright 2018 Costas Tyfoxylos
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
What oktalib authenticates with.

A credential knows one thing: how to turn itself into a requests auth handler that
signs every call to an org. Okta accepts two kinds, an api token and a service app
holding a private key, and they have almost nothing in common beyond that -- one is a
header, the other is a signed assertion exchanged for a token that is then proved with
a fresh signature per request. Both arrive here as an ``AuthBase``, so the session
installs either the same way and never learns which it was handed.

Keeping that behind one interface is also what keeps the OAuth dependency in one place.
Nothing outside this module imports it, and none of its types appear in a signature or
escape as an exception, so replacing it stays a change to one method.

.. _Google Python Style Guide:
   https://google.github.io/styleguide/pyguide.html

"""

import logging
from abc import ABC, abstractmethod
from typing import Any

from jwskate import Jwk, to_jwk
from requests import PreparedRequest, RequestException, Session
from requests.auth import AuthBase
from requests_oauth2client import OAuth2Client, OAuth2ClientCredentialsAuth, OAuth2Error, PrivateKeyJwt

from .oktalibexceptions import AuthFailed

__author__ = 'Costas Tyfoxylos <ctyfoxylos@schubergphilis.com>'
__docformat__ = 'google'
__copyright__ = 'Copyright 2018, Costas Tyfoxylos'
__license__ = 'MIT'
__maintainer__ = 'Costas Tyfoxylos'
__email__ = '<ctyfoxylos@schubergphilis.com>'
__status__ = 'Development'  # "Prototype", "Development", "Production".

# This is the main prefix used for logging
LOGGER_BASENAME = 'oktacredentials'
LOGGER = logging.getLogger(LOGGER_BASENAME)
LOGGER.addHandler(logging.NullHandler())

# Only the org authorization server mints tokens carrying okta.* scopes, so this sits at
# the org root rather than under a custom authorization server's id.
TOKEN_ENDPOINT = '/oauth2/v1/token'
CURRENT_USER_ENDPOINT = '/users/me/'
# Okta refuses an assertion that expires more than an hour out. A minute is plenty for
# one request and leaves nothing worth replaying if it is ever captured.
ASSERTION_LIFETIME = 60
# Renew this long before expiry, so a token cannot lapse between the check and the call.
EXPIRY_LEEWAY = 20
SIGNATURE_ALGORITHMS = {'RSA': 'RS256', 'EC': 'ES256'}


class ApiTokenAuth(AuthBase):  # pylint: disable=too-few-public-methods
    """Signs every request with an Okta api token."""

    def __init__(self, token: str) -> None:
        """Initialize the handler.

        Args:
            token: The api token to sign with.

        """
        self._token = token

    def __call__(self, request: PreparedRequest) -> PreparedRequest:
        """Sign the request.

        Args:
            request: The request on its way out.

        Returns:
            PreparedRequest: The same request, signed.

        """
        request.headers['authorization'] = f'SSWS {self._token}'
        return request


class OktaCredentials(ABC):
    """How a caller proves to one Okta org that it may use the api."""

    @abstractmethod
    def authenticator(self, host: str, token_session: Session) -> AuthBase:
        """Build the handler that signs every call to this org.

        Args:
            host: The org root, for credentials that derive an endpoint from it.
            token_session: A session carrying the org's transport policy, for
                credentials that must call an endpoint to obtain their authority.
                Ignored by credentials that already hold it.

        Raises:
            AuthFailed: Okta would not accept the credentials.

        Returns:
            AuthBase: The handler to install on the session.

        """

    @property
    def probe(self) -> str | None:
        """The endpoint whose success proves the credentials work.

        Returns:
            str | None: An endpoint to call, or None when nothing can prove it.

        """
        return None

    def __str__(self) -> str:
        """Describe the credentials without disclosing them.

        Returns:
            str: A description safe to log.

        """
        return self.__class__.__name__


class ApiTokenCredentials(OktaCredentials):
    """An Okta api token, the one an administrator creates in the admin console."""

    def __init__(self, token: str) -> None:
        """Initialize the credentials.

        Args:
            token: The api token to authenticate with.

        """
        self._token = token

    # An api token is bearer-like: it carries its own authority, so there is no endpoint
    # to call and nothing about the org to know before signing with it.
    def authenticator(self, host: str, token_session: Session) -> AuthBase:  # pylint: disable=unused-argument
        """Build the handler that signs every call with this token.

        Args:
            host: Unused, the token is not bound to an endpoint.
            token_session: Unused, nothing has to be exchanged.

        Returns:
            AuthBase: A handler stamping the token on every request.

        """
        return ApiTokenAuth(self._token)

    @property
    def probe(self) -> str | None:
        """The endpoint that proves the token works.

        Returns:
            str | None: The current user, which any valid token may read.

        """
        return CURRENT_USER_ENDPOINT

    def __str__(self) -> str:
        """Describe the credentials without disclosing them.

        Returns:
            str: A description safe to log.

        """
        return 'api token'


class ServiceAppCredentials(OktaCredentials):
    """An Okta API Services app, authenticating with a private key.

    The app exchanges an assertion signed with its private key for an access token.
    Okta's org authorization server allows nothing else: a client secret is refused
    outright there, whatever the app is configured with.

    Access is the intersection of two gates that are granted separately, so a key that
    Okta accepts is not yet a client that may do anything. The app needs the okta.*
    scopes granted to it, which only a super administrator can do, and it needs an
    admin role assigned. Minting a token proves the scopes; the role only shows up as a
    403 on the first real call.
    """

    def __init__(
        self,
        client_id: str,
        private_key: dict[str, Any] | str,
        scopes: list[str] | tuple[str, ...],
        *,
        key_id: str | None = None,
        algorithm: str | None = None,
        dpop: bool = True,
    ) -> None:
        """Initialize the credentials.

        Args:
            client_id: The client id of the API Services app.
            private_key: The private key whose public half is registered on the app,
                as a JWK mapping or a PEM.
            scopes: The okta.* scopes to ask for. Okta refuses any that are not granted
                to the app, so there is no sensible default.
            key_id: The id Okta gave the registered public key. Okta selects the key to
                verify against by the kid in the assertion, and the id it assigns is
                not the key's thumbprint, so without this the assertion is rejected as
                invalid_client. Leave unset only if the key already carries its kid.
            algorithm: The algorithm to sign the assertion with. Derived from the key
                when unset.
            dpop: Whether to bind the token to a held key, proving possession on every
                request. An application setting in Okta, so it has to match the app.

        """
        self._client_id = client_id
        self._private_key = private_key
        self._scopes = tuple(scopes)
        self._key_id = key_id
        self._algorithm = algorithm
        self._dpop = dpop
        self._logger = logging.getLogger(f'{LOGGER_BASENAME}.{self.__class__.__name__}')

    @property
    def signing_key(self) -> Jwk:
        """The private key, as something that can sign an assertion.

        Returns:
            Jwk: The key, carrying the kid Okta knows it by.

        Raises:
            AuthFailed: The key could not be read.

        """
        try:
            key = self._private_key
            jwk = Jwk.from_pem(key) if isinstance(key, str) else to_jwk(key)
            if self._key_id:
                jwk = to_jwk(dict(jwk) | {'kid': self._key_id})
        except (ValueError, TypeError) as error:
            raise AuthFailed(f'The private key of service app {self._client_id} could not be read: {error}') from error
        if not jwk.get('kid'):
            raise AuthFailed(
                f'The private key of service app {self._client_id} has no key id. Okta picks the key to verify '
                f'an assertion against by the id it assigned when the public key was registered, so pass it as '
                f'key_id. A PEM never carries one, and the id Okta assigns is not the key thumbprint, so it '
                f'cannot be worked out from the key itself: read it from the app, or from the public keys listed '
                f'under its client credentials in the admin console.'
            )
        return jwk

    def authenticator(self, host: str, token_session: Session) -> AuthBase:
        """Build the handler that signs every call with a minted access token.

        The token is minted here rather than on the first call, so credentials Okta
        will not accept fail while the caller is still looking at the constructor.

        Args:
            host: The org root, which the token endpoint hangs off.
            token_session: The session to mint over. Deliberately not the session being
                authenticated: that one labels its bodies as json and carries the very
                handler being renewed.

        Raises:
            AuthFailed: Okta would not mint a token for these credentials.

        Returns:
            AuthBase: A handler that presents the token and proves possession of the
                key on every request.

        """
        jwk = self.signing_key
        algorithm = self._algorithm or SIGNATURE_ALGORITHMS.get(str(jwk.kty))
        try:
            client = OAuth2Client(
                token_endpoint=f'{host}{TOKEN_ENDPOINT}',
                auth=PrivateKeyJwt(self._client_id, jwk, alg=algorithm, lifetime=ASSERTION_LIFETIME),
                dpop_bound_access_tokens=self._dpop,
                session=token_session,
            )
            authenticator = OAuth2ClientCredentialsAuth(client, scope=' '.join(self._scopes), leeway=EXPIRY_LEEWAY)
            authenticator.renew_token()
        except (OAuth2Error, RequestException, ValueError) as error:
            raise AuthFailed(f'Okta would not mint a token for {self}: {error}') from error
        self._logger.debug(f'Minted an access token for {self}, scopes {" ".join(self._scopes)}.')
        return authenticator

    def __str__(self) -> str:
        """Describe the credentials without disclosing them.

        Returns:
            str: A description safe to log, a client id being public.

        """
        return f'service app {self._client_id}'
