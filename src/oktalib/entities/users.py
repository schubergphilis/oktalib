#!/usr/bin/env python
# File: users.py
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
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.
#
"""
User-related entities.

.. _Google Python Style Guide:
   https://google.github.io/styleguide/pyguide.html

"""

from __future__ import annotations

import json
import logging
from collections.abc import Generator
from datetime import datetime
from typing import TYPE_CHECKING, Any

from cachetools import TTLCache, cached

from oktalib.oktalibexceptions import UnableToUpdate

from . import groups
from .adminrole import AdminRole
from .core import Entity

if TYPE_CHECKING:
    from oktalib.oktalib import Okta

    from .groups import Group

__author__ = 'Yorick Hoorneman <yhoorneman@schubergphilis.com>'
__docformat__ = 'google'
__date__ = '2026-03-24'
__copyright__ = 'Copyright 2026, Yorick Hoorneman'
__credits__ = ['Yorick Hoorneman']
__license__ = 'MIT'
__maintainer__ = 'Yorick Hoorneman'
__email__ = '<yhoorneman@schubergphilis.com>'
__status__ = 'Development'  # "Prototype", "Development", "Production".

LOGGER_BASENAME = 'users'
LOGGER = logging.getLogger(LOGGER_BASENAME)
LOGGER.addHandler(logging.NullHandler())


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
            yield groups.Group(self._okta, data)

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

    def __init__(self, okta_instance: Okta, data: dict[str, Any]) -> None:
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
        return groups.Group(self._okta, response.json())

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


class UserFactor(Entity):
    """Models the user factor object of okta."""

    def __init__(
        self, okta_instance: Okta, user_data: dict[str, Any], data: dict[str, Any]
    ) -> None:
        super().__init__(okta_instance, data)
        self._user_data = user_data

    @property
    def factor_type(self) -> str:
        """The type of the user factor.

        Returns:
            factor_type (str): The type of the user factor.

        """
        return self._data.get('factorType', '')

    @property
    def provider(self) -> str:
        """The provider of the user factor.

        Returns:
            provider (str): The provider of the user factor.

        """
        return self._data.get('provider', '')

    @property
    def vendor_name(self) -> str:
        """The vendor name of the user factor.

        Returns:
            vendor_name (str): The vendor name of the user factor.

        """
        return self._data.get('vendorName', '')

    @property
    def status(self) -> str:
        """The status of the user factor.

        Returns:
            status (str): The status of the user factor.

        """
        return self._data.get('status', '')

    @property
    def profile(self) -> dict[str, Any]:
        """The profile of the user factor.

        Returns:
            profile (dict): The profile of the user factor.

        """
        return self._data.get('profile', {})

    def delete(self) -> bool:
        """Deletes the user factor from okta.

        Returns:
            bool: True on success, False otherwise

        """
        url = f'{self._okta.api}/users/{self._user_data.get("id")}/factors/{self.id}'
        response = self._okta.session.delete(url)
        return response.ok


class UserSupportedFactor:
    """Models a supported (but not yet enrolled) user factor from the catalog endpoint.

    Unlike UserFactor, these factors don't have an ID yet since they're not enrolled.
    They represent factor types that can be enrolled for a user.
    """

    def __init__(
        self, okta_instance: Okta, user_data: dict[str, Any], data: dict[str, Any]
    ) -> None:
        """Initialize UserSupportedFactor.

        Args:
            okta_instance: The Okta instance
            user_data: The user data dictionary
            data: The factor data from the catalog endpoint
        """
        self._okta = okta_instance
        self._user_data = user_data
        self._data = data
        self._logger = logging.getLogger(f'{LOGGER_BASENAME}.UserSupportedFactor')

    @property
    def factor_type(self) -> str:
        """The type of the user factor.

        Returns:
            str: The type of the user factor (e.g., 'sms',
                'token:software:totp', 'question')

        """
        return self._data.get('factorType', '')

    @property
    def provider(self) -> str:
        """The provider of the user factor.

        Returns:
            str: The provider of the user factor (e.g., 'OKTA', 'GOOGLE', 'RSA')

        """
        return self._data.get('provider', '')

    @property
    def vendor_name(self) -> str | None:
        """The vendor name of the user factor.

        Returns:
            str | None: The vendor name of the user factor, if present

        """
        return self._data.get('vendorName')

    @property
    def enrollment(self) -> str:
        """The optionality of the user factor.

        Returns:
            str: The optionality of the user factor (e.g., 'required', 'optional')

        """
        return self._data.get('enrollment', '')

    @property
    def enroll_link(self) -> str | None:
        """The enrollment URL for this factor.

        Returns:
            str | None: The URL to POST to for enrolling in this factor

        """
        return self._data.get('_links', {}).get('enroll', {}).get('href')

    @property
    def questions_link(self) -> str | None:
        """The questions URL for security question factors.

        Returns:
            str | None: The URL to GET available security questions
                (only for question factors)

        """
        return self._data.get('_links', {}).get('questions', {}).get('href')

    @property
    def embedded_phones(self) -> list[dict[str, Any]]:
        """Embedded phone data for SMS/call factors.

        Returns:
            list[dict]: List of phone objects with id, profile (phoneNumber), and status

        """
        return self._data.get('_embedded', {}).get('phones', [])
