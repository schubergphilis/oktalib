#!/usr/bin/env python
# File: entities.py
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
# pylint: disable=too-many-lines
"""
Main code for entities.

.. _Google Python Style Guide:
   https://google.github.io/styleguide/pyguide.html

"""

import json
import logging
import xml.etree.ElementTree as ET
from collections.abc import Generator
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from cachetools import TTLCache, cached

from oktalib.oktalibexceptions import (
    InvalidApplication,
    InvalidGroup,
    InvalidUser,
    UnableToUpdate,
)

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

LOGGER_BASENAME = 'entities'
LOGGER = logging.getLogger(LOGGER_BASENAME)
LOGGER.addHandler(logging.NullHandler())


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

    def __init__(
        self, okta_instance: 'Okta', app_data: dict[str, Any], data: dict[str, Any]
    ) -> None:
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

    def __init__(
        self, okta_instance: 'Okta', app_data: dict[str, Any], data: dict[str, Any]
    ) -> None:
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
        self, okta_instance: 'Okta', client_data: dict[str, Any], data: dict[str, Any]
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


class Group(Entity):
    """Models the group object of okta."""

    def __init__(self, okta_instance: 'Okta', data: dict[str, Any]) -> None:
        self._validate_fields(
            data=data,
            required_fields={'id': ('id',), 'profile.name': ('profile', 'name')},
            error_type=InvalidGroup,
            entity_name='Group',
        )
        super().__init__(okta_instance, data)

    @property
    def id(self) -> str:
        """The id of the group."""
        return self._data['id']

    @property
    def url(self) -> str:
        """The url of the group.

        Returns:
            string: The url of the group

        """
        return f'{self._okta.api}/groups/{self.id}'

    @property
    def type(self) -> str | None:
        """The type of the group.

        Returns:
            string: The name of the type of the group

        """
        return self._data.get('type')

    @property
    def profile(self) -> dict[str, Any] | None:
        """The profile of the group.

        Returns:
            dict: The profile of the group

        """
        return self._data.get('profile')

    @property
    def name(self) -> str:
        """The name of the group.

        Returns:
            string: The name of the group

        """
        return self._data['profile']['name']

    @name.setter
    def name(self, value: str) -> None:
        url = f'{self._okta.api}/groups/{self.id}'
        payload = {'profile': {'name': value, 'description': self.description}}
        response = self._okta.session.put(url, data=json.dumps(payload))
        if not response.ok:
            self._logger.error(f'Setting name failed. Response: {response.text}')
        else:
            self._update()

    @property
    def description(self) -> str | None:
        """The description of the group.

        Returns:
            string: The description of the group

        """
        return self._data.get('profile', {}).get('description')

    @description.setter
    def description(self, value: str) -> None:
        url = f'{self._okta.api}/groups/{self.id}'
        payload = {'profile': {'name': self.name, 'description': value}}
        response = self._okta.session.put(url, data=json.dumps(payload))
        if not response.ok:
            self._logger.error(f'Setting description failed. Response: {response.text}')
        else:
            self._update()

    @property
    def last_membership_updated_at(self) -> datetime | None:
        """The date and time of the group's last membership update.

        Returns:
            datetime: The datetime object of when the group's memberships
                were last updated

        """
        return self._get_date_from_key('lastMembershipUpdated')

    @property
    def object_classes(self) -> tuple[str, ...]:
        """The classes of the group.

        Returns:
            tuple: The tuple of the classes of the group

        """
        value = self._data.get('objectClass')
        if not isinstance(value, list):
            return ()
        return tuple(str(item) for item in value)

    @property
    def users(self) -> Generator['User', None, None]:
        """The users of the group.

        Returns:
            generator: A generator of User objects for the users of the group

        """
        url = self._data.get('_links', {}).get('users', {}).get('href')
        for data in self._okta._get_paginated_url(url):  # noqa: SLF001
            yield User(self._okta, data)

    @property
    def applications(self) -> Generator['Application', None, None]:
        """The applications of the group.

        Returns:
            generator: A generator of Application objects for the applications
                of the group

        """
        url = self._data.get('_links', {}).get('apps', {}).get('href')
        for data in self._okta._get_paginated_url(url):  # noqa: SLF001
            yield Application(self._okta, data)

    def delete(self) -> bool:
        """Deletes the group from okta.

        Returns:
            bool: True on success, False otherwise

        """
        url = f'{self._okta.api}/groups/{self.id}'
        response = self._okta.session.delete(url)
        return response.ok

    def add_to_application_with_label(self, application_label: str) -> bool:
        """Adds the group to an application.

        Args:
            application_label: The label of the application to add the group to

        Returns:
            True on success, False otherwise

        """
        application = self._okta.get_application_by_label(application_label)
        if not application:
            raise InvalidApplication(application_label)
        return application.add_group_by_id(self.id)

    def remove_from_application_with_label(self, application_label: str) -> bool:
        """Removes the group from an application.

        Args:
            application_label: The label of the application to remove the group from

        Returns:
            True on success, False otherwise

        """
        application = self._okta.get_application_by_label(application_label)
        if not application:
            raise InvalidApplication(application_label)
        return application.remove_group_by_id(self.id)

    def add_user_by_login(self, login: str) -> bool:
        """Adds a user to the group.

        Args:
            login: The login of the user to add

        Returns:
            True on success, False otherwise

        """
        user = next(
            (user for user in self._okta.users if (user.login or '').lower() == login.lower()),
            None,
        )
        if not user:
            raise InvalidUser(login)
        url = f'{self._okta.api}/groups/{self.id}/users/{user.id}'
        response = self._okta.session.put(url)
        if not response.ok:
            self._logger.error(f'Adding user failed. Response: {response.text}')
        return response.ok

    def remove_user_by_login(self, login: str) -> bool:
        """Removes a user from the group.

        Args:
            login: The login of the user to remove

        Returns:
            True on success, False otherwise

        """
        user = next((user for user in self._okta.users if user.login == login), None)
        if not user:
            raise InvalidUser(login)
        url = f'{self._okta.api}/groups/{self.id}/users/{user.id}'
        response = self._okta.session.delete(url)
        if not response.ok:
            self._logger.error(f'Removing user failed. Response: {response.text}')
        return response.ok

    def add_user_by_id(self, id_: str) -> bool:
        """Adds a user to the group.

        Args:
            id_: The id of the user to add

        Returns:
            True on success, False otherwise

        """
        url = f'{self._okta.api}/groups/{self.id}/users/{id_}'
        response = self._okta.session.put(url)
        if not response.ok:
            self._logger.error(f'Adding user failed. Response: {response.text}')
        return response.ok

    def remove_user_by_id(self, id_: str) -> bool:
        """Remove a user from the group.

        Args:
            id_: The id of the user to remove

        Returns:
            True on success, False otherwise

        """
        url = f'{self._okta.api}/groups/{self.id}/users/{id_}'
        response = self._okta.session.delete(url)
        if not response.ok:
            self._logger.error(f'Removing user failed. Response: {response.text}')
        return response.ok


