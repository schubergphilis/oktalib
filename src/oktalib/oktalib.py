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

from .entities import (
    AdminRole,
    APIServiceApp,
    Application,
    ApplicationType,
    AppSigningCertificate,
    DirectoryIntegrationsAgentPool,
    Feature,
    Group,
    SAMLApplication,
    SAMLMetadata,
    User,
)
from .oktacredentials import OktaCredentials
from .oktalibexceptions import (
    InvalidApplication,
    InvalidGroup,
)
from .oktasession import OktaSession

__author__ = 'Costas Tyfoxylos <ctyfoxylos@schubergphilis.com>'
__docformat__ = 'google'
__date__ = '2018-01-08'
__copyright__ = 'Copyright 2018, Costas Tyfoxylos'
__credits__ = ['Costas Tyfoxylos']
__license__ = 'MIT'
__maintainer__ = 'Costas Tyfoxylos'
__email__ = '<ctyfoxylos@schubergphilis.com>'
__status__ = 'Development'  # "Prototype", "Development", "Production".

# The sign-on modes whose applications sign assertions, and so hold signing certificates.
SIGNING_SIGN_ON_MODES = (
    ApplicationType.SAML_2_0.value,
    ApplicationType.WS_FEDERATION.value,
)

# This is the main prefix used for logging
LOGGER_BASENAME = 'oktalib'
LOGGER = logging.getLogger(LOGGER_BASENAME)
LOGGER.addHandler(logging.NullHandler())


