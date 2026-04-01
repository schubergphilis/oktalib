#!/usr/bin/env python
# File: registry.py
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
Entity registry for avoiding circular imports.

.. _Google Python Style Guide:
   https://google.github.io/styleguide/pyguide.html

"""

from __future__ import annotations

from collections.abc import Callable

__author__ = 'Yorick Hoorneman <yhoorneman@schubergphilis.com>'
__docformat__ = 'google'
__date__ = '2026-03-31'
__copyright__ = 'Copyright 2026, Yorick Hoorneman'
__credits__ = ['Yorick Hoorneman']
__license__ = 'MIT'
__maintainer__ = 'Yorick Hoorneman'
__email__ = '<yhoorneman@schubergphilis.com>'
__status__ = 'Development'  # "Prototype", "Development", "Production".

_entity_registry: dict[str, type] = {}


def register_entity[T](name: str) -> Callable[[type[T]], type[T]]:
    """Decorator to register an entity class in the global registry.

    Args:
        name: The name to register the entity under

    Returns:
        The decorator function that registers the class

    """

    def wrapper(cls: type[T]) -> type[T]:
        """Register the class and return it unchanged.

        Args:
            cls: The class to register

        Returns:
            The same class, unchanged

        """
        _entity_registry[name] = cls
        return cls

    return wrapper


def get_entity(name: str) -> type:
    """Look up an entity class from the registry.

    Args:
        name: The name of the entity to look up

    Returns:
        The entity class

    Raises:
        KeyError: If the entity name is not registered

    """
    if name not in _entity_registry:
        raise KeyError(f"Entity '{name}' not registered")
    return _entity_registry[name]
