#!/usr/bin/env python
# File: apps.py
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
Application-related entities (OAuth, SAML metadata).

.. _Google Python Style Guide:
   https://google.github.io/styleguide/pyguide.html

"""

from __future__ import annotations

import json
import logging
import xml.etree.ElementTree as ET
from collections.abc import Generator
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from oktalib.oktalibexceptions import InvalidGroup

from . import groups, users
from .core import Entity

if TYPE_CHECKING:
    from oktalib.oktalib import Okta

    from .groups import Group, GroupAssignment
    from .users import User, UserAssignment

__author__ = 'Yorick Hoorneman <yhoorneman@schubergphilis.com>'
__docformat__ = 'google'
__date__ = '2026-03-24'
__copyright__ = 'Copyright 2026, Yorick Hoorneman'
__credits__ = ['Yorick Hoorneman']
__license__ = 'MIT'
__maintainer__ = 'Yorick Hoorneman'
__email__ = '<yhoorneman@schubergphilis.com>'
__status__ = 'Development'  # "Prototype", "Development", "Production".

LOGGER_BASENAME = 'entities'


class ApplicationType(Enum):
    """Enumeration of Okta application sign-on modes."""

    SAML_2_0 = 'SAML_2_0'
    OPENID_CONNECT = 'OPENID_CONNECT'
    WS_FEDERATION = 'WS_FEDERATION'
    SECURE_PASSWORD_STORE = 'SECURE_PASSWORD_STORE'
    AUTO_LOGIN = 'AUTO_LOGIN'
    BROWSER_PLUGIN = 'BROWSER_PLUGIN'
    BASIC_AUTH = 'BASIC_AUTH'
    BOOKMARK = 'BOOKMARK'
    UNKNOWN = 'UNKNOWN'


@dataclass
class SingleSignOnService:
    """Models a SAML Single Sign-On Service with both POST and Redirect URLs."""

    http_post: str | None = None
    http_redirect: str | None = None


class OAuthApplicationGrant(Entity):
    """Models an OAuth application grant (API scope grant) for an application."""

    def __init__(self, okta_instance: Okta, app_data: dict[str, Any], data: dict[str, Any]) -> None:
        """Initialize an OAuthApplicationGrant instance.

        Args:
            okta_instance: The Okta instance
            app_data: The application data from the API response
            data: The grant data from the API response

        """
        super().__init__(okta_instance, data)
        self._app_data = app_data

    @property
    def status(self) -> str | None:
        """The status of the grant.

        Returns:
            string: The status (ACTIVE or INACTIVE)

        """
        return self._data.get('status')

    @property
    def created(self) -> str | None:
        """The creation timestamp of the grant.

        Returns:
            string: ISO 8601 timestamp

        """
        return self._data.get('created')

    @property
    def created_by(self) -> dict[str, Any] | None:
        """The user or entity that created the grant.

        Returns:
            dictionary: Object with 'id' and 'type' fields

        """
        return self._data.get('createdBy')

    @property
    def last_updated(self) -> str | None:
        """The last update timestamp of the grant.

        Returns:
            string: ISO 8601 timestamp

        """
        return self._data.get('lastUpdated')

    @property
    def issuer(self) -> str | None:
        """The issuer (Okta domain) of the grant.

        Returns:
            string: The Okta domain URL

        """
        return self._data.get('issuer')

    @property
    def client_id(self) -> str | None:
        """The client ID of the application.

        Returns:
            string: The OAuth client ID

        """
        return self._data.get('clientId')

    @property
    def scope_id(self) -> str | None:
        """The scope ID of the grant.

        Returns:
            string: The scope identifier (e.g., 'okta.users.read')

        """
        return self._data.get('scopeId')

    @property
    def source(self) -> str | None:
        """The source of the grant.

        Returns:
            string: The grant source (e.g., 'ADMIN')

        """
        return self._data.get('source')

    @property
    def embedded(self) -> dict[str, Any]:
        """The embedded resources for the grant.

        Returns:
            dictionary: Embedded scope information

        """
        return self._data.get('_embedded', {})

    @property
    def links(self) -> dict[str, Any]:
        """The HATEOAS links for the grant.

        Returns:
            dictionary: Links for app, self, and client

        """
        return self._data.get('_links', {})

    def delete(self) -> bool:
        """Delete the grant.

        Returns:
            bool: True on success, False otherwise

        """
        url = f'{self._okta.api}/apps/{self._app_data.get("id")}/grants/{self.id}'
        response = self._okta.session.delete(url)
        if not response.ok:
            self._logger.error(f'Deleting grant failed. Response: {response.text}')
        return response.ok


class ClientSecret(Entity):
    """Models an OAuth client secret for an application."""

    def __init__(self, okta_instance: Okta, app_data: dict[str, Any], data: dict[str, Any]) -> None:
        """Initialize a ClientSecret instance.

        Args:
            okta_instance: The Okta instance
            app_data: The application data from the API response
            data: The client secret data from the API response

        """
        super().__init__(okta_instance, data)
        self._app_data = app_data

    @property
    def status(self) -> str | None:
        """The status of the client secret.

        Returns:
            string: The status (ACTIVE or INACTIVE)

        """
        return self._data.get('status')

    @property
    def client_secret(self) -> str | None:
        """The client secret value.

        Returns:
            string: The client secret value

        """
        return self._data.get('client_secret')

    @property
    def secret_hash(self) -> str | None:
        """The hash of the client secret.

        Returns:
            string: The secret hash

        """
        return self._data.get('secret_hash')

    @property
    def created(self) -> str | None:
        """The creation timestamp of the client secret.

        Returns:
            string: ISO 8601 timestamp

        """
        return self._data.get('created')

    @property
    def last_updated(self) -> str | None:
        """The last update timestamp of the client secret.

        Returns:
            string: ISO 8601 timestamp

        """
        return self._data.get('lastUpdated')

    @property
    def links(self) -> dict[str, Any]:
        """The HATEOAS links for the client secret.

        Returns:
            dictionary: Links for activate and delete operations

        """
        return self._data.get('_links', {})

    def deactivate(self) -> bool:
        """Deactivate the client secret.

        Returns:
            bool: True on success, False otherwise

        """
        app_id = self._app_data.get('id')
        url = f'{self._okta.api}/apps/{app_id}/credentials/secrets/{self.id}/lifecycle/deactivate'
        response = self._okta.session.post(url)
        if not response.ok:
            self._logger.error(f'Deactivating client secret failed. Response: {response.text}')
        return response.ok

    def delete(self) -> bool:
        """Delete the client secret.

        Returns:
            bool: True on success, False otherwise

        """
        url = f'{self._okta.api}/apps/{self._app_data.get("id")}/credentials/secrets/{self.id}'
        response = self._okta.session.delete(url)
        if not response.ok:
            self._logger.error(f'Deleting client secret failed. Response: {response.text}')
        return response.ok


class ClientRole(Entity):
    """Models an OAuth client role (admin role assigned to an OAuth client)."""

    def __init__(
        self, okta_instance: Okta, client_data: dict[str, Any], data: dict[str, Any]
    ) -> None:
        """Initialize a ClientRole instance.

        Args:
            okta_instance: The Okta instance
            client_data: The client/application data from the API response
            data: The role data from the API response

        """
        super().__init__(okta_instance, data)
        self._client_data = client_data

    @property
    def label(self) -> str | None:
        """The label of the role.

        Returns:
            string: The label of the role

        """
        return self._data.get('label')

    @property
    def type(self) -> str | None:
        """The type of the role.

        Returns:
            string: The role type (e.g., 'HELP_DESK_ADMIN')

        """
        return self._data.get('type')

    @property
    def status(self) -> str | None:
        """The status of the role.

        Returns:
            string: The status (ACTIVE or INACTIVE)

        """
        return self._data.get('status')

    @property
    def created(self) -> str | None:
        """The creation timestamp of the role.

        Returns:
            string: ISO 8601 timestamp

        """
        return self._data.get('created')

    @property
    def last_updated(self) -> str | None:
        """The last update timestamp of the role.

        Returns:
            string: ISO 8601 timestamp

        """
        return self._data.get('lastUpdated')

    @property
    def assignment_type(self) -> str | None:
        """The assignment type of the role.

        Returns:
            string: The assignment type (e.g., 'CLIENT')

        """
        return self._data.get('assignmentType')

    @property
    def links(self) -> dict[str, Any]:
        """The HATEOAS links for the role.

        Returns:
            dictionary: Links for assignee and other operations

        """
        return self._data.get('_links', {})

    def delete(self) -> bool:
        """Delete the client role.

        Returns:
            bool: True on success, False otherwise

        """
        client_id = self._client_data.get('id')
        url = f'{self._okta.host}/oauth2/v1/clients/{client_id}/roles/{self.id}'
        response = self._okta.session.delete(url)
        if not response.ok:
            self._logger.error(f'Deleting client role failed. Response: {response.text}')
        return response.ok


class SAMLMetadata:
    """Models SAML metadata for an Identity Provider.

    Parses SAML metadata XML and provides structured access to the data.
    """

    # XML namespaces
    NAMESPACES = {
        'md': 'urn:oasis:names:tc:SAML:2.0:metadata',
        'ds': 'http://www.w3.org/2000/09/xmldsig#',
    }

    def __init__(self, xml_data: str) -> None:
        """Initialize SAMLMetadata with raw XML string.

        Args:
            xml_data: Raw SAML metadata XML string
        """
        self._data = xml_data
        self._root = ET.fromstring(xml_data)
        self._logger = logging.getLogger(f'{LOGGER_BASENAME}.SAMLMetadata')

    @property
    def entity_id(self) -> str:
        """The entity ID from the EntityDescriptor.

        Returns:
            str: The entity ID
        """
        return self._root.get('entityID', '')

    @property
    def want_authn_requests_signed(self) -> bool:
        """Whether authentication requests should be signed.

        Returns:
            bool: True if requests should be signed, False otherwise
        """
        idp_descriptor = self._root.find('md:IDPSSODescriptor', self.NAMESPACES)
        if idp_descriptor is not None:
            value = idp_descriptor.get('WantAuthnRequestsSigned', 'false')
            return value.lower() == 'true'
        return False

    @property
    def protocol_support_enumeration(self) -> str | None:
        """The protocol support enumeration.

        Returns:
            str | None: The protocol support string
        """
        idp_descriptor = self._root.find('md:IDPSSODescriptor', self.NAMESPACES)
        if idp_descriptor is not None:
            return idp_descriptor.get('protocolSupportEnumeration')
        return None

    @property
    def x509_certificate(self) -> str | None:
        """The X.509 certificate for signing.

        Returns:
            str | None: The X.509 certificate string
        """
        cert_path = './/md:KeyDescriptor[@use="signing"]//ds:X509Certificate'
        cert_elem = self._root.find(cert_path, self.NAMESPACES)
        if cert_elem is not None and cert_elem.text:
            return cert_elem.text.strip()
        return None

    @property
    def name_id_formats(self) -> list[str]:
        """The supported NameID formats.

        Returns:
            list[str]: List of NameID format URNs
        """
        formats = []
        for format_elem in self._root.findall('.//md:NameIDFormat', self.NAMESPACES):
            if format_elem.text:
                formats.append(format_elem.text.strip())
        return formats

    @property
    def single_sign_on_services(self) -> SingleSignOnService:
        """Returns a SingleSignOnService with both HTTP-POST and
        HTTP-Redirect URLs if present.
        """
        sso_services = {
            sso.get('Binding', ''): sso.get('Location', '')
            for sso in self._root.findall('.//md:SingleSignOnService', self.NAMESPACES)
        }
        return SingleSignOnService(
            http_post=sso_services.get('urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST'),
            http_redirect=sso_services.get('urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect'),
        )


class Application(Entity):
    """Models the apps in okta."""

    @property
    def url(self) -> str:
        """The url of the application.

        Returns:
            string: The url of the application

        """
        return f'{self._okta.api}/apps/{self.id}'

    @property
    def name(self) -> str | None:
        """The name of the application.

        Returns:
            basestring: The name of the application

        """
        return self._data.get('name')

    @property
    def label(self) -> str | None:
        """The label of the application.

        Returns:
            basestring: The label of the application

        """
        return self._data.get('label')

    @property
    def status(self) -> str | None:
        """The status of the application.

        Returns:
            basestring: The status of the application

        """
        return self._data.get('status')

    @property
    def accessibility(self) -> dict[str, Any] | None:
        """The accessibility of the application.

        Returns:
            dictionary: The accessibility of the application

        """
        return self._data.get('accessibility')

    @property
    def visibility(self) -> dict[str, Any] | None:
        """The visibility of the application.

        Returns:
            dictionary: The visibility of the application

        """
        return self._data.get('visibility')

    @property
    def features(self) -> dict[str, Any] | None:
        """The features of the application.

        Returns:
            dictionary: The features of the application

        """
        return self._data.get('features')

    @property
    def sign_on_mode(self) -> str:
        """The sign on mode of the application.

        Returns:
            basestring: The sign on mode of the application

        """
        return self._data.get('signOnMode', '')

    @property
    def credentials(self) -> dict[str, Any]:
        """The credentials of the application.

        Returns:
            dictionary: The credentials of the application

        """
        return self._data.get('credentials', {})

    def delete(self) -> bool:
        """Deletes the application from okta.

        Returns:
            bool: True on success, False otherwise

        """
        url = f'{self._okta.api}/apps/{self.id}'
        response = self._okta.session.delete(url)
        return response.ok

    @property
    def settings(self) -> dict[str, Any] | None:
        """The settings of the application.

        Returns:
            dictionary: The settings of the application

        """
        return self._data.get('settings', {}).get('app')

    @property
    def notification_settings(self) -> dict[str, Any] | None:
        """The notification settings of the application.

        Returns:
            dictionary: The notification settings of the application

        """
        return self._data.get('settings', {}).get('notifications')

    @property
    def users(self) -> Generator[User, None, None]:
        """The users of the application.

        Returns:
            generator: A generator of User objects for the users of the application

        """
        url = self._data.get('_links', {}).get('users', {}).get('href')
        for data in self._okta._get_paginated_url(url):  # noqa: SLF001
            yield users.User(self._okta, data)

    @property
    def groups(self) -> Generator[Group | None, None, None]:
        """The groups of the application.

        Returns:
            generator: A generator of Group objects for the groups of the application

        """
        url = self._data.get('_links', {}).get('groups', {}).get('href')
        for group in self._okta._get_paginated_url(url):  # noqa: SLF001
            yield self._okta.get_group_by_id(group.get('id', ''))

    @property
    def group_assignments(self) -> Generator[GroupAssignment, None, None]:
        """The group assignments to the application.

        Returns:
            generator: A generator of group assignments for application

        """
        url = self._data.get('_links', {}).get('groups', {}).get('href')
        for data in self._okta._get_paginated_url(url):  # noqa: SLF001
            yield groups.GroupAssignment(self._okta, data)

    def get_group_assignment_by_group_name(self, name: str) -> GroupAssignment | None:
        """Retrieves a group assignment by a group name.

        Args:
            name: The name of the group assignment to retrieve.

        Returns:
            group_assignment (GroupAssignment): The matching group assignment
                if found else None.

        """
        return next((group for group in self.group_assignments if group.name == name), None)

    @property
    def user_assignments(self) -> Generator[UserAssignment, None, None]:
        """The user assignments to the application.

        Returns:
            generator: A generator of user assignments for application

        """
        url = self._data.get('_links', {}).get('users', {}).get('href')
        for data in self._okta._get_paginated_url(url):  # noqa: SLF001
            yield users.UserAssignment(self._okta, data)

    def get_user_assignment_by_email(self, email: str) -> UserAssignment | None:
        """Retrieves a user assignment by a user email.

        Args:
            email: The email of the user assignment to retrieve.

        Returns:
            user_assignment (UserAssignment): The matching user assignment
                if found else None.

        """
        return next(
            (user for user in self.user_assignments if (user.email or '').lower() == email.lower()),
            None,
        )

    def activate(self) -> bool:
        """Activates the application.

        Returns:
            bool: True on success, False otherwise

        """
        if self.status == 'ACTIVE':
            return True
        url = self._data.get('_links', {}).get('activate').get('href')
        response = self._okta.session.post(url)
        if not response.ok:
            self._logger.error(f'Response: {response.text}')
        else:
            self._update()
        return response.ok

    def deactivate(self) -> bool:
        """Deactivates the application.

        Returns:
            bool: True on success, False otherwise

        """
        if self.status == 'INACTIVE':
            return True
        url = self._data.get('_links', {}).get('deactivate').get('href')
        response = self._okta.session.post(url)
        if not response.ok:
            self._logger.error(f'Response: {response.text}')
        else:
            self._update()
        return response.ok

    def add_group_by_id(self, group_id: str) -> bool:
        """Adds a group to the application.

        Args:
            group_id: The id of the group to add

        Returns:
            True on success, False otherwise

        """
        url = f'{self._okta.api}/apps/{self.id}/groups/{group_id}'
        response = self._okta.session.put(url)
        if not response.ok:
            self._logger.error(f'Adding group failed. Response: {response.text}')
        return response.ok

    def add_group_by_name(self, group_name: str) -> bool:
        """Adds a group to the application.

        Args:
            group_name: The name of the group to add

        Returns:
            True on success, False otherwise

        """
        group = self._okta.get_group_by_name(group_name)
        if not group:
            raise InvalidGroup(group_name)
        url = f'{self._okta.api}/apps/{self.id}/groups/{group.id}'
        response = self._okta.session.put(url, data=json.dumps({}))
        if not response.ok:
            self._logger.error(f'Adding group failed. Response: {response.text}')
        return response.ok

    def remove_group_by_id(self, group_id: str) -> bool:
        """Removes a group from the application.

        Args:
            group_id: The id of the group to remove

        Returns:
            True on success, False otherwise

        """
        url = f'{self._okta.api}/apps/{self.id}/groups/{group_id}'
        response = self._okta.session.delete(url)
        if not response.ok:
            self._logger.error(f'Removing group failed. Response: {response.text}')
        return response.ok

    def remove_group_by_name(self, group_name: str) -> bool:
        """Removes a group from the application.

        Args:
            group_name: The name of the group to remove

        Returns:
            True on success, False otherwise

        """
        group = self._okta.get_group_by_name(group_name)
        if not group:
            raise InvalidGroup(group_name)
        url = f'{self._okta.api}/apps/{self.id}/groups/{group.id}'
        response = self._okta.session.delete(url)
        if not response.ok:
            self._logger.error(f'Removing group failed. Response: {response.text}')
        return response.ok


class SAMLApplication(Application):
    """Models the SAML apps in okta."""

    @property
    def sso_url(self) -> str | None:
        """The SSO URL of the application.

        Returns:
            string: The SSO URL of the application

        """
        return self.settings.get('ssoUrl') if self.settings else None

    @property
    def sign_on_settings(self) -> dict[str, Any] | None:
        """The sign on settings of the application.

        Returns:
            dictionary: The sign on settings of the application

        """
        return self._data.get('settings', {}).get('signOn')

    @property
    def audience(self) -> str | None:
        """The audience of the application.

        Returns:
            string: The audience of the application

        """
        return self.settings.get('audience') if self.settings else None

    def assign_group_to_saml_user_roles(
        self, group_id: str, role: str, saml_roles: list[str]
    ) -> bool:
        """Assigns an okta group to an okta application with saml user roles.

        Args:
            group_id: The id of the group to be associated
            role: The aws role that okta uses to assume SAML roles in other accounts
            saml_roles: the SAML Roles to be assumed

        Returns:
            Bool: The status of the assignment( True or False )

        """
        url = f'{self._okta.api}/apps/{self.id}/groups/{group_id}'
        payload = {'id': group_id, 'profile': {'role': role, 'samlRoles': saml_roles}}
        response = self._okta.session.put(url, json=payload)
        if not response.ok:
            self._logger.error(
                f'Assigning group to the saml user roles failed. Response: {response.text}'
            )
        return response.ok

    def get_associated_saml_roles(self) -> list[str]:
        """Returns the Saml IAM Roles associated with the application.

        Returns:
            list: List of saml iam roles

        """
        url = f'{self._okta.api}/internal/apps/{self.id}/types'
        response = self._okta.session.get(url)
        if not response.ok:
            self._logger.error(f'Response: {response.text}')
            return []
        return response.json().get('SamlIamRole', [])

    @property
    def metadata_url(self) -> str | None:
        """The metadata URL of the application.

        Returns:
            str | None: The metadata URL of the application

        """
        return self._data.get('_links', {}).get('metadata', {}).get('href')

    def metadata(self) -> SAMLMetadata | None:
        """The metadata of the application.

        Returns:
            SAMLMetadata | None: The metadata of the application

        """
        if not self.metadata_url:
            self._logger.info('This application does not have a metadata URL.')
            return None
        return self._okta.get_application_metadata(
            self.id, self.credentials.get('signing', {}).get('kid')
        )


class APIServiceApp(Application):
    """Models the API Service apps in okta."""

    MAX_CLIENT_SECRETS = 2  # Maximum number of client secrets allowed per application

    @property
    def api_endpoint(self) -> str:
        """The API endpoint of the application.

        Returns:
            string: The API endpoint of the application

        """
        return self._data.get('settings', {}).get('apiEndpoint', '')

    @property
    def client_authentication(self) -> str:
        """The client authentication method of the application.

        Returns:
            string: The client authentication method of the application

        """
        return self.credentials.get('oauthClient', {}).get('token_endpoint_auth_method', '')

    @property
    def client_secrets(self) -> list[ClientSecret] | None:
        """The client secrets of the application.

        Returns:
            list[ClientSecret] | None: The client secrets of the application


        """
        url = f'{self._okta.api}/apps/{self.id}/credentials/secrets'
        response = self._okta.session.get(url)
        if not response.ok:
            self._logger.error(f'Retrieving client secrets failed. Response: {response.text}')
            return None
        return [
            ClientSecret(self._okta, self._data, client_secret) for client_secret in response.json()
        ]

    def create_client_secrets(self) -> ClientSecret | None:
        """Creates new client secrets for the application.

        Note:
            Applications can have a maximum of MAX_CLIENT_SECRETS client secrets at any time.

        Returns:
            ClientSecret | None: The newly created client secrets of the application

        """
        url = f'{self._okta.api}/apps/{self.id}/credentials/secrets'
        response = self._okta.session.post(url)
        if not response.ok:
            # Check if error is due to maximum secrets limit
            error_msg = f'Creating client secrets failed. Response: {response.text}'
            if response.status_code == 400 and 'maximum' in response.text.lower():
                error_msg = (
                    f'Creating client secrets failed: Maximum of {self.MAX_CLIENT_SECRETS} '
                    f'client secrets reached. Response: {response.text}'
                )
            self._logger.error(error_msg)
            return None
        return ClientSecret(self._okta, self._data, response.json())

    def add_grant(self, scope_id: str) -> OAuthApplicationGrant | None:
        """Adds an API scope to the application.

        Args:
            scope_id: The id of the API scope to add

        Returns:
            OAuthApplicationGrant | None: The newly created OAuth application grant
                on success, None otherwise
        """
        url = f'{self._okta.api}/apps/{self.id}/grants'
        payload = {'issuer': self._okta.host, 'scopeId': scope_id}
        response = self._okta.session.post(url, json=payload)
        if not response.ok:
            self._logger.error(f'Adding grants failed. Response: {response.text}')
            return None
        self._update()
        return OAuthApplicationGrant(self._okta, self._data, response.json())

    def add_grants(self, scope_ids: list[str]) -> list[OAuthApplicationGrant | None]:
        """Adds API scopes to the application.

        Args:
            scope_ids: The ids of the API scopes to add

        Returns:
            list[OAuthApplicationGrant | None]: The newly created OAuth application grants
                on success, None for failed additions
        """
        return [self.add_grant(scope_id) for scope_id in scope_ids]

    @property
    def grants(self) -> Generator[OAuthApplicationGrant, None, None]:
        """The API scopes granted to the application.

        Returns:
            generator: A generator of OAuthApplicationGrant objects for the grants
                of the application

        """
        url = f'{self._okta.api}/apps/{self.id}/grants'
        for data in self._okta._get_paginated_url(url):  # noqa: SLF001
            yield OAuthApplicationGrant(self._okta, self._data, data)

    @property
    def client_roles(self) -> Generator[ClientRole, None, None]:
        """The client roles (Okta admin roles) assigned to the application.

        Note:
            Client roles are Okta admin roles that grant administrative privileges
            to the application.

        Returns:
            generator: A generator of ClientRole objects for the client roles of the application

        """
        url = f'{self._okta.host}/oauth2/v1/clients/{self.id}/roles'
        for data in self._okta._get_paginated_url(url):  # noqa: SLF001
            yield ClientRole(self._okta, self._data, data)

    def add_client_role(self, role_type: str) -> ClientRole | None:
        """Adds a client role (Okta admin role) to the application.

        Note:
            Client roles are Okta admin roles that grant administrative privileges
            to the application.

        Args:
            role_type: The type of the Okta admin role to add (e.g. "MOBILE_ADMIN")

        Returns:
            ClientRole | None: The newly created client role on success, None otherwise
        """
        url = f'{self._okta.host}/oauth2/v1/clients/{self.id}/roles'
        payload = {'type': role_type}
        response = self._okta.session.post(url, json=payload)
        if not response.ok:
            self._logger.error(f'Adding client role failed. Response: {response.text}')
            return None
        self._update()
        return ClientRole(self._okta, self._data, response.json())

    def add_client_roles(self, role_types: list[str]) -> list[ClientRole | None]:
        """Adds client roles (Okta admin roles) to the application.

        Note:
            Client roles are Okta admin roles that grant administrative privileges
            to the application.

        Args:
            role_types: The types of Okta admin roles to add
                (e.g. ["MOBILE_ADMIN", "MOBILE_APP"])

        Returns:
            list[ClientRole | None]: The newly created client roles on success,
                None for failed additions
        """
        return [self.add_client_role(role_type) for role_type in role_types]

    @property
    def jwks_uri(self) -> str | None:
        """The JWKS URI of the application.

        Returns:
            string: The JWKS URI of the application

        """
        return self._data.get('settings', {}).get('oauthClient', {}).get('jwks_uri', '')

    @property
    def jwks(self) -> dict[str, Any] | None:
        """The JWKS of the application.

        Returns:
            dictionary: The JWKS of the application

        """
        return self.credentials.get('oauthClient', {}).get('jwks')

    @property
    def is_public_keys_configured(self) -> bool:
        """Indicates whether public keys are configured for the application.

        Returns:
            bool: True if public keys are configured, False otherwise

        """
        return bool(self.jwks_uri or self.jwks)

    def add_public_keys_by_public_url(self, jwks_uri: str) -> bool:
        """Adds public keys to the application using a JWKS URI.

        Args:
            jwks_uri: The JWKS URI to fetch keys from dynamically

        Returns:
            bool: True on success, False otherwise
        """
        payload = deepcopy(self._data)
        payload.setdefault('settings', {}).setdefault('oauthClient', {})['jwks_uri'] = jwks_uri
        url = f'{self._okta.api}/apps/{self.id}'
        response = self._okta.session.put(url, json=payload)
        if not response.ok:
            self._logger.error(
                f'Adding public keys with JWKS URI failed. Response: {response.text}'
            )
            return False
        self._update()
        return response.ok

    def add_public_keys_by_jwks(self, jwks: dict[str, Any]) -> bool:
        """Adds public keys to the application using a JWKS.

        Args:
            jwks: The JWKS containing the public keys

        Returns:
            bool: True on success, False otherwise
        """
        url = f'{self._okta.api}/apps/{self.id}/credentials/jwks'
        response = self._okta.session.post(url, json=jwks)
        if not response.ok:
            self._logger.error(f'Adding public keys with JWKS failed. Response: {response.text}')
            return False
        self._update()
        return response.ok

    def _enable_public_private_key_authentication(self) -> bool:
        """Enable public/private key JWT authentication for the application.

        This changes the token endpoint authentication method to 'private_key_jwt'
        and removes any client secret credentials.

        Returns:
            bool: True on success, False otherwise

        """
        payload = deepcopy(self._data)
        oauth_client = payload.setdefault('credentials', {}).setdefault('oauthClient', {})
        oauth_client['token_endpoint_auth_method'] = 'private_key_jwt'
        oauth_client.pop('client_secret', None)

        url = f'{self._okta.api}/apps/{self.id}'
        response = self._okta.session.put(url, json=payload)
        if not response.ok:
            self._logger.error(
                f'Enabling public key authentication failed. Response: {response.text}'
            )
            return False
        self._update()
        return response.ok
