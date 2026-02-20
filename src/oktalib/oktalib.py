#!/usr/bin/env python
# File: oktalib.py
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
Main code for oktalib.

.. _Google Python Style Guide:
   https://google.github.io/styleguide/pyguide.html

"""

import json
import logging
from collections.abc import Generator
from typing import Any

import backoff
from requests import Response, Session

from oktalib.entities.entities import IDP, IDPKey, SAMLMetadata

from .entities import AdminRole, Application, Group, User
from .oktalibexceptions import (
    ApiLimitReached,
    AuthFailed,
    InvalidApplication,
    InvalidGroup,
    InvalidIDPKey,
    ServerError,
)

__author__ = 'Costas Tyfoxylos <ctyfoxylos@schubergphilis.com>'
__docformat__ = 'google'
__date__ = '2018-01-08'
__copyright__ = 'Copyright 2018, Costas Tyfoxylos'
__credits__ = ['Costas Tyfoxylos']
__license__ = 'MIT'
__maintainer__ = 'Costas Tyfoxylos'
__email__ = '<ctyfoxylos@schubergphilis.com>'
__status__ = 'Development'  # "Prototype", "Development", "Production".

# This is the main prefix used for logging
LOGGER_BASENAME = 'oktalib'
LOGGER = logging.getLogger(LOGGER_BASENAME)
LOGGER.addHandler(logging.NullHandler())


class Okta:
    """Models the api of okta."""

    def __init__(self, host: str, token: str) -> None:
        """Initializes the Okta object.

        Args:
            host: The host of the okta instance, e.g. https://dev.oktapreview.com
            token: The API token to use for authentication

        """
        logger_name = f'{LOGGER_BASENAME}.{self.__class__.__name__}'
        self._logger = logging.getLogger(logger_name)
        self.host = host
        self.api = f'{host}/api/v1'
        self.token = token
        self.session = self._setup_session()
        self._monkey_patch_session()

    def _setup_session(self) -> Session:
        """Sets up the session for the Okta object.

        Returns:
            Session: The session object with the correct headers and authentication.

        """
        session = Session()
        session.get(self.host)
        session.headers.update(
            {
                'accept': 'application/json',
                'content-type': 'application/json',
                'authorization': f'SSWS {self.token}',
            }
        )
        url = f'{self.api}/users/me/'
        response = session.get(url)
        if not response.ok:
            raise AuthFailed(response.content)
        return session

    def _monkey_patch_session(self) -> None:
        """Gets original request method and overrides it with the patched one.

        Returns:
            Response: Response instance.

        """
        self.session.original_request = self.session.request  # type: ignore[attr-defined]
        self.session.request = self._patched_request  # type: ignore[assignment]

    @backoff.on_exception(backoff.expo, ApiLimitReached, max_time=60)
    def _patched_request(self, method: str, url: str, **kwargs: Any) -> Response:
        """Patch the original request method from requests.Sessions library.

        Args:
            method (str): HTTP verb as string.
            url (str): string.
            kwargs: keyword arguments.

        Raises:
            ApiLimitReached: Raised when the Okta API limit is reached.

        Returns:
            Response: Response instance.

        """
        self._logger.debug(
            f'Using patched request for method {method}, url {url}, kwargs {kwargs}'
        )
        response = self.session.original_request(  # type: ignore[attr-defined]
            method, url, **kwargs
        )
        if response.status_code == 429:
            self._logger.warning('Api is exhausted for endpoint, backing off.')
            raise ApiLimitReached
        return response

    @property
    def idps(self) -> Generator[IDP, None, None]:
        """The identity providers configured in okta.

        Returns:
            generator: The generator of identity providers configured in okta

        """
        url = f'{self.api}/idps'
        for data in self._get_paginated_url(url):
            yield IDP(self, data)

    def get_idp_by_name(self, name: str) -> IDP | None:
        """Retrieves the first identity provider by name.

        Args:
            name: The name of the identity provider to retrieve

        Returns:
            IDP: The identity provider if a match is found else None

        """
        return next(
            (idp for idp in self.idps if idp.name == name),
            None,
        )

    def get_idp_keys(self) -> Generator[IDPKey, None, None]:
        """Retrieves the identity provider by id.

        Args:
            idp_id: The id of the identity provider to retrieve

        Returns:
            generator: The generator of IDPKey instances

        """
        url = f"{self.api}/idps/credentials/keys"
        for data in self._get_paginated_url(url):
            yield IDPKey(self, data)

    def get_idp_key_by_kid(self, kid: str) -> IDPKey | None:
        """Retrieves the identity provider by key ID.

        Args:
            kid: The key ID of the identity provider to retrieve

        Returns:
            IDPKey: The identity provider key if a match is found else None

        """
        url = f"{self.api}/idps/credentials/keys/{kid}"
        response = self.session.get(url)
        if not response.ok:
            self._logger.error(response.json())
        return IDPKey(self, response.json()) if response.ok else None

    def delete_idp_key(self, kid: str) -> bool:
        """Deletes an IDP key from okta.

        Args:
            kid: The key ID of the IDP key to delete

        Returns:
            bool: True on success, False otherwise

        Raises:
            InvalidIDPKey: The IDP key provided as argument does not exist.

        """
        idp_key = self.get_idp_key_by_kid(kid)
        if not idp_key:
            raise InvalidIDPKey(kid)
        return idp_key.delete()

    def create_saml_idp(
        self,
        name: str,
        okta_idp_issuer_url: str,
        okta_idp_sso_url: str,
        users_regex_filter: str = "",
        kid: str | None = None,
        idp_username: str = "idpuser.subjectNameId",
        trust_claims: bool = True,
        provisioning_action: str = "DISABLED",
        provisioning_profile_master: bool = False,
        account_link_action: str = "AUTO",
        account_link_group_filter: list | None = None,
        account_link_exclude_users: list | None = None,
        account_link_exclude_admins: bool = False,
        account_matching: str = "USERNAME",
        maxClockSkew: int = 120000,
    ) -> IDP | None:
        """Creates an identity provider in okta.

        Args:
            name: The name of the identity provider to create
            okta_idp_issuer_url: The issuer URL of the identity provider to
                create
            okta_idp_sso_url: The SSO URL of the identity provider to create
            users_regex_filter: The regex filter for users that are allowed
                to use the identity provider
            kid: The key ID of the signing key to use for the identity
                provider to create (if not provided, no signing key will be
                used)
            idp_username: The template for the username to use for the
                identity provider to create (default is
                "idpuser.subjectNameId")
            trust_claims: Whether to trust claims from this identity
                provider (default is True)
            provisioning_action: The provisioning action for this identity
                provider (default is "DISABLED", other options are "AUTO"
                and "IMPORT")
            provisioning_profile_master: Whether this identity provider is
                the profile master (default is False)
            account_link_action: The account link action for this identity
                provider (default is "AUTO", other options are "AUTO",
                "AUTO_GROUPS", "IMPORT", "IMPORT_GROUPS", "DISABLED")
            account_matching: The account matching type for this identity
                provider (default is "USERNAME", other options are
                "USERNAME_OR_EMAIL")
            account_link_group_filter: Only users in the specified groups
                will be included for account linking.
            account_link_exclude_users: Any user specified will be excluded
                from account linking.
            account_link_exclude_admins: Users with any admin roles or
                privileges will be excluded from account linking.
            maxClockSkew: The maximum allowed clock skew in milliseconds
                (default is 120000)
        Returns:
            IDP: The created identity provider on success, None otherwise

        """
        # flow
        # get metadata from saml app on the IDP tenant
        # get_keystore_key_by_cert -- if any key in the keystore has a
        # property x5c with the same value as the x509 value from the
        # metadata
        # if key not found, create new key with the x509 value from the
        # metadata
        # create saml idp with issuer and sso from saml app (metadata) and
        # kid from before.
        # name, Trust claims from this identity provider, idp_username,
        # If no match is found -> create new user || redirect to okta sign-in page
        # should be settable:
        # SAML Protocol Settings
        # IdP Issuer URI
        # IdP Single Sign-On URL
        # IdP Signature Certificate

        account_link_filter = {
            **(
                {"groups": {"include": account_link_group_filter}}
                if account_link_group_filter
                else {}
            ),
            **(
                {
                    "users": {
                        **(
                            {"exclude": account_link_exclude_users}
                            if account_link_exclude_users
                            else {}
                        ),
                        **(
                            {"excludeAdmins": True}
                            if account_link_exclude_admins
                            else {}
                        ),
                    }
                }
                if account_link_exclude_users or account_link_exclude_admins
                else {}
            ),
        }

        url = f"{self.api}/idps"
        payload: dict[str, Any] = {
            "type": "SAML2",
            "name": name,
            "protocol": {
                "type": "SAML2",
                "endpoints": {
                    "sso": {
                        "url": okta_idp_sso_url,
                        "binding": "HTTP-POST",
                        "destination": okta_idp_issuer_url,
                    },
                    "slo": {
                        "url": f"{okta_idp_issuer_url}/slo",
                        "binding": "HTTP-POST",
                    },
                    "acs": {"binding": "HTTP-POST", "type": "INSTANCE"},
                },
                "settings": {"participateSlo": True},
                "algorithms": {
                    "request": {
                        "signature": {"algorithm": "SHA-256", "scope": "REQUEST"}
                    },
                    "response": {"signature": {"algorithm": "SHA-256", "scope": "ANY"}},
                },
                "credentials": {
                    "trust": {
                        "issuer": okta_idp_issuer_url,
                        "audience": "",
                        "kid": kid,
                        "additionalKids": ["additional-key-id"],
                    }
                },
            },
            "policy": {
                "provisioning": {
                    "action": provisioning_action,
                    "profileMaster": provisioning_profile_master,
                    "groups": {"action": "NONE"},
                    "conditions": {
                        "deprovisioned": {"action": "NONE"},
                        "suspended": {"action": "NONE"},
                    },
                },
                "accountLink": {
                    "filter": account_link_filter,
                    "action": account_link_action,
                },
                "subject": {
                    "userNameTemplate": {"template": idp_username},
                    "format": ["urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified"],
                    "filter": users_regex_filter,
                    "matchType": account_matching,
                },
                "trustClaims": trust_claims,
                "maxClockSkew": maxClockSkew,
            },
        }
        response = self.session.post(url=url, json=payload)
        if not response.ok:
            self._logger.error(response.json())
        return IDP(self, response.json()) if response.ok else None

    def get_idp_by_id(self, idp_id: str) -> IDP | None:
        """Retrieves the identity provider by id.

        Args:
            idp_id: The id of the identity provider to retrieve

        Returns:
            IDP: The identity provider if a match is found else None

        """
        url = f'{self.api}/idps/{idp_id}'
        response = self.session.get(url)
        if not response.ok:
            self._logger.error(response.json())
        return IDP(self, response.json()) if response.ok else None

    def search_idps_by_name(self, name: str) -> list[IDP]:
        """Retrieves the identity providers (of any type) by name.

        Args:
            name: The name of the identity providers to retrieve

        Returns:
            list: A list of identity providers if a match is found else an empty list

        """
        url = f'{self.api}/idps?q={name}'
        response = self.session.get(url)
        if not response.ok:
            self._logger.error(response.json())
        return [IDP(self, data) for data in response.json()] if response.ok else []

    @property
    def groups(self) -> Generator[Group, None, None]:
        """The groups configured in okta.

        Returns:
            generator: The generator of groups configured in okta

        """
        url = f'{self.api}/groups'
        for data in self._get_paginated_url(url):
            yield Group(self, data)

    def create_group(self, name: str, description: str) -> Group | None:
        """Creates a group in okta.

        Args:
            name: The name of the group to create
            description: The description of the group to create

        Returns:
            The created group object on success, None otherwise

        """
        url = f'{self.api}/groups'
        payload = {'profile': {'name': name, 'description': description}}
        response = self.session.post(url, data=json.dumps(payload))
        if not response.ok:
            self._logger.error(response.json())
        return Group(self, response.json()) if response.ok else None

    def get_group_type_by_name(
        self, name: str, group_type: str = 'OKTA_GROUP'
    ) -> Group | None:
        """Retrieves the group type of okta by name.

        Args:
            group_type: The type of okta group to retrieve
            name: The name of the group to retrieve

        Returns:
            Group: The group if a match is found else None

        """
        group = next(
            (
                group
                for group in self.search_groups_by_name(name)
                if group.type == group_type
            ),
            None,
        )
        return group

    def get_group_by_name(self, name: str) -> Group | None:
        """Retrieves the first group (of any type) by name.

        Args:
            name: The name of the group to retrieve

        Returns:
            Group: The group if a match is found else None

        """
        return next(
            (group for group in self.search_groups_by_name(name) if group.name == name),
            None,
        )

    def get_group_by_id(self, group_id: str) -> Group | None:
        """Retrieves the group (of any type) by id.

        Args:
            group_id: The id of the group to retrieve

        Returns:
            Group: The group if a match is found else None

        """
        url = f'{self.api}/groups/{group_id}'
        response = self.session.get(url)
        if not response.ok:
            self._logger.error(response.json())
        return Group(self, response.json()) if response.ok else None

    def search_groups_by_name(self, name: str) -> list[Group]:
        """Retrieves the groups (of any type) by name.

        Args:
            name: The name of the groups to retrieve

        Returns:
            list: A list of groups if a match is found else an empty list

        """
        url = f'{self.api}/groups?q={name}'
        response = self.session.get(url)
        if not response.ok:
            self._logger.error(response.json())
        return [Group(self, data) for data in response.json()] if response.ok else []

    def delete_group(self, name: str) -> bool:
        """Deletes a group from okta.

        Args:
            name: The name of the group to delete

        Returns:
            bool: True on success, False otherwise

        Raises:
            InvalidGroup: The group provided as argument does not exist.

        """
        group = self.get_group_by_name(name)
        if not group:
            raise InvalidGroup(name)
        return group.delete()

    def _get_paginated_url(
        self, url: str, result_limit: int = 100
    ) -> Generator[dict[str, Any], None, None]:
        """Gets the paginated data from a url.

        Args:
            url: The url to get the data from
            result_limit: The number of results to get per page, defaults to 100

        Returns:
            generator: A generator of the data from the url

        """
        response = self._validate_response(url, {'limit': result_limit})
        yield from response.json()
        next_link = response.links.get('next', {}).get('url')
        while next_link:
            response = self._validate_response(url=next_link)
            yield from response.json()
            next_link = response.links.get('next', {}).get('url')

    def _validate_response(
        self, url: str, params: dict[str, Any] | None = None
    ) -> Response:
        """Validate API response and raise appropriate exceptions on error.

        Args:
            url: The API endpoint URL to request
            params: Optional query parameters for the request

        Returns:
            Response: The validated HTTP response object

        Raises:
            ServerError: If the response indicates an error (not ok status)

        """
        response = self.session.get(url=url, params=params)
        if not response.ok:
            try:
                error_message = response.json().get('errorSummary')
            except (ValueError, AttributeError):
                error_message = response.text
            raise ServerError(error_message) from None
        return response

    @property
    def users(self) -> Generator[User, None, None]:
        """The users configured in okta.

        Returns:
            generator: The generator of users configured in okta

        """
        url = f'{self.api}/users'
        for data in self._get_paginated_url(url):
            yield User(self, data)

    def create_user(
        self,
        first_name: str,
        last_name: str,
        email: str,
        login: str,
        password: str | None = None,
        enabled: bool = True,
    ) -> User | None:
        """Creates a user in okta.

        Args:
            first_name: The first name of the user
            last_name: The last name of the user
            email: The email of the user
            login: The login of the user
            password: The password of the user
            enabled: A flag whether the user should be enabled or not
                Defaults to True

        Returns:
            User: The created user on success, None otherwise

        """
        activate = 'true' if enabled else 'false'
        url = f'{self.api}/users?activate={activate}'
        payload: dict[str, Any] = {
            'profile': {
                'firstName': first_name,
                'lastName': last_name,
                'email': email,
                'login': login,
            }
        }
        if password:
            payload.update({'credentials': {'password': {'value': password}}})
        response = self.session.post(url=url, data=json.dumps(payload))
        if not response.ok:
            self._logger.error(response.json())
        return User(self, response.json()) if response.ok else None

    def get_user_by_login(self, login: str) -> User | None:
        """Retrieves a user by login.

        Args:
            login: The login to match the user with

        Returns:
            User: The user if found, None otherwise

        """
        url = f'{self.api}/users?filter=profile.login+eq+"{login}"'
        response = self.session.get(url)
        if not response.ok:
            self._logger.error(response.json())
            return None
        return next(
            (
                User(self, data)
                for data in response.json()
                if data.get('profile', {}).get('login', '') == login
            ),
            None,
        )

    def search_users(self, value: str) -> list[User]:
        """Retrieves a list of users by looking into name, last name and email.

        Args:
            value: The value to match with

        Returns:
            list: The users if found, empty list otherwise

        """
        url = f'{self.api}/users?q={value}'
        response = self.session.get(url)
        if not response.ok:
            self._logger.error(response.json())
        return [User(self, data) for data in response.json()]

    def search_users_by_email(self, email: str) -> list[User]:
        """Retrieves a list of users by email.

        Args:
            email: The email to match the user with

        Returns:
            list: The users if found, empty list otherwise

        """
        url = f'{self.api}/users?filter=profile.email+eq+"{email}"'
        response = self.session.get(url)
        if not response.ok:
            self._logger.error(response.json())
        return [User(self, data) for data in response.json()]

    def get_user_assigned_roles_by_id(self, user_id: str) -> list[AdminRole] | None:
        """Retrieves if any, admin roles assigned to the user by id.

        Args:
            id: The user ID to match the user with

        Returns:
            list: A list of the user's roles if found, None otherwise

        """
        url = f'{self.api}/users/{user_id}/roles'
        response = self.session.get(url)
        if not response.ok:
            self._logger.error(response.json())
            return None
        return [AdminRole(self, data) for data in response.json()]

    def assign_role_to_user_by_id(
        self, user_id: str, role_name: str
    ) -> AdminRole | None:
        """Assigns an admin role to a user by id.

        Args:
            user_id: The user ID to match the user with
            role_name: The name of the role to assign

        Returns:
            User: The response, None otherwise

        """
        url = f'{self.api}/users/{user_id}/roles'
        data = {'type': role_name}
        response = self.session.post(url, json=data)
        if not response.ok:
            self._logger.error(response.json())
            return None
        return AdminRole(self, response.json())

    def remove_role_from_user_by_id(self, user_id: str, role_id: str) -> bool:
        """Remove an admin role from a user by id.

        Args:
            user_id: The user ID to match the user with
            role_id: The id of the role to remove

        Returns:
            User: The response, None otherwise

        """
        url = f'{self.api}/users/{user_id}/roles/{role_id}'
        response = self.session.delete(url)
        if not response.ok:
            self._logger.error(response.json())
            return False
        return True

    @property
    def applications(self) -> Generator[Application, None, None]:
        """The applications configured in okta.

        Returns:
            generator: The generator of applications configured in okta

        """
        url = f'{self.api}/apps'
        for data in self._get_paginated_url(url):
            yield Application(self, data)

    def get_application_by_id(self, id_: str) -> Application | None:
        """Retrieves an application by id.

        Args:
            id_: The id of the application to retrieve

        Returns:
            Application Object

        """
        app = next((app for app in self.applications if app.id == id_), None)
        return app

    def get_application_by_label(self, label: str) -> Application | None:
        """Retrieves an application by label.

        Args:
            label: The label of the application to retrieve

        Returns:
            Application Object

        """
        app = next(
            (
                app
                for app in self.applications
                if (app.label or '').lower() == label.lower()
            ),
            None,
        )
        return app

    def get_application_by_sign_on_mode(self, sign_on_mode: str) -> Application | None:
        """Retrieves an application by sign-on mode.

        Args:
            sign_on_mode: The sign-on mode of the application to retrieve

        Returns:
            Application Object

        """
        app = next(
            (
                app
                for app in self.applications
                if (app.sign_on_mode or "").lower() == sign_on_mode.lower()
            ),
            None,
        )
        return app

    def get_application_metadata(self, id_: str, kid: str) -> SAMLMetadata | None:
        """Retrieves an application's SAML metadata by id.

        Args:
            id_: The id of the application to retrieve
            kid: The key ID to match the SAML metadata with

        Returns:
            SAMLMetadata: The application's SAML metadata if found, None otherwise

        """
        url = f"{self.api}/apps/{id_}/sso/saml/metadata?kid={kid}"
        headers = {"Accept": "text/xml"}
        response = self.session.get(url, headers=headers)
        if not response.ok:
            self._logger.error(response.text)
            return None
        return SAMLMetadata(response.text)

    def assign_group_to_application(
        self, application_label: str, group_name: str
    ) -> bool:
        """Assigns a group to an application.

        Args:
            application_label: The label of the application to assign the group to
            group_name: The group name to assign to the application

        Returns:
            True on success, False otherwise

        """
        application = self.get_application_by_label(application_label)
        if not application:
            raise InvalidApplication(application_label)
        group = self.get_group_by_name(group_name)
        if not group:
            raise InvalidGroup(group_name)
        return application.add_group_by_id(group.id)

    def remove_group_from_application(
        self, application_label: str, group_name: str
    ) -> bool:
        """Removes a group from an application.

        Args:
            application_label: The label of the application to remove the group from
            group_name: The name of the group to remove from the application

        Returns:
            True on success, False otherwise

        """
        application = self.get_application_by_label(application_label)
        if not application:
            raise InvalidApplication(application_label)
        group = self.get_group_by_name(group_name)
        if not group:
            raise InvalidGroup(group_name)
        return application.remove_group_by_id(group.id)
