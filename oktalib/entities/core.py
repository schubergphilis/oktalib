#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File: core.py
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
Main code for core

.. _Google Python Style Guide:
   http://google.github.io/styleguide/pyguide.html

"""

import logging

from dateutil.parser import parse

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
LOGGER_BASENAME = '''core'''
LOGGER = logging.getLogger(LOGGER_BASENAME)
LOGGER.addHandler(logging.NullHandler())


class Entity:
    """The core object of okta"""

    def __init__(self, okta_instance, data):
        logger_name = u'{base}.{suffix}'.format(base=LOGGER_BASENAME,
                                                suffix=self.__class__.__name__)
        self._logger = logging.getLogger(logger_name)
        self._okta = okta_instance
        self._data = self._parse_data(data)

    def _parse_data(self, data):
        if not isinstance(data, dict):
            self._logger.error('Invalid data received :{}'.format(data))
            data = {}
        return data

    @property
    def url(self):
        """The url of the entity

        Returns:
             None in the core entity.

        All objects inheriting from this would either expose this from their data or construct
        and overwrite this.

        """
        return None

    @property
    def id(self):  # pylint: disable=invalid-name
        """The id of the entity

        Returns:
            basestring: The internal id of the entity

        """
        return self._data.get('id')

    @property
    def created_at(self):
        """The date and time of the group's creation

        Returns:
            datetime: The datetime object of when the group was created

        """
        return self._get_date_from_key('created')

    @property
    def last_updated_at(self):
        """The date and time of the entity's last update

        Returns:
            datetime: The datetime object of when the entity was last updated

        """
        return self._get_date_from_key('lastUpdated')

    def _get_date_from_key(self, name):
        try:
            date_ = parse(self._data.get(name))
        except (ValueError, TypeError):
            date_ = None
        return date_

    def _update(self):
        response = self._okta.session.get(self.url)
        if not response.ok:
            self._logger.error(('Error getting entities data. '
                                'Response :{}').format(response.text))
            return False
        self._data = response.json()
        return True