class GroupAssignment(Group):
    """Models the group assignment object of okta for apps."""

    def __init__(self, okta_instance: 'Okta', data: dict[str, Any]) -> None:
        self._okta = okta_instance
        self._group_assignment_data = data
        group_data = self._get_group_data()
        Group.__init__(self, okta_instance, group_data)

    @property
    def priority(self) -> int | None:
        """The priority of the group assignment.

        Returns:
            int: The priority of the group.

        """
        return self._group_assignment_data.get('priority')

    def _get_group_data(self) -> dict[str, Any]:
        """The group data of the inherited group that the group assignment refers to.

        Returns:
            group_data (dict): The group data of the parent group that the
                group assignment refers to.

        """
        url = self._group_assignment_data.get('_links', {}).get('group', {}).get('href')
        response = self._okta.session.get(url)
        if not response.ok:
            self._logger.error(response.text)
        return response.json()

    @property
    @cached(cache=TTLCache(maxsize=100, ttl=60))
    def profile_role(self) -> str | None:
        """Profile role."""
        return self._group_assignment_data.get('profile', {}).get('role')

    @property
    @cached(cache=TTLCache(maxsize=100, ttl=60))
    def profile_saml_roles(self) -> list[str]:
        """Profile saml roles."""
        return self._group_assignment_data.get('profile', {}).get('samlRoles', [])


