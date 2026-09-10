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
from .core import Entity, parse_datetime

if TYPE_CHECKING:
    from oktalib.oktalib import Okta

    from .apps import Application
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

# Provisioning task statuses that are not an outstanding failure. COMPLETED is done;
# PROVISIONING is Okta still working, and was observed on a task moments after an
# assignment was re-driven. Treating an in-flight task as a failure makes a caller
# act on work that is already running.
NON_FAILURE_TASK_STATUSES = frozenset({'COMPLETED', 'PROVISIONING'})


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

    def app_assignments(self) -> Generator[UserAssignment, None, None]:
        """The user's application assignments, one request per page rather than a scan.

        Okta lets ``/api/v1/apps`` be filtered by user and asked to embed that
        user's app user in the same call, so the whole answer arrives with the
        application listing::

            GET /api/v1/apps?filter=user.id eq "{userId}"&expand=user/{userId}

        That is the documented equivalent of the admin console's per-user task
        view. Reaching the same answer through
        :attr:`~oktalib.entities.apps.Application.user_assignments` would mean
        listing every application and paging its users.

        The two parameters are a pair: ``expand`` is rejected with 400 unless the
        filter names the same user, and the filter without the expand returns the
        applications with no assignment embedded. A user id that matches nothing
        yields no applications rather than an error, so an unknown user and a user
        with no assignments are indistinguishable here.

        ``expand`` cannot also carry ``task``, so these assignments have no
        :attr:`~UserAssignment.task` and report a failure through
        :attr:`~UserAssignment.sync_state` without its reason. Use
        :meth:`~oktalib.entities.apps.Application.user_assignments_with_tasks` on
        the application for that.

        Returns:
            generator: A generator of the user's assignments, each carrying the
                application it is to.

        """
        url = f'{self._okta.api}/apps'
        params = {'filter': f'user.id eq "{self.id}"', 'expand': f'user/{self.id}'}
        for data in self._okta._get_paginated_url(url, params=params):  # noqa: SLF001
            assignment = data.get('_embedded', {}).get('user')
            if not assignment:
                continue
            yield UserAssignment(self._okta, assignment, application_data=data)

    def enrolled_factors(self) -> Generator[UserFactor, None, None]:
        """Lists the factors the user is enrolled in.

        Returns:
            generator: A generator of UserFactor objects for which the user
                is enrolled in

        """
        url = f'{self._okta.api}/users/{self.id}/factors'
        for data in self._okta._get_paginated_url(url):  # noqa: SLF001
            yield _create_factor_from_data(self._okta, self._data, data)

    def supported_factors(self) -> Generator[UserSupportedFactor, None, None]:
        """Lists all the supported factors that can be enrolled for the
        specified user that are included in the highest priority
        authenticator enrollment policy that applies to the user.

        Only factors that are REQUIRED or OPTIONAL in the highest priority
        authenticator enrollment policy can be returned.

        Returns:
            generator: A generator of UserSupportedFactor objects for which
                the user can enroll in

        """
        url = f'{self._okta.api}/users/{self.id}/factors/catalog'
        for data in self._okta._get_paginated_url(url):  # noqa: SLF001
            yield UserSupportedFactor(self._okta, self._data, data)

    def enroll_factor(self, factor_type: str, provider: str, query: dict[str, Any]) -> UserFactor | None:
        """Enrolls the user in a new factor.

        Args:
            factor_type: The type of the factor to enroll in (e.g., 'sms',
                'token:software:totp', 'question')
            provider: The provider of the factor to enroll in (e.g., 'OKTA',
                'GOOGLE', 'RSA')
            query: A dictionary containing the query attributes required for
                enrolling in the factor (e.g., {'phoneNumber': '+1234567890'}
                for sms factors)
        Returns:
            UserFactor: The enrolled UserFactor object on success, None otherwise
        """
        url = f'{self._okta.api}/users/{self.id}/factors'
        payload = {'factorType': factor_type, 'provider': provider}
        response = self._okta.session.post(url, data=json.dumps(payload), params=query)
        if not response.ok:
            self._logger.error(response.text)
            return None
        return _create_factor_from_data(self._okta, self._data, response.json())


