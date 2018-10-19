#!/usr/bin/env python
# -*- coding: utf-8 -*-
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
#  pylint: disable=too-many-lines
"""
Main code for entities

.. _Google Python Style Guide:
   http://google.github.io/styleguide/pyguide.html

"""

import json
import logging

from oktalib.oktalibexceptions import (InvalidApplication,
                                       InvalidUser,
                                       InvalidGroup)
from .core import Entity

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
LOGGER_BASENAME = '''entities'''
LOGGER = logging.getLogger(LOGGER_BASENAME)
LOGGER.addHandler(logging.NullHandler())


class Group(Entity):
    """Models the group object of okta"""

    def __init__(self, okta_instance, data):
        Entity.__init__(self, okta_instance, data)

    @property
    def url(self):
        """The url of the group

        Returns:
            string: The url of the group

        """
        return '{api}/groups/{id_}'.format(api=self._okta.api, id_=self.id)

    @property
    def type(self):
        """The type of the group

        Returns:
            string: The name of the type of the group

        """
        return self._data.get('type')

    @property
    def profile(self):
        """The profile of the group

        Returns:
            dict: The profile of the group

        """
        return self._data.get('profile')

    @property
    def name(self):
        """The name of the group

        Returns:
            string: The name of the group

        """
        return self._data.get('profile', {}).get('name')

    @name.setter
    def name(self, value):
        url = '{api}/groups/{id_}'.format(api=self._okta.api, id_=self.id)
        payload = {'profile': {'name': value,
                               'description': self.description}}
        response = self._okta.session.put(url, data=json.dumps(payload))
        if not response.ok:
            self._logger.error(('Setting name failed. '
                                'Response :{}').format(response.text))
        else:
            self._update()

    @property
    def description(self):
        """The description of the group

        Returns:
            string: The description of the group

        """
        return self._data.get('profile', {}).get('description')

    @description.setter
    def description(self, value):
        url = '{api}/groups/{id_}'.format(api=self._okta.api, id_=self.id)
        payload = {'profile': {'name': self.name,
                               'description': value}}
        response = self._okta.session.put(url, data=json.dumps(payload))
        if not response.ok:
            self._logger.error(('Setting description failed. '
                                'Response :{}').format(response.text))
        else:
            self._update()

    @property
    def last_membership_updated_at(self):
        """The date and time of the group's last membership update

        Returns:
            datetime: The datetime object of when the group's memberships were last updated

        """
        return self._get_date_from_key('lastMembershipUpdated')

    @property
    def object_classes(self):
        """The classes of the group

        Returns:
            tuple: The tuple of the classes of the group

        """
        return tuple(self._data.get('objectClass'))

    @property
    def users(self):
        """The users of the group

        Returns:
            list: A list of User objects for the users of the group

        """
        url = self._data.get('_links', {}).get('users', {}).get('href')
        return [User(self._okta, data) for data in self._okta._get_paginated_url(url)]  # pylint: disable=protected-access

    @property
    def applications(self):
        """The applications of the group

        Returns:
            list: A list of Application objects for the applications of the group

        """
        url = self._data.get('_links', {}).get('apps', {}).get('href')
        return [Application(self._okta, data) for data in self._okta._get_paginated_url(url)]  # pylint: disable=protected-access

    def delete(self):
        """Deletes the group from okta

        Returns:
            bool: True on success, False otherwise

        """
        url = '{api}/groups/{id}'.format(api=self._okta.api, id=self.id)
        response = self._okta.session.delete(url)
        return response.ok

    def add_to_application_with_label(self, application_label):
        """Adds the group to an application

        Args:
            application_label: The label of the application to add the group to

        Returns:
            True on success, False otherwise

        """
        application = self._okta.get_application_by_label(application_label)
        if not application:
            raise InvalidApplication(application_label)
        return application.add_group_by_id(self.id)

    def remove_from_application_with_label(self, application_label):
        """Removes the group from an application

        Args:
            application_label: The label of the application to remove the group from

        Returns:
            True on success, False otherwise

        """
        application = self._okta.get_application_by_label(application_label)
        if not application:
            raise InvalidApplication(application_label)
        return application.remove_group_by_id(self.id)

    def add_user_by_login(self, login):
        """Adds a user to the group

        Args:
            login: The login of the user to add

        Returns:
            True on success, False otherwise

        """
        user = next((user for user in self._okta.users
                     if user.login.lower() == login.lower()), None)
        if not user:
            raise InvalidUser(login)
        url = '{api}/groups/{id_}/users/{user_id}'.format(api=self._okta.api,
                                                          id_=self.id,
                                                          user_id=user.id)
        response = self._okta.session.put(url)
        if not response.ok:
            self._logger.error(('Adding user failed '
                                'Response :{}').format(response.text))
        return response.ok

    def remove_user_by_login(self, login):
        """Removes a user from the group

        Args:
            login: The login of the user to remove

        Returns:
            True on success, False otherwise

        """
        user = next((user for user in self._okta.users
                     if user.login == login), None)
        if not user:
            raise InvalidUser(login)
        url = '{api}/groups/{id_}/users/{user_id}'.format(api=self._okta.api,
                                                          id_=self.id,
                                                          user_id=user.id)
        response = self._okta.session.delete(url)
        if not response.ok:
            self._logger.error(('Removing user failed '
                                'Response :{}').format(response.text))
        return response.ok

    def add_user_by_id(self, id_):
        """Adds a user to the group

        Args:
            id_: The id of the user to add

        Returns:
            True on success, False otherwise

        """
        url = '{api}/groups/{id_}/users/{user_id}'.format(api=self._okta.api,
                                                          id_=self.id,
                                                          user_id=id_)
        response = self._okta.session.put(url)
        if not response.ok:
            self._logger.error(('Adding user failed '
                                'Response :{}').format(response.text))
        return response.ok

    def remove_user_by_id(self, id_):
        """Remove a user from the group

        Args:
            id_: The id of the user to remove

        Returns:
            True on success, False otherwise

        """
        url = '{api}/groups/{id_}/users/{user_id}'.format(api=self._okta.api,
                                                          id_=self.id,
                                                          user_id=id_)
        response = self._okta.session.delete(url)
        if not response.ok:
            self._logger.error(('Removing user failed '
                                'Response :{}').format(response.text))
        return response.ok


