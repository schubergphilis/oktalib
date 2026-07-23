#!/usr/bin/env python
# File: features.py
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
Feature-related entities.

.. _Google Python Style Guide:
   https://google.github.io/styleguide/pyguide.html

"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

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


class Feature(Entity):
    """Models the feature object of okta."""

    @property
    def url(self) -> str:
        """The url of the feature.

        Returns:
            string: The url of the feature

        """
        return f'{self._okta.api}/features/{self.id}'

    @property
    def name(self) -> str | None:
        """The name of the feature.

        Returns:
            string: The name of the feature

        """
        return self._data.get('name')

    @property
    def description(self) -> str | None:
        """The description of the feature.

        Returns:
            string: The description of the feature

        """
        return self._data.get('description')

    @property
    def status(self) -> str | None:
        """The status of the feature.

        Returns:
            string: The status of the feature

        """
        return self._data.get('status')

    @property
    def type(self) -> str | None:
        """The type of the feature.

        Returns:
            string: The type of the feature

        """
        return self._data.get('type')

    @property
    def stage(self) -> dict[str, Any]:
        """The stage of the feature.

        Returns:
            dictionary: The stage of the feature containing state and value

        """
        return self._data.get('stage', {})

    @property
    def stage_state(self) -> str | None:
        """The stage state of the feature.

        Returns:
            string: The stage state of the feature, or None if not present

        """
        return self.stage.get('state')

    @property
    def stage_value(self) -> str | None:
        """The stage value of the feature.

        Returns:
            string: The stage value of the feature, or None if not present

        """
        return self.stage.get('value')

    def dependencies(self) -> Generator[Feature, None, None]:
        """The dependencies of the feature.

        Returns:
            generator: A generator of Feature objects for the dependencies of the feature

        """
        return self._okta.get_feature_dependencies_by_id(self.id)

    def dependents(self) -> Generator[Feature, None, None]:
        """The dependents of the feature.

        Returns:
            generator: A generator of Feature objects for the dependents of the feature

        """
        return self._okta.get_feature_dependents_by_id(self.id)

    def update_feature(self, lifecycle: str, force: bool) -> bool:
        """Updates a feature's lifecycle status.

        Use this endpoint to enable or disable a feature for your org.
        Use the mode=force parameter to override dependency restrictions for a
        particular feature. Normally, you can't enable a feature if it has one
        or more dependencies that aren't enabled.

        When you use the mode=force parameter while enabling a feature, Okta
        first tries to enable any disabled features that this feature may have
        as dependencies. If you don't pass the mode=force parameter and the
        feature has dependencies that need to be enabled before the feature is
        enabled, a 400 error is returned.

        When you use the mode=force parameter while disabling a feature, Okta
        first tries to disable any enabled features that this feature may have
        as dependents. If you don't pass the mode=force parameter and the
        feature has dependents that need to be disabled before the feature is
        disabled, a 400 error is returned.

        Args:
            lifecycle: Either 'enable' or 'disable'
            force: Whether to override dependency restrictions

        Returns:
            bool: True if the feature was updated and its local state
                refreshed, False otherwise

        Raises:
            ValueError: If lifecycle is not 'enable' or 'disable'

        """
        if lifecycle not in ('enable', 'disable'):
            raise ValueError(f"lifecycle must be 'enable' or 'disable', got {lifecycle!r}")
        url = (
            f'{self._okta.api}/features/{self.id}/{lifecycle}'
            if not force
            else f'{self._okta.api}/features/{self.id}/{lifecycle}?mode=force'
        )
        response = self._okta.session.post(url)
        if not response.ok:
            self._logger.error(f'Updating feature failed. Response: {response.text}')
        return response.ok and self._update()
