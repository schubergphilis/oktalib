# Welcome to oktalib

A library to interface with Okta through it's restful API.

## Overview

oktalib provides a simple, object-oriented interface to Okta's REST API. It handles authentication, pagination, rate limiting, and provides convenient Python objects for working with Okta resources like users, groups, and applications.

## Key Features

- **Automatic Rate Limiting**: Built-in exponential backoff when API limits are reached
- **Pagination Support**: Automatically handles paginated responses
- **Entity Objects**: Work with Groups, Users, Applications, and Admin Roles as Python objects
- **Property Setters**: Update Okta resources using simple property assignment
- **Lifecycle Management**: Easily activate, deactivate, suspend, and unlock users

## Quick Example

```python
from oktalib import Okta

# Initialize the client
okta = Okta(host='https://your-domain.okta.com', token='your-api-token')

# Get a user
user = okta.get_user_by_login('user@example.com')

# Update user properties
user.first_name = 'John'
user.department = 'Engineering'

# List all groups
for group in okta.groups:
    print(f'{group.name}: {group.description}')

# Add user to a group
group = okta.get_group_by_name('Developers')
group.add_user_by_id(user.id)
```

## Getting Started

- [Installation](installation.md) - How to install oktalib
- [Usage Guide](usage.md) - Detailed usage examples
- [API Reference](api.md) - Complete API documentation
- [Contributing](contributing.md) - How to contribute to the project

## Project Information

- **License**: MIT
- **Python Version**: >= 3.12
- **Source Code**: [GitHub Repository](https://github.com/schubergphilis/oktalib)
