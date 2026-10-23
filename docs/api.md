# API Reference

Complete API documentation auto-generated from source code.

## Okta Client

Main client for interacting with the Okta API.

::: oktalib.oktalib.Okta
    options:
      show_source: false
      members: true
      heading_level: 3

## Authenticators

How the client authenticates against an org. Either kind is passed to `Okta` the same way.

### ApiTokenAuthenticator

::: oktalib.oktaauthenticators.ApiTokenAuthenticator
    options:
      show_source: false
      members: true
      heading_level: 4

### ServiceAppAuthenticator

::: oktalib.oktaauthenticators.ServiceAppAuthenticator
    options:
      show_source: false
      members: true
      heading_level: 4

### OktaAuthenticator

The interface both implement, for anyone adding a third.

::: oktalib.oktaauthenticators.OktaAuthenticator
    options:
      show_source: false
      members: true
      heading_level: 4

## Entities

### Group

::: oktalib.entities.groups.Group
    options:
      show_source: false
      members: true
      heading_level: 4

### User

::: oktalib.entities.users.User
    options:
      show_source: false
      members: true
      heading_level: 4

### Application

::: oktalib.entities.apps.Application
    options:
      show_source: false
      members: true
      heading_level: 4

### AdminRole

::: oktalib.entities.adminrole.AdminRole
    options:
      show_source: false
      members: true
      heading_level: 4

### GroupAssignment

::: oktalib.entities.groups.GroupAssignment
    options:
      show_source: false
      members: true
      heading_level: 4

### UserAssignment

::: oktalib.entities.users.UserAssignment
    options:
      show_source: false
      members: true
      heading_level: 4

## Exceptions

::: oktalib.oktalibexceptions
    options:
      show_source: false
      members: true
      heading_level: 3