class AdminRole(Entity):
    """Models the admin role object of okta."""

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
            string: The name of the type of the role

        """
        return self._data.get('type')

    @property
    def status(self) -> str | None:
        """The status of the role.

        Returns:
            string: The status of the role

        """
        return self._data.get('status')

    @property
    def created(self) -> datetime | None:
        """The date and time when the role was created.

        Returns:
            datetime: The datetime object of when the role was created

        """
        return self._get_date_from_key('created')

    @property
    def last_updated(self) -> datetime | None:
        """The date and time of the role when it was last updated.

        Returns:
            datetime: The datetime object of when the role was last updated

        """
        return self._get_date_from_key('lastUpdated')

    @property
    def assignment_type(self) -> str | None:
        """The assignment type of the role.

        Returns:
            string: The assignment type the role

        """
        return self._data.get('assignmentType')


class User(Entity):
    """Models the user object of okta."""

    @property
    def url(self) -> str:
        """The url of the user.

        Returns:
            string: The url of the user

        """
        return self._data.get('_links', {}).get('self', {}).get('href') or ''

    @property
    def status(self) -> str | None:
        """The status of the user.

        Returns:
            string: The status of the user

        """
        return self._data.get('status')

    @property
    def activated_at(self) -> datetime | None:
        """The date and time of the users's activation.

        Returns:
            datetime: The datetime object of when the user was activated

        """
        return self._get_date_from_key('activated')

    @property
    def status_changed_at(self) -> datetime | None:
        """The date and time of the users's status change.

        Returns:
            datetime: The datetime object of when the user had last changed status

        """
        return self._get_date_from_key('statusChanged')

    @property
    def last_login_at(self) -> datetime | None:
        """The date and time of the users's last login.

        Returns:
            datetime: The datetime object of when the user last logged in

        """
        return self._get_date_from_key('lastLogin')

    @property
    def password_changed_at(self) -> datetime | None:
        """The date and time of the users's last password change.

        Returns:
            datetime: The datetime object of when the user last changed password

        """
        return self._get_date_from_key('passwordChanged')

    @property
    def first_name(self) -> str | None:
        """The first name of the user.

        Returns:
            string: The first name of the user

        """
        return self._data.get('profile', {}).get('firstName')

    @first_name.setter
    def first_name(self, value: str) -> None:
        """First name setter."""
        self._update_profile_attribute({'firstName': value})

    @property
    def last_name(self) -> str | None:
        """The last name of the user.

        Returns:
            string: The last name of the user

        """
        return self._data.get('profile', {}).get('lastName')

    @last_name.setter
    def last_name(self, value: str) -> None:
        """Last name setter."""
        self._update_profile_attribute({'lastName': value})

    @property
    def manager(self) -> str | None:
        """The manager of the user.

        Returns:
            string: The manager of the user

        """
        return self._data.get('profile', {}).get('manager')

    @manager.setter
    def manager(self, value: str) -> None:
        """Manager setter."""
        self._update_profile_attribute({'manager': value})

    @property
    def display_name(self) -> str | None:
        """The display name of the user.

        Returns:
            string: The display name of the user

        """
        return self._data.get('profile', {}).get('displayName')

    @display_name.setter
    def display_name(self, value: str) -> None:
        """Display name setter."""
        self._update_profile_attribute({'displayName': value})

    @property
    def title(self) -> str | None:
        """The title of the user.

        Returns:
            string: The title of the user

        """
        return self._data.get('profile', {}).get('title')

    @title.setter
    def title(self, value: str) -> None:
        """Title setter."""
        self._update_profile_attribute({'title': value})

    @property
    def locale(self) -> str | None:
        """The locale of the user.

        Returns:
            string: The locale of the user

        """
        return self._data.get('profile', {}).get('locale')

    @locale.setter
    def locale(self, value: str) -> None:
        """Locale setter."""
        self._update_profile_attribute({'locale': value})

    @property
    def employee_number(self) -> str | None:
        """The employee number of the user.

        Returns:
            string: The employee number of the user

        """
        return self._data.get('profile', {}).get('employeeNumber')

    @employee_number.setter
    def employee_number(self, value: str) -> None:
        """Employee number setter."""
        self._update_profile_attribute({'employeeNumber': value})

    @property
    def zip_code(self) -> str | None:
        """The zip code of the user.

        Returns:
            string: The zip code of the user

        """
        return self._data.get('profile', {}).get('zipCode')

    @zip_code.setter
    def zip_code(self, value: str) -> None:
        """Zip number setter."""
        self._update_profile_attribute({'zipCode': value})

    @property
    def city(self) -> str | None:
        """The city of the user.

        Returns:
            string: The city of the user

        """
        return self._data.get('profile', {}).get('city')

    @city.setter
    def city(self, value: str) -> None:
        """City setter."""
        self._update_profile_attribute({'city': value})

    @property
    def street_address(self) -> str | None:
        """The street address of the user.

        Returns:
            string: The street address of the user

        """
        return self._data.get('profile', {}).get('streetAddress')

    @street_address.setter
    def street_address(self, value: str) -> None:
        """Street address setter."""
        self._update_profile_attribute({'streetAddress': value})

    @property
    def contry_code(self) -> str | None:
        """The contry code of the user.

        Returns:
            string: The country code of the user

        """
        return self._data.get('profile', {}).get('countryCode')

    @contry_code.setter
    def contry_code(self, value: str) -> None:
        """Country code setter."""
        self._update_profile_attribute({'countryCode': value})

    @property
    def organization(self) -> str | None:
        """The organization of the user.

        Returns:
            string: The organization of the user

        """
        return self._data.get('profile', {}).get('organization')

    @organization.setter
    def organization(self, value: str) -> None:
        """Organization setter."""
        self._update_profile_attribute({'organization': value})

    @property
    def department(self) -> str | None:
        """The department of the user.

        Returns:
            string: The department of the user

        """
        return self._data.get('profile', {}).get('department')

    @department.setter
    def department(self, value: str) -> None:
        """Department setter."""
        self._update_profile_attribute({'department': value})

    @property
    def primary_phone(self) -> str | None:
        """The primary phone of the user.

        Returns:
            string: The primary phone of the user

        """
        return self._data.get('profile', {}).get('primaryPhone')

    @primary_phone.setter
    def primary_phone(self, value: str) -> None:
        """Primary phone setter."""
        self._update_profile_attribute({'primaryPhone': value})

    @property
    def mobile_phone(self) -> str | None:
        """The mobile phone of the user.

        Returns:
            string: The mobile phone of the user

        """
        return self._data.get('profile', {}).get('mobilePhone')

    @mobile_phone.setter
    def mobile_phone(self, value: str) -> None:
        """Mobile phone setter."""
        self._update_profile_attribute({'mobilePhone': value})

    @property
    def email(self) -> str | None:
        """The email of the user.

        Returns:
            string: The email of the user

        """
        return self._data.get('profile', {}).get('email')

    @email.setter
    def email(self, value: str) -> None:
        """Email setter."""
        self._update_profile_attribute({'email': value})

    @property
    def second_email(self) -> str | None:
        """The second email of the user.

        Returns:
            string: The second email of the user

        """
        return self._data.get('profile', {}).get('secondEmail')

    @second_email.setter
    def second_email(self, value: str) -> None:
        """Second email setter."""
        self._update_profile_attribute({'secondEmail': value})

    @property
    def login(self) -> str | None:
        """The login of the user.

        Returns:
            string: The login of the user

        """
        return self._data.get('profile', {}).get('login')

    @login.setter
    def login(self, value: str) -> None:
        """Login setter."""
        self._update_profile_attribute({'login': value})

    def _update_profile_attribute(self, attribute: dict[str, Any]) -> None:
        """Update a user profile attribute and refresh entity data.

        Args:
            attribute: Dictionary containing the profile attribute to update

        Raises:
            UnableToUpdate: If the profile update fails

        """
        if not self.update_profile({'profile': attribute}):
            raise UnableToUpdate(f'Failed to update with payload {attribute}')
        self._update()

    @property
    def credentials(self) -> dict[str, Any] | None:
        """The credentials of the user.

        Returns:
            dictionary: The credentials of the user

        """
        return self._data.get('credentials')

    @property
    def roles(self) -> Generator[AdminRole, None, None]:
        """Lists the admin roles the user has.

        Returns:
            generator: A generator of roles objects for which the user is member of

        """
        url = f'{self._okta.api}/users/{self.id}/roles'
        for data in self._okta._get_paginated_url(url):  # noqa: SLF001
            yield AdminRole(self._okta, data)

    @property
    def groups(self) -> Generator[Group, None, None]:
        """Lists the groups the user is a member of.

        Returns:
            generator: A generator of Group objects for which the user is member of

        """
        url = f'{self._okta.api}/users/{self.id}/groups'
        for data in self._okta._get_paginated_url(url):  # noqa: SLF001
            yield Group(self._okta, data)

    def delete(self) -> bool:
        """Deletes the user from okta.

        Returns:
            bool: True on success, False otherwise

        """
        # The first request deactivates the user, the second one deletes
        response = self._okta.session.delete(self.url)
        if not response.ok:
            self._logger.error(response.text)
        else:
            self._okta.session.delete(self.url)
            if not response.ok:
                self._logger.error(response.text)
        return response.ok

    def _post_lifecycle(self, url: str, message: str) -> bool:
        """Execute a lifecycle state change via POST request.

        Args:
            url: The lifecycle endpoint URL
            message: Error message to log if the request fails

        Returns:
            bool: True if the lifecycle change succeeded, False otherwise

        """
        response = self._okta.session.post(url)
        if not response.ok:
            self._logger.error(f'{message}\nResponse: {response.text}')
        else:
            self._update()
        return response.ok

    def activate(self) -> bool:
        """Activate the user.

        Returns:
            True on success, False otherwise

        """
        url = f'{self._okta.api}/users/{self.id}/lifecycle/activate?sendEmail=false'
        return self._post_lifecycle(url, 'Activating user failed')

    def deactivate(self) -> bool:
        """Deactivate the user.

        Returns:
            True on success, False otherwise

        """
        url = f'{self._okta.api}/users/{self.id}/lifecycle/deactivate'
        return self._post_lifecycle(url, 'Deactivating user failed')

    def unlock(self) -> bool:
        """Unlocks the user.

        Returns:
            True on success, False otherwise

        """
        url = f'{self._okta.api}/users/{self.id}/lifecycle/unlock'
        return self._post_lifecycle(url, 'Unlocking user failed')

    def expire_password(self) -> bool:
        """Expires the user's password.

        Returns:
            True on success, False otherwise

        """
        url = f'{self._okta.api}/users/{self.id}/lifecycle/expire_password'
        return self._post_lifecycle(url, "Expiring user's password failed")

    def reset_password(self) -> bool:
        """Resets the user's password.

        Returns:
            True on success, False otherwise

        """
        url = f'{self._okta.api}/users/{self.id}/lifecycle/reset_password??sendEmail=false'
        return self._post_lifecycle(url, "Resetting user's password failed")

    def set_temporary_password(self) -> str | None:
        """Sets a temporary password for the user.

        Returns:
            string: Password on success, None otherwise

        """
        url = f'{self._okta.api}/users/{self.id}/lifecycle/expire_password?tempPassword=true'
        response = self._okta.session.post(url)
        if not response.ok:
            error = f'Setting a temporary password failed\nResponse: {response.text}'
            self._logger.error(error)
        else:
            self._update()
        return response.json().get('tempPassword', None)

    def suspend(self) -> bool:
        """Suspends the user.

        Returns:
            True on success, False otherwise

        """
        url = f'{self._okta.api}/users/{self.id}/lifecycle/suspend'
        return self._post_lifecycle(url, 'Suspending user failed')

    def unsuspend(self) -> bool:
        """Unsuspends the user.

        Returns:
            True on success, False otherwise

        """
        url = f'{self._okta.api}/users/{self.id}/lifecycle/unsuspend'
        return self._post_lifecycle(url, 'Un-suspending user failed')

    def update_password(self, old_password: str, new_password: str) -> bool:
        """Changes the user's password.

        Returns:
            True on success, False otherwise

        """
        url = f'{self._okta.api}/users/{self.id}/credentials/change_password'
        payload = {
            'oldPassword': {'value': old_password},
            'newPassword': {'value': new_password},
        }
        response = self._okta.session.post(url, data=json.dumps(payload))
        if not response.ok:
            self._logger.error(response.text)
        return response.ok

    def set_password(self, password: str) -> bool:
        """Set a password for the user.

        Returns:
            True on success, False otherwise

        """
        url = f'{self._okta.api}/users/{self.id}'
        payload = {'credentials': {'password': {'value': password}}}
        response = self._okta.session.put(url, data=json.dumps(payload))
        if not response.ok:
            self._logger.error(response.text)
        return response.ok

    def update_profile(self, new_profile: dict[str, Any]) -> bool:
        """Update a user's profile in okta.

        Args:
            new_profile: A object with attributes to change
                (example: {'profile': {'firstName': 'Test'}})

        Returns:
            Bool: True or False depending on success

        """
        url = f'{self._okta.api}/users/{self.id}'
        response = self._okta.session.post(url, data=json.dumps(new_profile))
        if not response.ok:
            self._logger.error(response.text)
        return response.ok

    def update_security_question(self, password: str, question: str, answer: str) -> bool:
        """Changes the user's security question and answer.

        Returns:
            True on success, False otherwise

        """
        url = f'{self._okta.api}/users/{self.id}/credentials/change_recovery_question'
        payload = {
            'password': {'value': password},
            'recovery_question': {'question': question, 'answer': answer},
        }
        response = self._okta.session.post(url, data=json.dumps(payload))
        if not response.ok:
            self._logger.error(response.text)
        return response.ok


class UserAssignment(Entity):
    """Models the user assignment object of okta for apps."""

    def __init__(self, okta_instance: 'Okta', data: dict[str, Any]) -> None:
        super().__init__(okta_instance, data)
        self._user_assignment_data = self._data

    def _get_user_data(self) -> dict[str, Any]:
        """The parent user data that the user assignment refers to.

        Returns:
            user_data (dict): The parent user data that the user assignment refers to.

        """
        url = self._user_assignment_data.get('_links', {}).get('user', {}).get('href')
        response = self._okta.session.get(url)
        if not response.ok:
            self._logger.error(response.text)
        return response.json()

    @property
    def user(self) -> User:
        """The user that the user assignment refers to."""
        return User(self._okta, self._get_user_data())

    @property
    def group(self) -> Group:
        """The group that the user assignment refers to.

        Returns:
            group (Group): The group that the user assignment refers to.

        """
        url = self._user_assignment_data.get('_links', {}).get('group', {}).get('href')
        response = self._okta.session.get(url)
        if not response.ok:
            self._logger.error(response.text)
        return Group(self._okta, response.json())

    @property
    def email(self) -> str | None:
        """The email of the user.

        Returns:
            email (str): The email of the user.

        """
        return self._user_assignment_data.get('profile', {}).get('email')

    @email.setter
    def email(self, value: str) -> None:
        """Email setter - updates the application user profile email."""
        self._update_profile_attribute({'email': value})

    def _update(self) -> bool:
        """Refresh the assignment data from Okta."""
        url = self._user_assignment_data.get('_links', {}).get('self', {}).get('href')
        response = self._okta.session.get(url)
        if not response.ok:
            self._logger.error(f'Error getting assignment data. Response: {response.text}')
            return False
        self._user_assignment_data = response.json()
        return True

    def update_profile(self, new_profile: dict[str, Any]) -> bool:
        """Update the application user's profile.

        Args:
            new_profile: A object with attributes to change
                (example: {'profile': {'email': 'new@example.com'}})

        Returns:
            Bool: True or False depending on success

        """
        url = self._user_assignment_data.get('_links', {}).get('self', {}).get('href')
        response = self._okta.session.post(url, data=json.dumps(new_profile))
        if not response.ok:
            self._logger.error(response.text)
        return response.ok

    def _update_profile_attribute(self, attribute: dict[str, Any]) -> None:
        """Update a single profile attribute for the application user assignment.

        Args:
            attribute: Dictionary with the attribute to update

        Raises:
            UnableToUpdate: If the update fails

        """
        if not self.update_profile({'profile': attribute}):
            raise UnableToUpdate(f'Failed to update with payload {attribute}')
        self._update()

    @property
    @cached(cache=TTLCache(maxsize=100, ttl=60))
    def profile_role(self) -> str | None:
        """Profile role."""
        return self._user_assignment_data.get('profile', {}).get('role')

    @property
    @cached(cache=TTLCache(maxsize=100, ttl=60))
    def profile_saml_roles(self) -> list[str]:
        """Profile saml roles."""
        return self._user_assignment_data.get('profile', {}).get('samlRoles', [])


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
            yield User(self._okta, data)

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
            yield GroupAssignment(self._okta, data)

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
            yield UserAssignment(self._okta, data)

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
