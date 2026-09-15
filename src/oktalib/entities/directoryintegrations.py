#!/usr/bin/env python
# File: directoryintegrations.py
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
Directory Integrations entities (agent pools and their agents).

These model what the admin console lists under Directory > Directory
Integrations, which Okta's API exposes as agent pools.

.. _Google Python Style Guide:
   https://google.github.io/styleguide/pyguide.html

"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from .core import Entity, parse_epoch_millis

if TYPE_CHECKING:
    from oktalib.oktalib import Okta

__author__ = 'Yorick Hoorneman <yhoorneman@schubergphilis.com>'
__docformat__ = 'google'
__date__ = '2026-08-10'
__copyright__ = 'Copyright 2026, Yorick Hoorneman'
__credits__ = ['Yorick Hoorneman']
__license__ = 'MIT'
__maintainer__ = 'Yorick Hoorneman'
__email__ = '<yhoorneman@schubergphilis.com>'
__status__ = 'Development'  # "Prototype", "Development", "Production".

LOGGER_BASENAME = 'directoryintegrations'

# The operational status of a healthy agent or pool. Anything else is degraded,
# disrupted or inactive, which is what the console reports as an agent being down.
OPERATIONAL_STATUS = 'OPERATIONAL'


class DirectoryIntegrationsAgent(Entity):
    """Models an agent of a Directory Integrations agent pool.

    Agents arrive embedded in their pool rather than from an endpoint of their
    own, so this entity holds no url; a non-operational one is the admin
    console's "Agent down" task.
    """

    def __init__(self, okta_instance: 'Okta', pool_data: dict[str, Any], data: dict[str, Any]) -> None:
        """Initialize a DirectoryIntegrationsAgent instance.

        Args:
            okta_instance: The Okta instance
            pool_data: The agent pool data the agent belongs to
            data: The agent data from the API response

        """
        super().__init__(okta_instance, data)
        self._pool_data = pool_data

    @property
    def name(self) -> str | None:
        """The name of the agent.

        Returns:
            string: The name of the agent, None if absent

        """
        return self._data.get('name')

    @property
    def type(self) -> str | None:
        """The type of the agent.

        Returns:
            string: The type of the agent, e.g. AD or LDAP. None if absent.

        """
        return self._data.get('type')

    @property
    def operational_status(self) -> str | None:
        """The operational status of the agent.

        Returns:
            string: The status of the agent, one of OPERATIONAL, DEGRADED,
                DISRUPTED or INACTIVE. None if absent.

        """
        return self._data.get('operationalStatus')

    @property
    def is_operational(self) -> bool:
        """Whether the agent is operational.

        An agent whose status is missing is not reported as operational, so a
        caller looking for problems sees it rather than silently skipping it.

        Returns:
            bool: True if the agent is operational, False otherwise

        """
        return self.operational_status == OPERATIONAL_STATUS

    @property
    def last_connection(self) -> datetime | None:
        """The date and time the agent last connected.

        Okta reports this as milliseconds since the epoch rather than the ISO 8601
        string the rest of the API uses, which is why this does not go through the
        entity's usual date handling.

        Returns:
            datetime: The datetime of the last connection in UTC, None if the
                agent has never connected or the field is absent

        """
        return parse_epoch_millis(self._data.get('lastConnection'))

    @property
    def version(self) -> str | None:
        """The installed version of the agent.

        Returns:
            string: The version of the agent, None if absent

        """
        return self._data.get('version')

    @property
    def is_latest_version(self) -> bool:
        """Whether the agent runs the latest generally available version.

        Returns:
            bool: True if the agent is up to date, False otherwise or when the
                field is absent

        """
        return self._data.get('isLatestGAedVersion') is True

    @property
    def is_hidden(self) -> bool:
        """Whether the console hides this agent.

        Returns:
            bool: True if the agent is hidden, False otherwise or when the field
                is absent

        """
        return self._data.get('isHidden') is True

    @property
    def update_status(self) -> str | None:
        """The status of the agent's last self update.

        Absent from the AD agents of the org this was verified against; the field
        is documented in the API spec, so it is exposed for the agent types that
        do report it.

        Returns:
            string: The update status of the agent, None if absent

        """
        return self._data.get('updateStatus')

    @property
    def update_message(self) -> str | None:
        """The message of the agent's last self update.

        Absent from the AD agents of the org this was verified against; see
        :attr:`update_status`.

        Returns:
            string: The update message of the agent, None if absent

        """
        return self._data.get('updateMessage')

    @property
    def pool_id(self) -> str | None:
        """The id of the pool the agent belongs to.

        The agent carries its own ``poolId``; the parent pool is the fallback for
        payloads that omit it.

        Returns:
            string: The id of the parent agent pool, None if absent

        """
        return self._data.get('poolId') or self._pool_data.get('id')


