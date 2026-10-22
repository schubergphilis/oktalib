#!/usr/bin/env python
# File: oktacredentials.py
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
What oktalib authenticates with.

A credential knows how to hand over a session that is already authenticated against
an org, how to tell that the authentication worked, and how to renew it once Okta stops
accepting it. Okta accepts two kinds, an api token and a service app holding a private
key, and they have almost nothing in common beyond that -- one is a header, the other is
a signed assertion exchanged for a token that is then proved with a fresh signature per
request. Both sign through an ``AuthBase`` installed on a rate limited session, so the
api session receives either the same way and never learns which it was handed.

Keeping that behind one interface is also what keeps the OAuth dependency in one place.
Nothing outside this module imports it, and none of its types appear in a signature or
escape as an exception, so replacing it stays a change to one method.

.. _Google Python Style Guide:
   https://google.github.io/styleguide/pyguide.html

"""

import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from jwskate import Jwk, to_jwk
from requests import PreparedRequest, RequestException
from requests.auth import AuthBase
from requests_oauth2client import OAuth2Client, OAuth2ClientCredentialsAuth, OAuth2Error, PrivateKeyJwt

from .configuration import ASSERTION_LIFETIME, CURRENT_USER_ENDPOINT, DEFAULT_TIMEOUT, EXPIRY_LEEWAY, TOKEN_ENDPOINT
from .oktalibexceptions import AuthFailed
from .ratelimitedsession import RateLimitedSession

__author__ = 'Yorick Hoorneman <yhoorneman@schubergphilis.com>'
__docformat__ = 'google'
__date__ = '2026-09-16'
__copyright__ = 'Copyright 2026, Yorick Hoorneman'
__credits__ = ['Yorick Hoorneman']
__license__ = 'MIT'
__maintainer__ = 'Yorick Hoorneman'
__email__ = '<yhoorneman@schubergphilis.com>'
__status__ = 'Development'  # "Prototype", "Development", "Production".

# This is the main prefix used for logging
LOGGER_BASENAME = 'oktacredentials'
LOGGER = logging.getLogger(LOGGER_BASENAME)
LOGGER.addHandler(logging.NullHandler())


def read_key(private_key: Jwk | dict[str, Any] | str) -> Jwk:
    """Read a private key, however it was handed over.

    Args:
        private_key: The key, as a JWK mapping, a Jwk, the same as json, or a PEM.

    Raises:
        ValueError: The key could not be read.
        TypeError: The key is not one of the shapes above.

    Returns:
        Jwk: The key, as something that can sign.

    """
    # to_jwk reads a mapping, a Jwk and json alike, but tries json on any string, so a
    # PEM is the one shape that has to be steered past it.
    if isinstance(private_key, str) and not private_key.lstrip().startswith('{'):
        return Jwk.from_pem(private_key)
    return to_jwk(private_key)


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


class ServiceAppAuth(AuthBase):  # pylint: disable=too-few-public-methods
    """Presents a minted token, and renews it when it is about to expire.

    A wrapper over the signer rather than the signer itself, because renewal happens an
    hour into a run, lazily, while an ordinary call is being prepared. Okta can refuse
    it by then -- a scope withdrawn, the app deactivated -- and without this the caller
    would get an exception from a library it never imported, raised from a call site
    whose documented failures are ``ServerError`` and ``ApiLimitReached``.
    """

    def __init__(self, authenticator: AuthBase, credentials: 'ServiceAppCredentials') -> None:
        """Initialize the handler.

        Args:
            authenticator: The handler that presents and renews the token.
            credentials: The credentials it was built from, to name in a failure.

        """
        self._authenticator = authenticator
        self._credentials = credentials

    @property
    def token(self) -> Any:
        """The token currently held, for callers and tests that inspect it.

        Returns:
            Any: The token, as the signer models it.

        """
        return self._authenticator.token  # type: ignore[attr-defined]

    def __call__(self, request: PreparedRequest) -> PreparedRequest:
        """Sign the request, renewing the token first if it has nearly expired.

        Args:
            request: The request on its way out.

        Raises:
            AuthFailed: Okta would not renew the token.

        Returns:
            PreparedRequest: The same request, signed.

        """
        try:
            return self._authenticator(request)
        except (OAuth2Error, RequestException) as error:
            raise AuthFailed(f'Okta would not renew the token for {self._credentials.type}: {error}') from error

    def renew(self) -> None:
        """Mint a token now, whether or not the one held has expired.

        Raises:
            AuthFailed: Okta would not mint a token for the credentials.

        """
        try:
            self._authenticator.renew_token()  # type: ignore[attr-defined]
        except (OAuth2Error, RequestException) as error:
            raise AuthFailed(f'Okta would not mint a token for {self._credentials.type}: {error}') from error


class OktaCredentials(ABC):
    """How a caller proves to one Okta org that it may use the api."""

    def authenticated_session(
        self,
        host: str,
        timeout: float | tuple[float, float] | None = DEFAULT_TIMEOUT,
    ) -> RateLimitedSession:
        """Build a session that signs every call to the org, and prove that it works.

        Args:
            host: The org root, e.g. https://dev.oktapreview.com
            timeout: The default applied to any request that does not name its own.

        Raises:
            AuthFailed: Okta would not accept the credentials.

        Returns:
            RateLimitedSession: A session Okta has already accepted the credentials on.

        """
        session = RateLimitedSession(timeout=timeout)
        # Unauthenticated on purpose, and before the credentials are installed: it only
        # confirms the host answers, so an unreachable org is not reported as a refusal.
        session.get(host)
        session.headers.update({'accept': 'application/json', 'content-type': 'application/json'})
        # Installed as ``auth`` rather than a header, so the credentials are applied while
        # each request is prepared. That is what lets a retry re-sign rather than replay,
        # and it is the only reason a DPoP proof can be per request at all.
        session.auth = self.authenticator(host, timeout)
        self.validate(session, host)
        return session

    @abstractmethod
    def authenticator(self, host: str, timeout: float | tuple[float, float] | None) -> AuthBase:
        """Build the handler that signs every call to this org, without calling Okta.

        Args:
            host: The org root, for credentials that derive an endpoint from it.
            timeout: The timeout for any session the handler needs of its own.

        Raises:
            AuthFailed: The credentials cannot sign anything.

        Returns:
            AuthBase: The handler to install on the session.

        """

    @abstractmethod
    def validate(self, session: RateLimitedSession, host: str) -> None:
        """Ask Okta to answer for the credentials now, on the session they sign.

        Args:
            session: The session carrying the handler from :meth:`authenticator`.
            host: The org root.

        Raises:
            AuthFailed: Okta rejected the credentials.

        """

    @abstractmethod
    def renew(self, session: RateLimitedSession) -> None:
        """Renew what the session signs with, after Okta stopped accepting it.

        Args:
            session: A session returned by :meth:`authenticated_session`.

        Raises:
            AuthFailed: There is nothing to renew, or Okta would not renew it.

        """

    @property
    def type(self) -> str:
        """The kind of credentials, without disclosing them.

        Returns:
            str: The class name, safe to log.

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
    def authenticator(self, host: str, timeout: float | tuple[float, float] | None) -> AuthBase:  # pylint: disable=unused-argument
        """Build the handler that signs every call with this token.

        Args:
            host: Unused, the token is not bound to an endpoint.
            timeout: Unused, nothing has to be exchanged.

        Returns:
            AuthBase: A handler stamping the token on every request.

        """
        return ApiTokenAuth(self._token)

    def validate(self, session: RateLimitedSession, host: str) -> None:
        """Read the current user, which any valid token may do without a scope.

        Args:
            session: The session carrying the token.
            host: The org root.

        Raises:
            AuthFailed: Okta rejected the token.

        """
        response = session.get(f'{host}/api/v1{CURRENT_USER_ENDPOINT}')
        if not response.ok:
            raise AuthFailed(response.text)

    def renew(self, session: RateLimitedSession) -> None:
        """Report that the token stopped working, since there is no renewing it.

        Args:
            session: Unused, the token is all there is.

        Raises:
            AuthFailed: Always. Only an administrator can issue a new token.

        """
        raise AuthFailed(
            f'Okta no longer accepts the {self.type}: it was revoked or expired, and only a new one helps.'
        )


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
        private_key: Jwk | dict[str, Any] | str,
        scopes: str | Sequence[str],
        *,
        key_id: str | None = None,
        algorithm: str | None = None,
        dpop: bool = True,
    ) -> None:
        """Initialize the credentials.

        Args:
            client_id: The client id of the API Services app.
            private_key: The private key whose public half is registered on the app, as
                a JWK mapping, the same as json, or a PEM. A path is deliberately not
                accepted: the key belongs in a secret manager rather than on disk.
            scopes: The okta.* scopes to ask for, as a sequence or as one space
                delimited string, which is how Okta itself spells them and how they
                arrive from an environment variable. Okta refuses any that are not
                granted to the app, so there is no sensible default.
            key_id: The id Okta gave the registered public key. Okta selects the key to
                verify against by the kid in the assertion, and the id it assigns is
                not the key's thumbprint, so it cannot be worked out from the key.
                Required unless the key already carries its own kid, which a PEM never
                does.
            algorithm: The algorithm to sign the assertion with. Derived from the key
                when unset.
            dpop: Whether to bind the token to a held key, proving possession on every
                request. An application setting in Okta, so it has to match the app.

        """
        self._client_id = client_id
        # A string is itself a sequence of strings, so tuple() would take it apart into
        # letters and ask Okta for each one, which it reports as a request for custom
        # scopes rather than as the mistake it is.
        self._scopes = tuple(scopes.split() if isinstance(scopes, str) else scopes)
        self._dpop = dpop
        self._logger = logging.getLogger(f'{LOGGER_BASENAME}.{self.__class__.__name__}')
        self._signing_key = self._load_signing_key(private_key, key_id, algorithm)

    def _load_signing_key(
        self, private_key: Jwk | dict[str, Any] | str, key_id: str | None, algorithm: str | None
    ) -> Jwk:
        """Read the private key, as something that can sign an assertion.

        The id and the algorithm are stamped onto the key rather than passed alongside
        it, because that is the only way either of them wins: the signer reads both off
        the key first and falls back to its arguments, so a key that carries its own
        ``alg`` would otherwise quietly outrank the one that was asked for.

        Args:
            private_key: The key, as a Jwk, a JWK mapping, JWK json, or a PEM.
            key_id: The id Okta knows the key by, if it is not in the key already.
            algorithm: The algorithm to sign with, or None to let the key decide.

        Raises:
            AuthFailed: The key could not be read, Okta could not be told which
                registered key it is, or the key cannot sign with the algorithm asked
                of it.

        Returns:
            Jwk: The key, carrying the kid Okta knows it by and the alg to sign with.

        """
        try:
            jwk = read_key(private_key)
            # A Jwk does allow its members to be assigned, but private_key may be an
            # object the caller keeps and uses elsewhere, so this goes on a copy.
            stamped = {'kid': key_id or jwk.get('kid'), 'alg': algorithm or self._algorithm_for(jwk)}
            jwk = to_jwk(dict(jwk) | {name: value for name, value in stamped.items() if value})
        except (ValueError, TypeError) as error:
            # Says nothing about why, on purpose. jwskate reports a key it will not accept
            # by quoting the whole key back, private parameters and all, so neither this
            # message nor a traceback may reach for it -- hence `from None` as well, since
            # a cause is rendered with its own str().
            raise AuthFailed(
                f'The private key of service app {self._client_id} could not be read '
                f'({type(error).__name__}). Nothing about the key is reported, since the '
                f'underlying error quotes the key itself.'
            ) from None
        if not jwk.get('kid'):
            raise AuthFailed(
                f'The private key of service app {self._client_id} has no key id. Okta picks the key to verify '
                f'an assertion against by the id it assigned when the public key was registered, so pass it as '
                f'key_id. A PEM never carries one, and the id Okta assigns is not the key thumbprint, so it '
                f'cannot be worked out from the key itself: read it from the app, or from the public keys listed '
                f'under its client credentials in the admin console.'
            )
        return jwk

    @staticmethod
    def _algorithm_for(jwk: Jwk) -> str | None:
        """The algorithm a key can sign an assertion with.

        Asked of the key rather than derived from its type, because for an elliptic
        curve key the algorithm follows the curve: P-256 signs ES256, P-384 only ES384
        and P-521 only ES512. Mapping every EC key to ES256 leaves a P-384 key unable to
        authenticate at all, and the complaint arrives from the signer rather than from
        Okta, which reads as though the org rejected the credentials.

        Args:
            jwk: The key that will do the signing.

        Returns:
            str | None: The algorithm to sign with, or None if the key supports none,
                which the signer reports better than a guess here would.

        """
        return next(iter(jwk.supported_signing_algorithms()), None)

    def authenticator(self, host: str, timeout: float | tuple[float, float] | None) -> AuthBase:
        """Build the handler that signs every call with a minted access token.

        No token is minted yet: that is what :meth:`validate` does, so the handler
        can be built and installed without Okta being asked anything.

        Args:
            host: The org root, which the token endpoint hangs off.
            timeout: The timeout for the session tokens are minted over.

        Raises:
            AuthFailed: The key cannot sign an assertion.

        Returns:
            AuthBase: A handler that presents the token and proves possession of the
                key on every request.

        """
        # Building the client validates the key locally and asks Okta nothing, so this
        # is not attributed to Okta: that would send the caller to the admin console for
        # a problem with the key they hold.
        try:
            client = self._token_client(host, RateLimitedSession(timeout=timeout))
            authenticator = OAuth2ClientCredentialsAuth(client, scope=' '.join(self._scopes), leeway=EXPIRY_LEEWAY)
        except ValueError as error:
            raise AuthFailed(f'The key of {self.type} cannot sign a client assertion: {error}') from error
        return ServiceAppAuth(authenticator, self)

    def validate(self, session: RateLimitedSession, host: str) -> None:
        """Mint the first token, which is the only proof a service app can give.

        There is no user to read, and every endpoint needs a scope that may not be
        granted, so calling one could only fail a client configured correctly but
        narrowly. The token is minted here rather than on the first call, so
        credentials Okta will not accept fail while the caller is still looking at the
        constructor.

        Args:
            session: The session carrying the handler from :meth:`authenticator`.
            host: Unused, the handler already knows its token endpoint.

        Raises:
            AuthFailed: Okta would not mint a token for these credentials.

        """
        self.renew(session)

    def renew(self, session: RateLimitedSession) -> None:
        """Mint a new token for the session, whether or not the one held has expired.

        Args:
            session: A session whose handler came from :meth:`authenticator`.

        Raises:
            AuthFailed: Okta would not mint a token for these credentials.
            TypeError: The session was not authenticated by service app credentials.

        """
        if not isinstance(session.auth, ServiceAppAuth):
            raise TypeError(f'The session was not authenticated by {self.type}.')
        session.auth.renew()
        self._logger.debug(f'Minted an access token for {self.type}, scopes {" ".join(self._scopes)}.')

    def _token_client(self, host: str, token_session: RateLimitedSession) -> OAuth2Client:
        """Build the client that exchanges a signed assertion for a token.

        Args:
            host: The org root, which the token endpoint hangs off.
            token_session: The session to exchange over.

        Returns:
            OAuth2Client: The client to mint with.

        """
        return OAuth2Client(
            token_endpoint=f'{host}{TOKEN_ENDPOINT}',
            # No alg argument: the key carries it, and the signer reads the key first.
            auth=PrivateKeyJwt(self._client_id, self._signing_key, lifetime=ASSERTION_LIFETIME),
            dpop_bound_access_tokens=self._dpop,
            session=token_session,
        )
