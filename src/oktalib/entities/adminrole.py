#!/usr/bin/env python
# File: adminrole.py
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
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#  FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#  DEALINGS IN THE SOFTWARE.
#
"""
Admin-related entities.

.. _Google Python Style Guide:
   https://google.github.io/styleguide/pyguide.html

"""

from datetime import datetime

from .core import Entity

__author__ = 'Yorick Hoorneman <yhoorneman@schubergphilis.com>'
__docformat__ = 'google'
__date__ = '2026-03-24'
__copyright__ = 'Copyright 2026, Yorick Hoorneman'
__credits__ = ['Yorick Hoorneman']
__license__ = 'MIT'
__maintainer__ = 'Yorick Hoorneman'
__email__ = '<yhoorneman@schubergphilis.com>'
__status__ = 'Development'  # "Prototype", "Development", "Production".


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