class UserAssignmentTask(Entity):
    """Models the provisioning task attached to an application assignment.

    These are the items behind the admin console's "Application assignments
    encountered errors" and provisioning to-do tasks, and the ``aat`` id matches
    the one the console uses. Unlike :attr:`UserAssignment.sync_state`, the task
    carries the reason the assignment failed.

    Okta embeds it in an app user read with ``expand=task``; there is no endpoint
    serving a task on its own, so this entity has no url of its own.
    """

    @property
    def status(self) -> str | None:
        """The status of the task.

        Do not read this as "did it fail": a task with status COMPLETED was
        observed still carrying an :attr:`error_string`. Use :attr:`has_error`.

        Returns:
            status (str): The status of the task, e.g. PROVISIONING_FAILED or
                COMPLETED. None if absent.

        """
        return self._data.get('status')

    @property
    def error_string(self) -> str | None:
        """The reason the provisioning action failed.

        This is the only place the public API exposes it — ``sync_state`` reports
        that something is wrong without saying what. The text names the affected
        user and the app, e.g. "Automatic provisioning of user ... to app ...
        failed: The object already exists."

        Returns:
            error_string (str): The failure reason, None when the task records no
                error

        """
        return self._data.get('errorString')

    @property
    def has_error(self) -> bool:
        """Whether the task records a failure.

        Returns:
            bool: True if the task carries a reason, False otherwise

        """
        return bool(self.error_string)

    @property
    def has_failed(self) -> bool:
        """Whether the task is one the admin console counts as outstanding.

        This is not the same question as :attr:`has_error`. Okta leaves the reason
        on a task after it succeeds, so a COMPLETED task usually still carries one.
        Counting by reason therefore over-reports heavily; only :attr:`status`
        matches the console.

        A status this library has not seen counts as a failure, so a new one
        surfaces rather than being silently dropped.

        Returns:
            bool: True when the task is in a failure status, False when it has
                completed, is still running, or reports no status at all.

        """
        return bool(self.status) and self.status not in NON_FAILURE_TASK_STATUSES

    @property
    def assignment_type(self) -> str | None:
        """How the assignment that produced this task was made.

        Returns:
            assignment_type (str): GROUP when the assignment comes from a group,
                USER for an individual one. None if absent.

        """
        return self._data.get('assignmentType')

    @property
    def group_id(self) -> str | None:
        """The id of the group the assignment came from.

        Returns:
            group_id (str): The id of the source group, None for an individual
                assignment or when absent

        """
        return self._data.get('groupId')

    @property
    def created_at(self) -> datetime | None:
        """The date and time the task was created.

        The task payload spells this ``createdDate`` rather than the ``created``
        the rest of the API uses, so the inherited implementation cannot read it.

        Returns:
            datetime: The datetime the task was created, None if absent

        """
        return self._get_date_from_key('createdDate')

    @property
    def last_updated_at(self) -> datetime | None:
        """The date and time the task was last updated.

        The task payload spells this ``lastUpdate``, not ``lastUpdated``.

        Returns:
            datetime: The datetime the task was last updated, None if absent

        """
        return self._get_date_from_key('lastUpdate')


class UserAssignment(Entity):
    """Models the user assignment object of okta for apps."""

    def __init__(
        self,
        okta_instance: Okta,
        data: dict[str, Any],
        application_data: dict[str, Any] | None = None,
    ) -> None:
        """Initialize a user assignment.

        Args:
            okta_instance: The Okta API client instance.
            data: The app user payload.
            application_data: The payload of the application the assignment is
                to, when the caller already has it. Reading it from a listing of
                applications, as :meth:`User.app_assignments` does, saves
                :attr:`application` a request.

        """
        super().__init__(okta_instance, data)
        self._user_assignment_data = self._data
        self._application_data = application_data

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
    def application(self) -> Application | None:
        """The application the assignment is to.

        Costs a request unless the assignment came from a listing that already
        carried the application, as :meth:`User.app_assignments` does.

        Returns:
            application (Application): The application, or None when the payload
                carries no link to one.

        """
        if self._application_data is None:
            url = self._user_assignment_data.get('_links', {}).get('app', {}).get('href')
            if not url:
                return None
            response = self._okta.session.get(url)
            if not response.ok:
                self._logger.error(response.text)
                return None
            self._application_data = response.json()
        return self._okta._create_application_from_data(self._application_data)  # noqa: SLF001

    @property
    def status(self) -> str | None:
        """The status of the assignment.

        This is the status of the app user, not of the Okta user it refers to;
        ``self.user.status`` is a different value from a different enum.

        Returns:
            status (str): The status of the assignment, one of ACTIVE, APPROVED,
                DEPROVISIONED, IMPLICIT, IMPORTED, INACTIVE, MATCHED, PENDING,
                PROVISIONED, REVOKED, STAGED, SUSPENDED or UNASSIGNED. None if
                absent.

        """
        return self._user_assignment_data.get('status')

    @property
    def sync_state(self) -> str | None:
        """The provisioning synchronisation state of the assignment.

        This is what the admin console's "Application assignments encountered
        errors" and "Profile push updates encountered errors" tasks are built
        on. Note that it carries no reason for the failure, and does not
        distinguish an assignment error from a profile push error.

        Returns:
            sync_state (str): The sync state of the assignment, one of DISABLED,
                ERROR, OUT_OF_SYNC, SYNCHRONIZED or SYNCING. None if absent.

        """
        return self._user_assignment_data.get('syncState')

    @property
    def scope(self) -> str | None:
        """Whether the assignment is individual or inherited from a group.

        Returns:
            scope (str): USER for an assignment made to the user directly,
                GROUP for one inherited from a group assignment. None if absent.

        """
        return self._user_assignment_data.get('scope')

    @property
    def task(self) -> UserAssignmentTask | None:
        """The provisioning task attached to this assignment.

        Only present when the assignment was read with ``expand=task``, which
        :meth:`oktalib.entities.apps.Application.user_assignments_with_tasks`
        does; the plain assignment listing carries no task and this returns None.
        Okta attaches a task to the failing assignments only, so a None here on an
        expanded read means the assignment is healthy.

        Returns:
            task (UserAssignmentTask): The task if one is embedded, None otherwise

        """
        data = self._user_assignment_data.get('_embedded', {}).get('task')
        if not isinstance(data, dict):
            return None
        return UserAssignmentTask(self._okta, data)

    @property
    def last_sync(self) -> datetime | None:
        """The date and time of the last provisioning synchronisation.

        Returns:
            last_sync (datetime): The datetime of the last sync, None if the
                assignment has never been synced or the field is absent.

        """
        return parse_datetime(self._user_assignment_data.get('lastSync'))

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


