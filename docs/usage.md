# Usage Guide

This guide covers common usage patterns for oktalib.

## Authentication

First, initialize the Okta client with your domain and API token:

```python
from oktalib import Okta

okta = Okta(
    host='https://your-domain.okta.com',
    token='your-api-token'
)
```

The client will automatically validate your credentials on initialization and raise `AuthFailed` if authentication fails.

## Working with Groups

### List All Groups

```python
# Iterate through all groups
for group in okta.groups:
    print(f'{group.name}: {group.description}')
```

### Find a Group

```python
# Get a specific group by name
group = okta.get_group_by_name('Developers')

# Get a specific type of group by name
group = okta.get_group_type_by_name('Developers', group_type='OKTA_GROUP')

# Get a group by ID
group = okta.get_group_by_id('00g1234567890abcdef')

# Search for groups by name (partial match)
groups = okta.search_groups_by_name('Dev')  # Returns list
```

### Create a Group

```python
group = okta.create_group(
    name='Engineering',
    description='Engineering team members'
)
```

### Update a Group

```python
group = okta.get_group_by_name('Engineering')

# Update properties
group.name = 'Engineering Team'
group.description = 'All engineering team members'
```

### Delete a Group

```python
# Delete by name
okta.delete_group('Old Group Name')

# Or delete via group object
group = okta.get_group_by_name('Temporary Group')
group.delete()
```

### Manage Group Members

```python
group = okta.get_group_by_name('Developers')

# Add user to group
group.add_user_by_login('user@example.com')
group.add_user_by_id('00u1234567890abcdef')

# Remove user from group
group.remove_user_by_login('user@example.com')
group.remove_user_by_id('00u1234567890abcdef')

# List group members
for user in group.users:
    print(f'{user.login}: {user.first_name} {user.last_name}')
```

## Working with Users

### List All Users

```python
for user in okta.users:
    print(f'{user.login}: {user.status}')
```

### Find a User

```python
# Get user by login
user = okta.get_user_by_login('user@example.com')

# Search users (searches name, last name, and email)
users = okta.search_users('john')

# Search by email
users = okta.search_users_by_email('user@example.com')
```

### Create a User

```python
# Create with password
user = okta.create_user(
    first_name='John',
    last_name='Doe',
    email='john.doe@example.com',
    login='john.doe@example.com',
    password='SecurePassword123!',
    enabled=True
)

# Create without password (activation email will be sent)
user = okta.create_user(
    first_name='Jane',
    last_name='Smith',
    email='jane.smith@example.com',
    login='jane.smith@example.com',
    enabled=True
)
```

### Update User Profile

```python
user = okta.get_user_by_login('user@example.com')

# Update individual properties
user.first_name = 'John'
user.last_name = 'Doe'
user.email = 'new.email@example.com'
user.mobile_phone = '+1-555-123-4567'
user.department = 'Engineering'
user.title = 'Senior Engineer'
user.manager = 'manager@example.com'

# Update multiple properties at once
user.update_profile({
    'profile': {
        'firstName': 'John',
        'department': 'Engineering',
        'title': 'Senior Engineer'
    }
})
```

### User Lifecycle Management

```python
user = okta.get_user_by_login('user@example.com')

# Activate user
user.activate()

# Deactivate user
user.deactivate()

# Suspend user
user.suspend()

# Unsuspend user
user.unsuspend()

# Unlock user
user.unlock()

# Delete user (must be deactivated first)
user.delete()
```

### Password Management

```python
user = okta.get_user_by_login('user@example.com')

# Set a password
user.set_password('NewSecurePassword123!')

# Update password (requires old password)
user.update_password('OldPassword123!', 'NewPassword123!')

# Expire password (force password change on next login)
user.expire_password()

# Reset password
user.reset_password()

# Set temporary password
temp_password = user.set_temporary_password()
print(f'Temporary password: {temp_password}')
```

### User Groups and Roles

