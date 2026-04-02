#!/usr/bin/env python
# File: idp.py
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
Identity Provider entities.

.. _Google Python Style Guide:
   https://google.github.io/styleguide/pyguide.html

"""

import logging
from typing import TYPE_CHECKING, Any

from .core import Entity

if TYPE_CHECKING:
    from oktalib.oktalib import Okta

__author__ = 'Costas Tyfoxylos <ctyfoxylos@schubergphilis.com>'
__docformat__ = 'google'
__date__ = '2018-01-08'
__copyright__ = 'Copyright 2018, Costas Tyfoxylos'
__credits__ = ['Costas Tyfoxylos']
__license__ = 'MIT'
__maintainer__ = 'Costas Tyfoxylos'
__email__ = '<ctyfoxylos@schubergphilis.com>'
__status__ = 'Development'  # "Prototype", "Development", "Production".

LOGGER_BASENAME = 'idp'
LOGGER = logging.getLogger(LOGGER_BASENAME)
LOGGER.addHandler(logging.NullHandler())


class IDP(Entity):
    """Models the identity provider object of okta."""

    @property
    def url(self) -> str:
        """The url of the identity provider.

        Returns:
            string: The url of the identity provider

        """
        return f'{self._okta.api}/idps/{self.id}'

    @property
    def name(self) -> str:
        """The name of the identity provider.

        Returns:
            str: The name of the identity provider

        """
        return self._data.get('name', '')

    @name.setter
    def name(self, value: str) -> bool:
        _new_data = self._data.copy()  # deepcopy
        _new_data['name'] = value
        return self.replace(_new_data)

    @property
    def status(self) -> str:
        """The status of the identity provider.

        Returns:
            str: The status of the identity provider

        """
        return self._data.get('status', '')

    @property
    def protocol(self) -> dict:
        """The protocol of the identity provider.

        Returns:
            dict: The protocol of the identity provider

        """
        return self._data.get('protocol', {})

    @property
    def type(self) -> dict:
        """The type of the identity provider.

        Returns:
            dict: The type of the identity provider

        """
        return self.protocol.get('type', {})

    @property
    def policy(self) -> dict:
        """The policy of the identity provider.

        Returns:
            dict: The policy of the identity provider

        """
        return self._data.get('policy', {})

    @property
    def claims(self) -> bool:
        """Whether to trust claims from this identity provider.

        Returns:
            bool: True if claims are trusted, False otherwise

        """
        return self.policy.get('trustClaims', False)

    @claims.setter
    def claims(self, value: bool) -> bool:
        _new_data = self._data.copy()
        _new_data['policy']['trustClaims'] = value
        return self.replace(_new_data)

    def deactivate(self) -> bool:
        """Deactivates the identity provider.

        Returns:
            bool: True on success, False otherwise

        """
        url = f'{self._okta.api}/idps/{self.id}/lifecycle/deactivate'
        response = self._okta.session.post(url)
        if not response.ok:
            self._logger.error(f'Response: {response.text}')
        else:
            self._update()
        return response.ok

    def activate(self) -> bool:
        """Activates the identity provider.

        Returns:
            bool: True on success, False otherwise

        """
        url = f'{self._okta.api}/idps/{self.id}/lifecycle/activate'
        response = self._okta.session.post(url)
        if not response.ok:
            self._logger.error(f'Response: {response.text}')
        else:
            self._update()
        return response.ok

    def delete(self) -> bool:
        """Deletes the identity provider from okta.

        Returns:
            bool: True on success, False otherwise

        """
        url = f'{self._okta.api}/idps/{self.id}'
        response = self._okta.session.delete(url)
        return response.ok

    def replace(self, new_idp: dict[str, Any]) -> bool:
        """Replaces the identity provider with new data.

        Args:
            new_idp: A dictionary containing the new identity provider data

        Returns:
            bool: True on success, False otherwise

        """
        url = f'{self._okta.api}/idps/{self.id}'
        response = self._okta.session.put(url, json=new_idp)
        if not response.ok:
            self._logger.error(f'Response: {response.text}')
        else:
            self._update()
        return response.ok


class IDPKey:
    """Models an Identity Provider signing key.

    Represents either an RSA or EC (Elliptic Curve) signing key used by an IDP.
    The key type is determined by the 'kty' field.
    """

    def __init__(self, okta_instance: 'Okta', data: dict[str, Any]) -> None:
        """Initialize IDPKey with raw API data.

        Args:
            okta_instance: The Okta instance
            data: Dictionary containing IDP key data from API
        """
        self._data = data
        self._okta = okta_instance

    @property
    def kid(self) -> str:
        """Key ID.

        Returns:
            str: The key ID
        """
        return self._data.get('kid', '')

    @property
    def created(self) -> str:
        """ISO 8601 timestamp of when the key was created.

        Returns:
            str: The creation timestamp
        """
        return self._data.get('created', '')

    @property
    def last_updated(self) -> str:
        """ISO 8601 timestamp of when the key was last updated.

        Returns:
            str: The last updated timestamp
        """
        return self._data.get('lastUpdated', '')

    @property
    def kty(self) -> str:
        """Key type: 'RSA' or 'EC'.

        Returns:
            str: The key type
        """
        return self._data.get('kty', '')

    @property
    def use(self) -> str:
        """Key usage, typically 'sig' for signing.

        Returns:
            str: The key usage
        """
        return self._data.get('use', '')

    @property
    def x5c(self) -> list[str]:
        """X.509 certificate chain.

        Returns:
            list[str]: The certificate chain
        """
        return self._data.get('x5c', [])

    @property
    def x5t_s256(self) -> str | None:
        """SHA-256 certificate thumbprint (corresponds to 'x5t#S256' in API response).

        Returns:
            str | None: The certificate thumbprint
        """
        return self._data.get('x5t#S256')

    @property
    def expires_at(self) -> str | None:
        """ISO 8601 timestamp of when the key expires (optional).

        Returns:
            str | None: The expiration timestamp
        """
        return self._data.get('expiresAt')

    # RSA-specific fields
    @property
    def e(self) -> str | None:
        """RSA public exponent (for RSA keys only).

        Returns:
            str | None: The RSA public exponent
        """
        return self._data.get('e')

    @property
    def n(self) -> str | None:
        """RSA modulus (for RSA keys only).

        Returns:
            str | None: The RSA modulus
        """
        return self._data.get('n')

    # EC-specific fields
    @property
    def alg(self) -> str | None:
        """Algorithm identifier (for EC keys).

        Returns:
            str | None: The algorithm identifier
        """
        return self._data.get('alg')

    @property
    def x(self) -> str | None:
        """EC public key x coordinate (for EC keys only).

        Returns:
            str | None: The x coordinate
        """
        return self._data.get('x')

    @property
    def y(self) -> str | None:
        """EC public key y coordinate (for EC keys only).

        Returns:
            str | None: The y coordinate
        """
        return self._data.get('y')

    @property
    def crv(self) -> str | None:
        """EC curve name, e.g., 'P-521' (for EC keys only).

        Returns:
            str | None: The curve name
        """
        return self._data.get('crv')

    def delete(self) -> bool:
        """Deletes the IDP key from okta.

        Returns:
            bool: True on success, False otherwise

        """
        url = f'{self._okta.api}/idps/credentials/keys/{self.kid}'
        response = self._okta.session.delete(url)
        return response.ok
