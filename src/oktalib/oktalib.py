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

from .entities import (
    AdminRole,
    APIServiceApp,
    Application,
    ApplicationType,
    Feature,
    Group,
    SAMLApplication,
    SAMLMetadata,
    User,
)
from .oktalibexceptions import (
    ApiLimitReached,
    AuthFailed,
    InvalidApplication,
    InvalidGroup,
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
        self._logger.debug(f'Using patched request for method {method}, url {url}, kwargs {kwargs}')
        response = self.session.original_request(  # type: ignore[attr-defined]
            method, url, **kwargs
        )
        if response.status_code == 429:
            self._logger.warning('Api is exhausted for endpoint, backing off.')
            raise ApiLimitReached
        return response

    @property
    def features(self) -> Generator[Feature, None, None]:
        """The features configured in okta.

        Returns:
            generator: The generator of features configured in okta

        """
        url = f'{self.api}/features'
        for data in self._get_paginated_url(url):
            yield Feature(self, data)

    def get_feature_by_id(self, feature_id: str) -> Feature | None:
        """Retrieves the feature by id.

        Args:
            feature_id: The id of the feature to retrieve

        Returns:
            Feature: The feature if a match is found else None

        """
        url = f'{self.api}/features/{feature_id}'
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
            (feature for feature in self.features if feature.name == name),
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
        url = f'{self.api}/features/{feature_id}/dependencies'
        for data in self._get_paginated_url(url):
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
        url = f'{self.api}/features/{feature_id}/dependents'
        for data in self._get_paginated_url(url):
            yield Feature(self, data)

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
            self._logger.error(response.text)
            return None
        return Group(self, response.json())

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
            self._logger.error(response.text)
            return None
        return Group(self, response.json())

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
        url = f'{self.api}/groups?search={query}'
        response = self.session.get(url)
        if not response.ok:
            self._logger.error(response.text)
            return []
        return [Group(self, data) for data in response.json()]

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

    def _get_paginated_url(self, url: str, result_limit: int = 100) -> Generator[dict[str, Any], None, None]:
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

    def _validate_response(self, url: str, params: dict[str, Any] | None = None) -> Response:
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
            self._logger.error(response.text)
            return None
        return User(self, response.json())

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
            self._logger.error(response.text)
            return None
        return next(
            (User(self, data) for data in response.json() if data.get('profile', {}).get('login', '') == login),
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
        url = f'{self.api}/users?filter=profile.email+eq+"{email}"'
        response = self.session.get(url)
        if not response.ok:
            self._logger.error(response.text)
            return []
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
            self._logger.error(response.text)
            return None
        return [AdminRole(self, data) for data in response.json()]

    def assign_role_to_user_by_id(self, user_id: str, role_name: str) -> AdminRole | None:
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
            self._logger.error(response.text)
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
            self._logger.error(response.text)
            return False
        return True

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

    def _create_application_api_services(self, data: dict[str, Any]) -> APIServiceApp | None:
        """Creates an API Services application in okta from the provided data.

        Args:
            data: The application data to create the application from
        Returns:
            Application: The created application
        """
        url = f'{self.api}/apps'
        response = self.session.post(url, json=data)

        if not response.ok:
            self._logger.error(response.text)
            return None
        app = self._create_application_from_data(response.json())
        return app if isinstance(app, APIServiceApp) else None

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

    @property
    def applications(self) -> Generator[Application, None, None]:
        """The applications configured in okta.

        Returns:
            generator: The generator of applications configured in okta.
                       Returns Application subclasses based on sign-on mode
                       (e.g., SAMLApplication for SAML apps, APIServiceApp for API Services apps).

        """
        url = f'{self.api}/apps'
        for data in self._get_paginated_url(url):
            yield self._create_application_from_data(data)

    def get_application_by_id(self, id_: str) -> Application | None:
        """Retrieves an application by id.

        Args:
            id_: The id of the application to retrieve

        Returns:
            Application Object or subclass (e.g., SAMLApplication, APIServiceApp)

        """
        url = f'{self.api}/apps/{id_}'
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
        url = f'{self.api}/apps/{id_}/sso/saml/metadata?kid={kid}'
        headers = {'Accept': 'text/xml'}
        response = self.session.get(url, headers=headers)
        if not response.ok:
            self._logger.error(response.text)
            return None
        return SAMLMetadata(response.text)

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