```python
user = okta.get_user_by_login('user@example.com')

# List user's groups
for group in user.groups:
    print(f'{group.name}: {group.type}')

# List user's admin roles
for role in user.roles:
    print(f'{role.label}: {role.type}')

# Assign admin role
okta.assign_role_to_user_by_id(user.id, 'USER_ADMIN')

# Remove admin role
roles = okta.get_user_assigned_roles_by_id(user.id)
for role in roles:
    okta.remove_role_from_user_by_id(user.id, role.id)
```

## Working with Applications

### List All Applications

```python
for app in okta.applications:
    print(f'{app.label}: {app.status}')
```

### Find an Application

```python
# Get by label
app = okta.get_application_by_label('AWS')

# Get by ID
app = okta.get_application_by_id('0oa1234567890abcdef')
```

### Application Lifecycle

```python
app = okta.get_application_by_label('My App')

# Activate application
app.activate()

# Deactivate application
app.deactivate()
```

### Manage Application Groups

```python
app = okta.get_application_by_label('AWS')

# Add group to application
okta.assign_group_to_application('AWS', 'Developers')

# Or via application object
app.add_group_by_name('Developers')
app.add_group_by_id('00g1234567890abcdef')

# Remove group from application
okta.remove_group_from_application('AWS', 'Developers')

# Or via application object
app.remove_group_by_name('Developers')
app.remove_group_by_id('00g1234567890abcdef')

# List application groups
for group in app.groups:
    print(f'{group.name}')

# Get group assignments (includes profile info)
for assignment in app.group_assignments:
    print(f'{assignment.name}: Priority {assignment.priority}')
    print(f'  Role: {assignment.profile_role}')
    print(f'  SAML Roles: {assignment.profile_saml_roles}')
```

### SAML Applications

```python
app = okta.get_application_by_label('AWS')

# Get SAML roles
saml_roles = app.get_associated_saml_roles()

# Assign group with SAML roles
app.assign_group_to_saml_user_roles(
    group_id='00g1234567890abcdef',
    role='arn:aws:iam::123456789012:role/OktaRole',
    saml_roles=[
        'arn:aws:iam::123456789012:role/Developer',
        'arn:aws:iam::987654321098:role/PowerUser'
    ]
)
```

### Application Users

```python
app = okta.get_application_by_label('My App')

# List application users
for user in app.users:
    print(f'{user.login}')

# Get user assignments (includes profile info)
for assignment in app.user_assignments:
    print(f'{assignment.email}')
    print(f'  Role: {assignment.profile_role}')

# Find specific user assignment
assignment = app.get_user_assignment_by_email('user@example.com')
```

## Error Handling

```python
from oktalib import Okta, AuthFailed, InvalidGroup, InvalidUser, ApiLimitReached, ServerError

try:
    okta = Okta(host='https://your-domain.okta.com', token='bad-token')
except AuthFailed as e:
    print(f'Authentication failed: {e}')

try:
    okta.delete_group('NonExistentGroup')
except InvalidGroup as e:
    print(f'Group not found: {e}')

try:
    # API calls with rate limiting are handled automatically
    for user in okta.users:
        print(user.login)
except ApiLimitReached:
    # This exception is caught and retried automatically by the library
    # You typically won't see this unless max retries are exceeded
    print('API rate limit exceeded')
except ServerError as e:
    print(f'Server error: {e}')
```

## Advanced Usage

### Pagination

The library automatically handles pagination for all list operations:

```python
# This will automatically fetch all pages
all_users = list(okta.users)  # Be careful with large datasets!

# Better: iterate without loading all into memory
for user in okta.users:
    if user.status == 'ACTIVE':
        print(user.login)
```

### Rate Limiting

The library automatically handles rate limiting with exponential backoff. When a 429 (rate limit) response is received, it will retry with increasing delays up to 60 seconds.

This is transparent to your code - you don't need to handle it manually.

## Next Steps

- [API Reference](api.md) - Complete API documentation
- [Contributing](contributing.md) - Contribute to the project
