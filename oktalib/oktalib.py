#!/usr/bin/env python
# -*- coding: utf-8 -*-
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
Main code for oktalib

.. _Google Python Style Guide:
   http://google.github.io/styleguide/pyguide.html

"""

import logging
import json
from requests import Session
from .oktalibexceptions import (AuthFailed,
                                InvalidGroup,
                                InvalidApplication)
from .entities import (Group,
                       User,
                       Application)

__author__ = '''Costas Tyfoxylos <ctyfoxylos@schubergphilis.com>'''
__docformat__ = '''google'''
__date__ = '''2018-01-08'''
__copyright__ = '''Copyright 2018, Costas Tyfoxylos'''
__credits__ = ["Costas Tyfoxylos"]
__license__ = '''MIT'''
__maintainer__ = '''Costas Tyfoxylos'''
__email__ = '''<ctyfoxylos@schubergphilis.com>'''
__status__ = '''Development'''  # "Prototype", "Development", "Production".

# This is the main prefix used for logging
LOGGER_BASENAME = '''oktalib'''
LOGGER = logging.getLogger(LOGGER_BASENAME)
LOGGER.addHandler(logging.NullHandler())


class Okta:
    """Models the api of okta"""

    def __init__(self, host, token):
        logger_name = u'{base}.{suffix}'.format(base=LOGGER_BASENAME,
                                                suffix=self.__class__.__name__)
        self._logger = logging.getLogger(logger_name)
        self.host = host
        self.api = '{host}/api/v1'.format(host=host)
        self.token = token
        self.session = self._setup_session()

    def _setup_session(self):
        session = Session()
        session.get(self.host)
        session.headers.update({'accept': 'application/json',
                                'content-type': 'application/json',
                                'authorization': 'SSWS {}'.format(self.token)})
        url = '{api}/users/me/'.format(api=self.api)
        response = session.get(url)
        if not response.ok:
            raise AuthFailed(response.content)
        return session

    @property
    def groups(self):
        """The groups configured in okta

        Returns:
            list: The list of groups configured in okta

        """
        url = '{api}/groups'.format(api=self.api)
        return [Group(self, data) for data in self._get_paginated_url(url)]

    def create_group(self, name, description):
        """Creates a group in okta

        Args:
            name: The name of the group to create
            description: The description of the group to create

        Returns:
            The created group object on success, None otherwise

        """
        url = '{api}/groups'.format(api=self.api)
        payload = {'profile': {'name': name,
                               'description': description}}
        response = self.session.post(url, data=json.dumps(payload))
        if not response.ok:
            self._logger.error(response.json())
        return Group(self, response.json()) if response.ok else None

    def get_group_type_by_name(self, name, group_type='OKTA_GROUP'):
        """Retrieves the group type of okta by name

        Args:
            group_type: The type of okta group to retrieve
            name: The name of the group to retrieve

        Returns:
            Group: The group if a match is found else None

        """
        group = next((group for group in self.search_groups_by_name(name)
                      if group.type == group_type), None)
        return group

    def get_group_by_name(self, name):
        """Retrieves the first group (of any type) by name

        Args:
            name: The name of the group to retrieve

        Returns:
            Group: The group if a match is found else None

        """
        return next((group for group in self.search_groups_by_name(name)
                     if group.name == name), None)

    def search_groups_by_name(self, name):
        """Retrieves the groups (of any type) by name

        Args:
            name: The name of the groups to retrieve

        Returns:
            list: A list of groups if a match is found else an empty list

        """
        url = '{api}/groups?q={name}'.format(api=self.api, name=name)
        response = self.session.get(url)
        if not response.ok:
            self._logger.error(response.json())
        return [Group(self, data) for data in response.json()] if response.ok else []

    def delete_group(self, name):
        """Deletes a group from okta

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

    def _get_paginated_url(self, url, result_limit=100):
        results = []
        params = {'limit': result_limit}
        try:
            response = self.session.get(url, params=params)
            results.extend(response.json())
            next_link = self._get_next_link(response)
            while next_link:
                response = self.session.get(next_link)
                results.extend(response.json())
                next_link = self._get_next_link(response)
            return results
        except ValueError:
            self._logger.error('Error getting url :%s', url)
            return []

    @staticmethod
    def _get_next_link(response):
        links = response.headers.get('Link')
        if links:  # pylint: disable=no-else-return
            link_text = next((link for link in links.split(',')
                              if 'next' in link), None)
            if link_text:  # pylint: disable=no-else-return
                link = link_text.split('>')[0].split('<')[1]
                return link
            else:
                return False
        else:
            return False

    @property
    def users(self):
        """The users configured in okta

        Returns:
            list: The list of users configured in okta

        """
        url = '{api}/users'.format(api=self.api)
        return [User(self, data) for data in self._get_paginated_url(url)]

    def create_user(self,  # pylint: disable=too-many-arguments
                    first_name,
                    last_name,
                    email,
                    login,
                    password=None,
                    enabled=True):
        """Creates a user in okta

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
        enabled = 'true' if enabled else 'false'
        url = '{api}/users?activate={enabled}'.format(api=self.api, enabled=enabled)
        payload = {'profile': {'firstName': first_name,
                               'lastName': last_name,
                               'email': email,
                               'login': login}}
        if password:
            payload.update({'credentials': {'password': {'value': password}}})
        response = self.session.post(url, data=json.dumps(payload))
        if not response.ok:
            self._logger.error(response.json())
        return User(self, response.json()) if response.ok else None

    def get_user_by_login(self, login):
        """Retrieves a user by login

        Args:
            login: The login to match the user with

        Returns:
            User: The user if found, None otherwise

        """
        url = '{api}/users?filter=profile.login+eq+"{login}"'.format(api=self.api, login=login)
        response = self.session.get(url)
        if not response.ok:
            self._logger.error(response.json())
            return None
        return next((User(self, data) for data in response.json()
                     if data.get('profile', {}).get('login', '') == login), None)

    def search_users(self, value):
        """Retrieves a list of users by looking into name, last name and email

        Args:
            value: The value to match with

        Returns:
            list: The users if found, empty list otherwise

        """
        url = '{api}/users?q={value}'.format(api=self.api, value=value)
        response = self.session.get(url)
        if not response.ok:
            self._logger.error(response.json())
        return [User(self, data) for data in response.json()]

    def search_users_by_email(self, email):
        """Retrieves a list of users by email

        Args:
            email: The email to match the user with

        Returns:
            list: The users if found, empty list otherwise

        """
        url = '{api}/users?filter=profile.email+eq+"{email}"'.format(api=self.api, email=email)
        response = self.session.get(url)
        if not response.ok:
            self._logger.error(response.json())
        return [User(self, data) for data in response.json()]

    @property
    def applications(self):
        """The applications configured in okta

        Returns:
            list: The list of applications configured in okta

        """
        url = '{api}/apps'.format(api=self.api)
        response = self.session.get(url)
        if not response.ok:
            self._logger.error(response.json())
        return [Application(self, data) for data in response.json()]

    def get_application_by_id(self, id_):
        """Retrieves an application by id

        Args:
            id_: The id of the application to retrieve

        Returns:

        """
        app = next((app for app in self.applications
                    if app.id == id_), None)
        return app

    def get_application_by_label(self, label):
        """Retrieves an application by label

        Args:
            label: The label of the application to retrieve

        Returns:

        """
        app = next((app for app in self.applications
                    if app.label.lower() == label.lower()), None)
        return app

    def assing_group_to_application(self, application_label, group_name):
        """Assigns a group to an application

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

    def remove_group_from_application(self, application_label, group_name):
        """Removes a group from an application

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