class Application(Entity):
    """Models the apps in okta"""

    def __init__(self, okta_instance, data):
        Entity.__init__(self, okta_instance, data)

    @property
    def url(self):
        """The url of the application

        Returns:
            string: The url of the application

        """
        return '{api}/apps/{id_}'.format(api=self._okta.api, id_=self.id)

    @property
    def name(self):
        """The name of the application

        Returns:
            basestring: The name of the application

        """
        return self._data.get('name')

    @property
    def label(self):
        """The label of the application

        Returns:
            basestring: The label of the application

        """
        return self._data.get('label')

    @property
    def status(self):
        """The status of the application

        Returns:
            basestring: The status of the application

        """
        return self._data.get('status')

    @property
    def accessibility(self):
        """The accessibility of the application

        Returns:
            dictionary: The accessibility of the application

        """
        return self._data.get('accessibility')

    @property
    def visibility(self):
        """The visibility of the application

        Returns:
            dictionary: The visibility of the application

        """
        return self._data.get('visibility')

    @property
    def features(self):
        """The features of the application

        Returns:
            dictionary: The features of the application

        """
        return self._data.get('features')

    @property
    def sign_on_mode(self):
        """The sign on mode of the application

        Returns:
            basestring: The sign on mode of the application

        """
        return self._data.get('sign_on_mode')

    @property
    def credentials(self):
        """The credentials of the application

        Returns:
            dictionary: The credentials of the application

        """
        return self._data.get('credentials')

    @property
    def settings(self):
        """The settings of the application

        Returns:
            dictionary: The settings of the application

        """
        return self._data.get('settings', {}).get('app')

    @property
    def notification_settings(self):
        """The notification settings of the application

        Returns:
            dictionary: The notification settings of the application

        """
        return self._data.get('settings', {}).get('notifications')

    @property
    def sign_on_settings(self):
        """The sign on settings of the application

        Returns:
            dictionary: The sign on settings of the application

        """
        return self._data.get('settings', {}).get('signOn')

    @property
    def users(self):
        """The users of the application

        Returns:
            list: A list of User objects for the users of the application

        """
        url = self._data.get('_links', {}).get('users', {}).get('href')
        return [User(self._okta, data) for data in self._okta._get_paginated_url(url)]  # pylint: disable=protected-access

    @property
    def groups(self):
        """The groups of the application

        Returns:
            list: A list of Group objects for the groups of the application

        """
        url = self._data.get('_links', {}).get('groups', {}).get('href')
        return [Group(self._okta, data) for data in self._okta._get_paginated_url(url)]  # pylint: disable=protected-access

    @property
    def activate(self):
        """Activates the application

        Returns:
            bool: True on success, False otherwise

        """
        if self.status == 'ACTIVE':
            return True
        url = self._data.get('_links', {}).get('activate').get('href')
        response = self._okta.session.post(url)  # noqa
        if not response.ok:
            self._logger.error('Response :{response}'.format(response=response.text))
        else:
            self._update()
        return response.ok

    @property
    def deactivate(self):
        """Deactivates the application

        Returns:
            bool: True on success, False otherwise

        """
        if self.status == 'INACTIVE':
            return True
        url = self._data.get('_links', {}).get('deactivate').get('href')
        response = self._okta.session.post(url)  # noqa
        if not response.ok:
            self._logger.error('Response :{response}'.format(response=response.text))
        else:
            self._update()
        return response.ok

    def add_group_by_id(self, group_id):
        """Adds a group to the application

        Args:
            group_id: The id of the group to add

        Returns:
            True on success, False otherwise

        """
        url = '{api}/apps/{id_}/groups/{group_id}'.format(api=self._okta.api,
                                                          id_=self.id,
                                                          group_id=group_id)
        response = self._okta.session.put(url)
        if not response.ok:
            self._logger.error(('Adding group failed '
                                'Response :{}').format(response.text))
        return response.ok

    def add_group_by_name(self, group_name):
        """Adds a group to the application

        Args:
            group_name: The name of the group to add

        Returns:
            True on success, False otherwise

        """
        group = self._okta.get_group_by_name(group_name)
        if not group:
            raise InvalidGroup(group_name)
        url = '{api}/apps/{id_}/groups/{group_id}'.format(api=self._okta.api,
                                                          id_=self.id,
                                                          group_id=group.id)
        response = self._okta.session.put(url, data=json.dumps({}))
        if not response.ok:
            self._logger.error(('Adding group failed '
                                'Response :{}').format(response.text))
        return response.ok

    def remove_group_by_id(self, group_id):
        """Removes a group from the application

        Args:
            group_id: The id of the group to remove

        Returns:
            True on success, False otherwise

        """
        url = '{api}/apps/{id_}/groups/{group_id}'.format(api=self._okta.api,
                                                          id_=self.id,
                                                          group_id=group_id)
        response = self._okta.session.delete(url)
        if not response.ok:
            self._logger.error(('Removing group failed '
                                'Response :{}').format(response.text))
        return response.ok

    def remove_group_by_name(self, group_name):
        """Removes a group from the application

        Args:
            group_name: The name of the group to remove

        Returns:
            True on success, False otherwise

        """
        group = self._okta.get_group_by_name(group_name)
        if not group:
            raise InvalidGroup(group_name)
        url = '{api}/apps/{id_}/groups/{group_id}'.format(api=self._okta.api,
                                                          id_=self.id,
                                                          group_id=group.id)
        response = self._okta.session.delete(url)
        if not response.ok:
            self._logger.error(('Adding group failed '
                                'Response :{}').format(response.text))
        return response.ok