class DirectoryIntegrationsAgentPool(Entity):
    """Models a Directory Integrations agent pool of okta."""

    @property
    def url(self) -> str:
        """The url identifying the agent pool.

        Okta serves no single pool over GET: this path answers 405, not 404, so it
        exists for update operations but cannot be fetched. :meth:`_update`
        therefore refreshes from the listing instead.

        Returns:
            string: The url identifying the agent pool

        """
        return f'{self._okta.session.api}/agentPools/{self.id}'

    def _update(self) -> bool:
        """Refresh the pool data from the listing.

        The inherited implementation would GET :attr:`url`, which Okta rejects with
        405, so the pool is found again in the collection instead.

        Returns:
            bool: True if the pool was found and refreshed, False otherwise

        """
        pool = self._okta.get_directory_integrations_agent_pool_by_id(self.id)
        if pool is None:
            self._logger.error(f'Agent pool {self.id} is no longer in the listing.')
            return False
        self._data = pool._data  # noqa: SLF001
        return True

    @property
    def name(self) -> str | None:
        """The name of the agent pool.

        Returns:
            string: The name of the agent pool, None if absent

        """
        return self._data.get('name')

    @property
    def type(self) -> str | None:
        """The type of the agent pool.

        Returns:
            string: The type of the pool, e.g. AD or LDAP. None if absent.

        """
        return self._data.get('type')

    @property
    def operational_status(self) -> str | None:
        """The operational status of the agent pool.

        Returns:
            string: The status of the pool, one of OPERATIONAL, DEGRADED,
                DISRUPTED or INACTIVE. None if absent.

        """
        return self._data.get('operationalStatus')

    @property
    def is_operational(self) -> bool:
        """Whether the agent pool is operational.

        Returns:
            bool: True if the pool is operational, False otherwise

        """
        return self.operational_status == OPERATIONAL_STATUS

    @property
    def disrupted_agents(self) -> int | None:
        """The number of disrupted agents in the pool, as reported by Okta.

        Returns:
            int: The count of disrupted agents, None if absent

        """
        return self._data.get('disruptedAgents')

    @property
    def inactive_agents(self) -> int | None:
        """The number of inactive agents in the pool, as reported by Okta.

        Returns:
            int: The count of inactive agents, None if absent

        """
        return self._data.get('inactiveAgents')

    @property
    def operational_agents(self) -> int | None:
        """The number of operational agents in the pool, as reported by Okta.

        Okta's three counts add up to the length of :attr:`agents`, so this is
        the figure to reconcile :attr:`down_agents` against.

        Returns:
            int: The count of operational agents, None if absent

        """
        return self._data.get('operationalAgents')

    @property
    def agents(self) -> list[DirectoryIntegrationsAgent]:
        """The agents of the pool.

        The pool listing embeds these, so reading them costs no extra request.

        Returns:
            list: A list of DirectoryIntegrationsAgent objects for the pool,
                empty if absent

        """
        return [DirectoryIntegrationsAgent(self._okta, self._data, data) for data in self._data.get('agents', [])]

    @property
    def down_agents(self) -> list[DirectoryIntegrationsAgent]:
        """The agents of the pool that are not operational.

        These are the agents behind the admin console's "Agent down" task.

        Returns:
            list: A list of DirectoryIntegrationsAgent objects that are not
                operational

        """
        return [agent for agent in self.agents if not agent.is_operational]
