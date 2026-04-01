#!/usr/bin/env python
# File: groups.py
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
Group-related entities.

.. _Google Python Style Guide:
   https://google.github.io/styleguide/pyguide.html

"""

from __future__ import annotations

import json
from collections.abc import Generator
from datetime import datetime
from typing import TYPE_CHECKING, Any

from cachetools import TTLCache, cached

from oktalib.oktalibexceptions import InvalidApplication, InvalidGroup, InvalidUser

from .core import Entity
from .registry import get_entity, register_entity

if TYPE_CHECKING:
    from oktalib.oktalib import Okta

    from .apps import Application
    from .users import User

__author__ = 'Yorick Hoorneman <yhoorneman@schubergphilis.com>'
__docformat__ = 'google'
__date__ = '2026-03-24'
__copyright__ = 'Copyright 2026, Yorick Hoorneman'
__credits__ = ['Yorick Hoorneman']
__license__ = 'MIT'
__maintainer__ = 'Yorick Hoorneman'
__email__ = '<yhoorneman@schubergphilis.com>'
__status__ = 'Development'  # "Prototype", "Development", "Production".


@register_entity('Group')
class Group(Entity):
    """Models the group object of okta."""

    def __init__(self, okta_instance: Okta, data: dict[str, Any]) -> None:
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
    def users(self) -> Generator[User, None, None]:
        """The users of the group.

        Returns:
            generator: A generator of User objects for the users of the group

        """
        User = get_entity('User')  # pylint: disable=invalid-name
        url = self._data.get('_links', {}).get('users', {}).get('href')
        for data in self._okta._get_paginated_url(url):  # noqa: SLF001
            yield User(self._okta, data)

    @property
    def applications(self) -> Generator[Application, None, None]:
        """The applications of the group.

        Returns:
            generator: A generator of Application objects for the applications
                of the group

        """
        Application = get_entity('Application')  # pylint: disable=invalid-name
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


@register_entity('GroupAssignment')
class GroupAssignment(Group):
    """Models the group assignment object of okta for apps."""

    def __init__(self, okta_instance: Okta, data: dict[str, Any]) -> None:
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