class Okta:
    """Models the api of okta."""

    def __init__(self, host: str, credentials: OktaCredentials) -> None:
        """Initializes the Okta object.

        Args:
            host: The host of the okta instance, e.g. https://dev.oktapreview.com
            credentials: What to authenticate with, either an
                :class:`oktalib.oktacredentials.ApiTokenCredentials` or a
                :class:`oktalib.oktacredentials.ServiceAppCredentials`.

        """
        logger_name = f'{LOGGER_BASENAME}.{self.__class__.__name__}'
        self._logger = logging.getLogger(logger_name)
        # Constructed through the module global on purpose: the test suite substitutes
        # the class by rebinding this name, so reaching for it any other way sends the
        # suite to the network, and it fails by passing.
        self.session = OktaSession(host, credentials)

    @property
    def applications(self) -> Generator[Application, None, None]:
        """The applications configured in okta.

        Returns:
            generator: The generator of applications configured in okta.
                       Returns Application subclasses based on sign-on mode
                       (e.g., SAMLApplication for SAML apps, APIServiceApp for API Services apps).

        """
        url = '/apps'
        for data in self.session.get_paginated_url(url):
            yield self._create_application_from_data(data)

    def assign_group_to_application(self, application_label: str, group_name: str) -> bool:
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

    def _cleanup_broken_app(self, app: APIServiceApp, label: str) -> None:
        """Clean up a broken application by deactivating and deleting it.

        Args:
            app: The application to clean up
            label: The label of the application (for logging)
        """
        try:
            app.deactivate()
            app.delete()
        except Exception as cleanup_error:  # pylint: disable=broad-exception-caught
            # Catch all exceptions in cleanup to avoid raising during error handling
            self._logger.error(f'Failed to clean up broken app {label}: {cleanup_error}')

    def create_api_services_app_with_client_secret(
        self,
        label: str,
        dpop_bound_access_tokens: bool = True,
        consent_method: str = 'REQUIRED',
    ) -> APIServiceApp | None:
        """Create an API Service application with client_secret authentication.

        Args:
            label: The application label/name
            dpop_bound_access_tokens: Enable DPoP bound access tokens (default: True)
            consent_method: Consent method (default: 'REQUIRED')

        Returns:
            APIServiceApp | None: The created application on success, None otherwise
        """
        payload = self._get_api_services_app_payload(
            label=label,
            dpop_bound_access_tokens=dpop_bound_access_tokens,
            consent_method=consent_method,
        )
        return self._create_application_api_services(payload)

    def create_api_services_app_with_jwks(
        self,
        label: str,
        jwks: dict[str, Any],
        dpop_bound_access_tokens: bool = True,
        consent_method: str = 'REQUIRED',
    ) -> APIServiceApp | None:
        """Create an API Service application with private_key_jwt auth using inline JWKS.

        This method creates an application that uses private_key_jwt authentication
        with an inline JSON Web Key Set.

        Args:
            label: The application label/name
            jwks: JSON Web Key Set dictionary containing the public key
            dpop_bound_access_tokens: Enable DPoP bound access tokens (default: True)
            consent_method: Consent method (default: 'REQUIRED')

        Returns:
            APIServiceApp | None: The created application on success, None otherwise

        Note:
            The application is first created, then the JWKS is configured,
            and finally private_key_jwt authentication is enabled.
        """
        payload = self._get_api_services_app_payload(
            label=label,
            dpop_bound_access_tokens=dpop_bound_access_tokens,
            consent_method=consent_method,
        )
        app = self._create_application_api_services(payload)
        if not isinstance(app, APIServiceApp):
            return None

        try:
            app.add_public_keys_by_jwks(jwks=jwks)
            app._enable_public_private_key_authentication()
            return app
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Catch all exceptions to ensure cleanup of broken apps
            self._logger.error(f'Failed to configure app {label}: {e}')
            self._cleanup_broken_app(app, label)
            return None

    def create_api_services_app_with_jwks_uri(
        self,
        label: str,
        jwks_uri: str,
        dpop_bound_access_tokens: bool = True,
        consent_method: str = 'REQUIRED',
    ) -> APIServiceApp | None:
        """Create an API Service application with private_key_jwt auth using JWKS URI.

        This method creates an application that uses private_key_jwt authentication
        by fetching public keys from the provided JWKS URI.

        Args:
            label: The application label/name
            jwks_uri: URL to JSON Web Key Set (public keys endpoint)
            dpop_bound_access_tokens: Enable DPoP bound access tokens (default: True)
            consent_method: Consent method (default: 'REQUIRED')

        Returns:
            APIServiceApp | None: The created application on success, None otherwise

        Note:
            The application is first created, then the JWKS URI is configured,
            and finally private_key_jwt authentication is enabled.
        """
        payload = self._get_api_services_app_payload(
            label=label,
            dpop_bound_access_tokens=dpop_bound_access_tokens,
            consent_method=consent_method,
        )
        app = self._create_application_api_services(payload)
        if not isinstance(app, APIServiceApp):
            return None

        try:
            app.add_public_keys_by_public_url(jwks_uri=jwks_uri)
            app._enable_public_private_key_authentication()
            return app
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Catch all exceptions to ensure cleanup of broken apps
            self._logger.error(f'Failed to configure app {label}: {e}')
            self._cleanup_broken_app(app, label)
            return None

    def _create_application_api_services(self, data: dict[str, Any]) -> APIServiceApp | None:
        """Creates an API Services application in okta from the provided data.

        Args:
            data: The application data to create the application from
        Returns:
            Application: The created application
        """
        url = '/apps'
        response = self.session.post(url, json=data)

        if not response.ok:
            self._logger.error(response.text)
            return None
        app = self._create_application_from_data(response.json())
        return app if isinstance(app, APIServiceApp) else None

    def _create_application_from_data(self, data: dict[str, Any]) -> Application:
        """Create an Application instance based on the application type.

        Uses pattern matching to determine the application type from sign-on mode
        and returns the appropriate Application subclass.

        Args:
            data: The application data from the Okta API

        Returns:
            Application: An Application or subclass instance (e.g., SAMLApplication, APIServiceApp)

        """
        sign_on_mode = (data.get('signOnMode') or '').upper()

        try:
            app_type = ApplicationType(sign_on_mode)
        except ValueError:
            app_type = ApplicationType.UNKNOWN

        match app_type:
            case ApplicationType.SAML_2_0:
                return SAMLApplication(self, data)
            case ApplicationType.OPENID_CONNECT:
                # Check if this is an API Services application
                application_type = data.get('settings', {}).get('oauthClient', {}).get('application_type')
                if application_type == 'service':
                    return APIServiceApp(self, data)
                return Application(self, data)
            case (
                ApplicationType.WS_FEDERATION
                | ApplicationType.SECURE_PASSWORD_STORE
                | ApplicationType.AUTO_LOGIN
                | ApplicationType.BROWSER_PLUGIN
                | ApplicationType.BASIC_AUTH
                | ApplicationType.BOOKMARK
                | ApplicationType.UNKNOWN
                | _
            ):
                return Application(self, data)

    def _get_api_services_app_payload(
        self,
        label: str,
        dpop_bound_access_tokens: bool,
        consent_method: str,
    ) -> dict[str, Any]:
        """Gets the payload for creating an API Services application.

        Args:
            label: The application label/name
            dpop_bound_access_tokens: Enable DPoP bound access tokens
            consent_method: Consent method

        Returns:
            dict: The payload for creating an API Services application

        """
        credentials = {'oauthClient': {'token_endpoint_auth_method': 'client_secret_basic'}}

        oauth_client: dict[str, Any] = {
            'application_type': 'service',
            'consent_method': consent_method,
            'grant_types': ['client_credentials'],
            'response_types': ['token'],
            'dpop_bound_access_tokens': dpop_bound_access_tokens,
        }

        return {
            'credentials': credentials,
            'label': label,
            'name': 'oidc_client',
            'signOnMode': 'OPENID_CONNECT',
            'settings': {'oauthClient': oauth_client},
        }

    def get_application_by_id(self, id_: str) -> Application | None:
        """Retrieves an application by id.

        Args:
            id_: The id of the application to retrieve

        Returns:
            Application Object or subclass (e.g., SAMLApplication, APIServiceApp)

        """
        url = f'/apps/{id_}'
        response = self.session.get(url)
        if not response.ok:
            return None
        return self._create_application_from_data(response.json())

    def get_application_by_label(self, label: str) -> Application | None:
        """Retrieves an application by label.

        Args:
            label: The label of the application to retrieve

        Returns:
            Application Object or subclass (e.g., SAMLApplication, APIServiceApp)

        """
        return next(
            (app for app in self.applications if (app.label or '').lower() == label.lower()),
            None,
        )

    def get_application_by_sign_on_mode(self, sign_on_mode: str) -> Application | None:
        """Retrieves an application by sign-on mode.

        Args:
            sign_on_mode: The sign-on mode of the application to retrieve

        Returns:
            Application Object

        """
        return next(
            (
                app
                for app in self.applications
                if app.sign_on_mode and sign_on_mode and app.sign_on_mode.lower() == sign_on_mode.lower()
            ),
            None,
        )

    def get_application_metadata(self, id_: str, kid: str) -> SAMLMetadata | None:
        """Retrieves an application's SAML metadata by id.

        Args:
            id_: The id of the application to retrieve
            kid: The key ID to match the SAML metadata with

        Returns:
            SAMLMetadata: The application's SAML metadata if found, None otherwise

        """
        url = f'/apps/{id_}/sso/saml/metadata?kid={kid}'
        headers = {'Accept': 'text/xml'}
        response = self.session.get(url, headers=headers)
        if not response.ok:
            self._logger.error(response.text)
            return None
        return SAMLMetadata(response.text)

    def get_expired_app_certificates(self) -> Generator[tuple[Application, AppSigningCertificate], None, None]:
        """Retrieves the app signing certificates that have already expired.

        Returns:
            generator: A generator of (Application, AppSigningCertificate)
                tuples for every expired certificate

        """
        yield from self.get_expiring_app_certificates(days=0)

    def get_expiring_app_certificates(
        self, days: int = 30
    ) -> Generator[tuple[Application, AppSigningCertificate], None, None]:
        """Retrieves the app signing certificates expiring within a window.

        Only applications whose sign-on mode signs assertions are inspected, so
        the sign-on mode already present in the application listing keeps this
        to one extra request per signing application rather than one per
        application. Already expired certificates are included.

        Args:
            days: The size of the window in days, counted from now

        Returns:
            generator: A generator of (Application, AppSigningCertificate)
                tuples for every certificate expiring within the window

        """
        yield from (
            (application, certificate)
            for application in self.applications
            if application.sign_on_mode in SIGNING_SIGN_ON_MODES
            for certificate in application.expiring_signing_certificates(days)
        )

    def remove_group_from_application(self, application_label: str, group_name: str) -> bool:
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

    @property
    def directory_integrations_agent_pools(self) -> Generator[DirectoryIntegrationsAgentPool, None, None]:
        """The Directory Integrations agent pools configured in okta.

        Returns:
            generator: The generator of agent pools configured in okta

        """
        url = '/agentPools'
        for data in self.session.get_paginated_url(url):
            yield DirectoryIntegrationsAgentPool(self, data)

    def get_directory_integrations_agent_pool_by_id(self, pool_id: str) -> DirectoryIntegrationsAgentPool | None:
        """Retrieves a Directory Integrations agent pool by id.

        Okta answers 405 for a single pool, so this searches the listing rather than
        addressing the pool directly. Orgs have few pools, so the listing is cheap.

        Args:
            pool_id: The id of the agent pool to retrieve

        Returns:
            DirectoryIntegrationsAgentPool: The pool if a match is found else None

        """
        return next(
            (pool for pool in self.directory_integrations_agent_pools if pool.id == pool_id),
            None,
        )

    def get_directory_integrations_agent_pool_by_name(self, name: str) -> DirectoryIntegrationsAgentPool | None:
        """Retrieves a Directory Integrations agent pool by name.

        Args:
            name: The name of the agent pool to retrieve

        Returns:
            DirectoryIntegrationsAgentPool: The pool if a match is found else None

        """
        return next(
            (pool for pool in self.directory_integrations_agent_pools if (pool.name or '').lower() == name.lower()),
            None,
        )

    def get_directory_integrations_agent_pools_by_type(
        self, pool_type: str
    ) -> Generator[DirectoryIntegrationsAgentPool, None, None]:
        """Retrieves the Directory Integrations agent pools of one type.

        Okta applies this filter itself, so it costs no more than listing them all.

        Args:
            pool_type: The type of pool to retrieve, e.g. AD or LDAP

        Returns:
            generator: The generator of agent pools of that type

        Raises:
            ServerError: If Okta rejects the pool type.

        """
        url = '/agentPools'
        for data in self.session.get_paginated_url(url, params={'poolType': pool_type}):
            yield DirectoryIntegrationsAgentPool(self, data)

    @property
    def features(self) -> Generator[Feature, None, None]:
        """The features configured in okta.

        Returns:
            generator: The generator of features configured in okta

        """
        url = '/features'
        for data in self.session.get_paginated_url(url):
            yield Feature(self, data)

    def get_feature_by_id(self, feature_id: str) -> Feature | None:
        """Retrieves the feature by id.

        Args:
            feature_id: The id of the feature to retrieve

        Returns:
            Feature: The feature if a match is found else None

        """
        url = f'/features/{feature_id}'
        response = self.session.get(url)
        if not response.ok:
            self._logger.error(response.text)
            return None
        return Feature(self, response.json())

    def get_feature_by_name(self, name: str) -> Feature | None:
        """Retrieves the first feature (of any type) by name.

        Args:
            name: The name of the feature to retrieve

        Returns:
            Feature: The feature if a match is found else None

        """
        return next(
            (feature for feature in self.features if (feature.name or '').lower() == name.lower()),
            None,
        )

    def get_feature_dependencies_by_id(self, feature_id: str) -> Generator[Feature, None, None]:
        """Lists all feature dependencies for a specified feature.

        A feature's dependencies are the features that it requires to be
        enabled in order for itself to be enabled.

        Args:
            feature_id: The id of the feature to retrieve

        Returns:
            generator: The generator of feature dependencies for the specified feature

        """
        url = f'/features/{feature_id}/dependencies'
        for data in self.session.get_paginated_url(url):
            yield Feature(self, data)

    def get_feature_dependents_by_id(self, feature_id: str) -> Generator[Feature, None, None]:
        """Lists all feature dependents for the specified feature.

        A feature's dependents are the features that need to be disabled in
        order for the feature itself to be disabled.

        Args:
            feature_id: The id of the feature to retrieve

        Returns:
            generator: The generator of feature dependents for the specified feature

        """
        url = f'/features/{feature_id}/dependents'
        for data in self.session.get_paginated_url(url):
            yield Feature(self, data)

    @property
    def groups(self) -> Generator[Group, None, None]:
        """The groups configured in okta.

        Returns:
            generator: The generator of groups configured in okta

        """
        url = '/groups'
        for data in self.session.get_paginated_url(url):
            yield Group(self, data)

    def create_group(self, name: str, description: str) -> Group | None:
        """Creates a group in okta.

        Args:
            name: The name of the group to create
            description: The description of the group to create

        Returns:
            The created group object on success, None otherwise

        """
        url = '/groups'
        payload = {'profile': {'name': name, 'description': description}}
        response = self.session.post(url, data=json.dumps(payload))
        if not response.ok:
            self._logger.error(response.text)
            return None
        return Group(self, response.json())

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

    def get_group_by_id(self, group_id: str) -> Group | None:
        """Retrieves the group (of any type) by id.

        Args:
            group_id: The id of the group to retrieve

        Returns:
            Group: The group if a match is found else None

        """
        url = f'/groups/{group_id}'
        response = self.session.get(url)
        if not response.ok:
            self._logger.error(response.text)
            return None
        return Group(self, response.json())

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

    def get_group_type_by_name(self, name: str, group_type: str = 'OKTA_GROUP') -> Group | None:
        """Retrieves the group type of okta by name.

        Args:
            group_type: The type of okta group to retrieve
            name: The name of the group to retrieve

        Returns:
            Group: The group if a match is found else None

        """
        return next(
            (group for group in self.search_groups_by_name(name) if group.type == group_type),
            None,
        )

    def search_groups_by_name(self, name: str) -> list[Group]:
        """Retrieves the groups (of any type) by name.

        Args:
            name: The name of the groups to retrieve

        Returns:
            list: A list of groups if a match is found else an empty list

        """
        url = f'/groups?q={name}'
        response = self.session.get(url)
        if not response.ok:
            self._logger.error(response.text)
            return []
        return [Group(self, data) for data in response.json()]

    def search_groups_by_query(self, query: str) -> list[Group]:
        """Retrieves the groups according to the raw query provided.
        Details about the filtering expression can be found in the
        [Okta Documentation](https://developer.okta.com/docs/api#filter)

        Args:
            query: Okta query to be used to retrieve subset of groups.

        Returns:
            list: A list of groups if a match is found else an empty list
        """
        url = f'/groups?search={query}'
        response = self.session.get(url)
        if not response.ok:
            self._logger.error(response.text)
            return []
        return [Group(self, data) for data in response.json()]

    @property
    def users(self) -> Generator[User, None, None]:
        """The users configured in okta.

        Returns:
            generator: The generator of users configured in okta

        """
        url = '/users'
        for data in self.session.get_paginated_url(url):
            yield User(self, data)

    def assign_role_to_user_by_id(self, user_id: str, role_name: str) -> AdminRole | None:
        """Assigns an admin role to a user by id.

        Args:
            user_id: The user ID to match the user with
            role_name: The name of the role to assign

        Returns:
            User: The response, None otherwise

        """
        url = f'/users/{user_id}/roles'
        data = {'type': role_name}
        response = self.session.post(url, json=data)
        if not response.ok:
            self._logger.error(response.text)
            return None
        return AdminRole(self, response.json())

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
        url = f'/users?activate={activate}'
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
            self._logger.error(response.text)
            return None
        return User(self, response.json())

    def get_user_assigned_roles_by_id(self, user_id: str) -> list[AdminRole] | None:
        """Retrieves if any, admin roles assigned to the user by id.

        Args:
            id: The user ID to match the user with

        Returns:
            list: A list of the user's roles if found, None otherwise

        """
        url = f'/users/{user_id}/roles'
        response = self.session.get(url)
        if not response.ok:
            self._logger.error(response.text)
            return None
        return [AdminRole(self, data) for data in response.json()]

    def get_user_by_login(self, login: str) -> User | None:
        """Retrieves a user by login.

        Args:
            login: The login to match the user with

        Returns:
            User: The user if found, None otherwise

        """
        url = f'/users?filter=profile.login+eq+"{login}"'
        response = self.session.get(url)
        if not response.ok:
            self._logger.error(response.text)
            return None
        return next(
            (User(self, data) for data in response.json() if data.get('profile', {}).get('login', '') == login),
            None,
        )

    def remove_role_from_user_by_id(self, user_id: str, role_id: str) -> bool:
        """Remove an admin role from a user by id.

        Args:
            user_id: The user ID to match the user with
            role_id: The id of the role to remove

        Returns:
            User: The response, None otherwise

        """
        url = f'/users/{user_id}/roles/{role_id}'
        response = self.session.delete(url)
        if not response.ok:
            self._logger.error(response.text)
            return False
        return True

    def search_users(self, value: str) -> list[User]:
        """Retrieves a list of users by looking into name, last name and email.

        Args:
            value: The value to match with

        Returns:
            list: The users if found, empty list otherwise

        """
        url = f'/users?q={value}'
        response = self.session.get(url)
        if not response.ok:
            self._logger.error(response.text)
            return []
        return [User(self, data) for data in response.json()]

    def search_users_by_email(self, email: str) -> list[User]:
        """Retrieves a list of users by email.

        Args:
            email: The email to match the user with

        Returns:
            list: The users if found, empty list otherwise

        """
        url = f'/users?filter=profile.email+eq+"{email}"'
        response = self.session.get(url)
        if not response.ok:
            self._logger.error(response.text)
            return []
        return [User(self, data) for data in response.json()]

    def search_users_by_query(self, query: str, sort_by: str | None = None) -> Generator[User, None, None]:
        """Retrieves the users matching a raw search expression.

        The ``search`` parameter is considerably more capable than the ``q`` and
        ``filter`` parameters the other search methods use: it combines terms
        with ``and``/``or``, and supports operators such as ``eq``, ``sw``
        (starts with) and ``gt`` over both top level and ``profile.*``
        properties. Details are in the
        [Okta documentation](https://developer.okta.com/docs/reference/core-okta-api/#filter).

        Examples:
            Every locked out user::

                okta.search_users_by_query('status eq "LOCKED_OUT"')

            Active or suspended users whose name starts with a term::

                okta.search_users_by_query(
                    '(status eq "ACTIVE" or status eq "SUSPENDED") '
                    'and (profile.firstName sw "Jo" or profile.lastName sw "Jo")',
                    sort_by='profile.lastName',
                )

        Args:
            query: The Okta search expression to match users with
            sort_by: Optional property to sort the results by, e.g.
                ``profile.lastName``

        Returns:
            generator: A generator of the matching users

        Raises:
            ServerError: If Okta rejects the search expression or the request
                otherwise fails.

        """
        url = '/users'
        for data in self.session.get_paginated_url(url, params={'search': query, 'sortBy': sort_by}):
            yield User(self, data)