def _create_factor_from_data(
    okta_instance: Okta,
    user_data: dict[str, Any],
    factor_data: dict[str, Any],
) -> UserFactor:
    """Create a UserFactor instance based on the factor type and provider.

    Uses pattern matching to determine the factor type from factorType and provider
    fields and returns the appropriate UserFactor subclass.

    Args:
        okta_instance: The Okta instance
        user_data: The user data dictionary
        factor_data: The factor data from the Okta API

    Returns:
        UserFactor: A UserFactor or subclass instance (e.g., UserFactorGoogleOTP)

    """
    factor_type = factor_data.get('factorType', '')
    provider = factor_data.get('provider', '')

    match (factor_type, provider):
        case ('token:software:totp', 'GOOGLE'):
            return UserFactorGoogleOTP(okta_instance, user_data, factor_data)
        case _:
            return UserFactor(okta_instance, user_data, factor_data)


class UserFactor(Entity):
    """Models the user factor object of okta."""

    def __init__(self, okta_instance: Okta, user_data: dict[str, Any], data: dict[str, Any]) -> None:
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


class UserFactorGoogleOTP(UserFactor):
    """Models a Google OTP (Authenticator) factor with enrollment and activation support.

    This subclass extends UserFactor to handle Google Authenticator TOTP factors,
    providing access to shared secrets, QR codes, and activation functionality.
    """

    @property
    def shared_secret(self) -> str:
        """The base32-encoded shared secret for TOTP generation.

        This secret is used to generate time-based one-time passwords and is
        typically displayed as a QR code or manual entry code during enrollment.

        Returns:
            str: The base32-encoded shared secret, or empty string if not available

        """
        return self._data.get('_embedded', {}).get('activation', {}).get('sharedSecret', '')

    @property
    def qr_code_link(self) -> str:
        """The URL to the QR code image for enrollment.

        Users can scan this QR code with their Google Authenticator app to
        automatically configure the TOTP factor.

        Returns:
            str: The QR code image URL, or empty string if not available

        """
        return self._data.get('_embedded', {}).get('activation', {}).get('_links', {}).get('qrcode', {}).get('href', '')

    @property
    def activation_link(self) -> str:
        """The API endpoint URL for activating this factor.

        Returns:
            str: The activation endpoint URL, or empty string if not available

        """
        return self._data.get('_links', {}).get('activate', {}).get('href', '')

    def activate(self, passcode: str) -> bool:
        """Activate the pending Google OTP factor with a TOTP code.

        This method activates a factor that is in PENDING_ACTIVATION status by
        verifying a time-based one-time password. The passcode can be generated
        by a user's Google Authenticator app or programmatically using the
        shared_secret property.

        Args:
            passcode: The 6-digit TOTP code to verify and activate the factor

        Returns:
            bool: True if activation was successful, False otherwise

        Example:
            >>> factor = user.enroll_factor('token:software:totp', 'GOOGLE', {})
            >>> # User scans QR code or uses shared_secret
            >>> factor.activate('123456')
            True

        """
        if not self.activation_link:
            self._logger.error('No activation link available for this factor')
            return False

        payload = {'passCode': passcode}
        response = self._okta.session.post(self.activation_link, data=json.dumps(payload))

        if not response.ok:
            self._logger.error(f'Failed to activate factor: {response.text}')
            return False

        # Update the factor data with the activation response
        self._data = response.json()
        return True


class UserSupportedFactor:
    """Models a supported (but not yet enrolled) user factor from the catalog endpoint.

    Unlike UserFactor, these factors don't have an ID yet since they're not enrolled.
    They represent factor types that can be enrolled for a user.
    """

    def __init__(self, okta_instance: Okta, user_data: dict[str, Any], data: dict[str, Any]) -> None:
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