class User(Entity):  # pylint: disable=too-many-public-methods
    """Models the user object of okta"""

    def __init__(self, okta_instance, data):
        Entity.__init__(self, okta_instance, data)

    @property
    def url(self):
        """The url of the user

        Returns:
            string: The url of the user

        """
        return self._data.get('_links', {}).get('self', {}).get('href')

    @property
    def status(self):
        """The status of the user

        Returns:
            string: The status of the user

        """
        return self._data.get('status')

    @property
    def activated_at(self):
        """The date and time of the users's activation

        Returns:
            datetime: The datetime object of when the user was activated

        """
        return self._get_date_from_key('activated')

    @property
    def status_changed_at(self):
        """The date and time of the users's status change

        Returns:
            datetime: The datetime object of when the user had last changed status

        """
        return self._get_date_from_key('statusChanged')

    @property
    def last_login_at(self):
        """The date and time of the users's last login

        Returns:
            datetime: The datetime object of when the user last logged in

        """
        return self._get_date_from_key('lastLogin')

    @property
    def password_changed_at(self):
        """The date and time of the users's last password change

        Returns:
            datetime: The datetime object of when the user last changed password

        """
        return self._get_date_from_key('passwordChanged')

    @property
    def first_name(self):
        """The first name of the user

        Returns:
            string: The first name of the user

        """
        return self._data.get('profile', {}).get('firstName')

    @property
    def last_name(self):
        """The last name of the user

        Returns:
            string: The last name of the user

        """
        return self._data.get('profile', {}).get('lastName')

    @property
    def manager(self):
        """The manager of the user

        Returns:
            string: The manager of the user

        """
        return self._data.get('profile', {}).get('manager')

    @property
    def display_name(self):
        """The display name of the user

        Returns:
            string: The display name of the user

        """
        return self._data.get('profile', {}).get('displayName')

    @property
    def title(self):
        """The title of the user

        Returns:
            string: The title of the user

        """
        return self._data.get('profile', {}).get('title')

    @property
    def locale(self):
        """The locale of the user

        Returns:
            string: The locale of the user

        """
        return self._data.get('profile', {}).get('locale')

    @property
    def employee_number(self):
        """The employee number of the user

        Returns:
            string: The employee number of the user

        """
        return self._data.get('profile', {}).get('employeeNumber')

    @property
    def zip_code(self):
        """The zip code of the user

        Returns:
            string: The zip code of the user

        """
        return self._data.get('profile', {}).get('zipCode')

    @property
    def city(self):
        """The city of the user

        Returns:
            string: The city of the user

        """
        return self._data.get('profile', {}).get('city')

    @property
    def street_address(self):
        """The street address of the user

        Returns:
            string: The street address of the user

        """
        return self._data.get('profile', {}).get('streetAddress')

    @property
    def contry_code(self):
        """The contry code of the user

        Returns:
            string: The country code of the user

        """
        return self._data.get('profile', {}).get('countryCode')

    @property
    def organization(self):
        """The organization of the user

        Returns:
            string: The organization of the user

        """
        return self._data.get('profile', {}).get('organization')

    @property
    def department(self):
        """The department of the user

        Returns:
            string: The department of the user

        """
        return self._data.get('profile', {}).get('department')

    @property
    def primary_phone(self):
        """The primary phone of the user

        Returns:
            string: The primary phone of the user

        """
        return self._data.get('profile', {}).get('primaryPhone')

    @property
    def mobile_phone(self):
        """The mobile phone of the user

        Returns:
            string: The mobile phone of the user

        """
        return self._data.get('profile', {}).get('mobilePhone')

    @property
    def email(self):
        """The email of the user

        Returns:
            string: The email of the user

        """
        return self._data.get('profile', {}).get('email')

    @property
    def second_email(self):
        """The second email of the user

        Returns:
            string: The second email of the user

        """
        return self._data.get('profile', {}).get('secondEmail')

    @property
    def login(self):
        """The login of the user

        Returns:
            string: The login of the user

        """
        return self._data.get('profile', {}).get('login')

    @property
    def credentials(self):
        """The credentials of the user

        Returns:
            dictionary: The credentials of the user

        """
        return self._data.get('credentials')

    @property
    def groups(self):
        """Lists the groups the user is a member of

        Returns:
            list: A list of Group objects for which the user is member of

        """
        url = '{api}/users/{id_}/groups'.format(api=self._okta.api, id_=self.id)
        return [Group(self._okta, data) for data in self._okta._get_paginated_url(url)]  # pylint: disable=protected-access

    def delete(self):
        """Deletes the user from okta

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

    def _post_lifecycle(self, url, message):
        response = self._okta.session.post(url)
        if not response.ok:
            error = ('{message}\n'
                     'Response :{response}').format(message=message,
                                                    response=response.text)
            self._logger.error(error)
        else:
            self._update()
        return response.ok

    def activate(self):
        """Activate the user

        Returns:
            True on success, False otherwise

        """
        url = ('{api}/users/{id_}/'
               'lifecycle/activate?sendEmail=false').format(api=self._okta.api,
                                                            id_=self.id)
        return self._post_lifecycle(url, 'Activating user failed')

    def deactivate(self):
        """Deactivate the user

        Returns:
            True on success, False otherwise

        """
        url = '{api}/users/{id_}/lifecycle/deactivate'.format(api=self._okta.api,
                                                              id_=self.id)
        return self._post_lifecycle(url, 'Deactivating user failed')

    def unlock(self):
        """Unlocks the user

        Returns:
            True on success, False otherwise

        """
        url = '{api}/users/{id_}/lifecycle/unlock'.format(api=self._okta.api,
                                                          id_=self.id)
        return self._post_lifecycle(url, 'Unlocking user failed')

    def expire_password(self):
        """Expires the user's password

        Returns:
            True on success, False otherwise

        """
        url = '{api}/users/{id_}/lifecycle/expire_password'.format(api=self._okta.api,
                                                                   id_=self.id)
        return self._post_lifecycle(url, "Expiring user's password failed")

    def reset_password(self):
        """Resets the user's password

        Returns:
            True on success, False otherwise

        """
        url = ('{api}/users/{id_}/lifecycle'
               '/reset_password??sendEmail=false').format(api=self._okta.api,
                                                          id_=self.id)
        return self._post_lifecycle(url, "Reseting user's password failed")

    def set_temporary_password(self):
        """Sets a temporary password for the user

        Returns:
            string: Password on success, None otherwise

        """
        url = ('{api}/users/{id_}/lifecycle'
               '/expire_password?tempPassword=true').format(api=self._okta.api,
                                                            id_=self.id)
        response = self._okta.session.post(url)
        if not response.ok:
            error = ('{message}\n'
                     'Response :{response}').format(message="Setting a temporary password failed",
                                                    response=response.text)
            self._logger.error(error)
        else:
            self._update()
        return response.json().get('tempPassword', None)

    def suspend(self):
        """Suspends the user

        Returns:
            True on success, False otherwise

        """
        url = '{api}/users/{id_}/lifecycle/suspend'.format(api=self._okta.api,
                                                           id_=self.id)
        return self._post_lifecycle(url, "Suspending user failed")

    def unsuspend(self):
        """Unsuspends the user

        Returns:
            True on success, False otherwise

        """
        url = '{api}/users/{id_}/lifecycle/unsuspend'.format(api=self._okta.api,
                                                             id_=self.id)
        return self._post_lifecycle(url, "Unsuspending user failed")

    def update_password(self, old_password, new_password):
        """Changes the user's password

        Returns:
            True on success, False otherwise

        """
        url = '{api}/users/{id_}/credentials/change_password'.format(api=self._okta.api,
                                                                     id_=self.id)
        payload = {'oldPassword': {'value': old_password},
                   'newPassword': {'value': new_password}}
        response = self._okta.session.post(url, data=json.dumps(payload))
        if not response.ok:
            self._logger.error(response.text)
        return response.ok

    def update_profile(self, new_profile):
        """Update a user's profile in okta

        Args:
            new_profile: A object with attributes to change (example: {'profile': {'firstName': 'Test'}})

        Returns:
            Bool: True or False depending on success

        """
        url = '{api}/users/{id_}'.format(api=self._okta.api, id_=self.id)
        response = self._okta.session.post(url, data=json.dumps(new_profile))
        if not response.ok:
            self._logger.error(response.json())
        return True if response.ok else False

    def update_security_question(self, password, question, answer):
        """Changes the user's security question and answer

        Returns:
            True on success, False otherwise

        """
        url = '{api}/users/{id_}/credentials/change_recovery_question'.format(api=self._okta.api,
                                                                              id_=self.id)
        payload = {"password": {"value": password},
                   "recovery_question": {"question": question,
                                         "answer": answer}}
        response = self._okta.session.post(url, data=json.dumps(payload))
        if not response.ok:
            self._logger.error(response.text)
        return response.ok
