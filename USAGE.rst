=====
Usage
=====


To develop on oktalib:

.. code-block:: bash

    # The following commands require pipenv as a dependency

    # To lint the project
    _CI/scripts/lint.py

    # To execute the testing
    _CI/scripts/test.py

    # To create a graph of the package and dependency tree
    _CI/scripts/graph.py

    # To build a package of the project under the directory "dist/"
    _CI/scripts/build.py

    # To see the package version
    _CI/scipts/tag.py

    # To bump semantic versioning [--major|--minor|--patch]
    _CI/scipts/tag.py --major|--minor|--patch

    # To upload the project to a pypi repo if user and password are properly provided
    _CI/scripts/upload.py

    # To build the documentation of the project
    _CI/scripts/document.py



To use oktalib in a project:

.. code-block:: python

    from oktalib import Okta
    okta = Okta(url, token)


    # Working with groups

    # enumerate groups in okta
    for group in okta.groups:
        print group.name

    # create a group
    group = okta.create_group(GROUP_NAME, GROUP_DESCRIPTION)

    # or get an existing one
    group = okta.get_group_by_name(GROUP_NAME)

    # delete a group
    okta.delete_group(GROUP_NAME)

    # or
    group = okta.get_group_by_name(GROUP_NAME)
    group.delete()

    # add a user to a group
    group.add_user_by_login(USERNAME)


    # Working with users

    # enumerate users in okta
    for user in okta.users:
        print user.login

    # create a user
    user = okta.create_user(FIRST_NAME,
                            LAST_NAME,
                            EMAIL,
                            OKTA_USERNAME)

    # or get an existing one
    user = okta.get_user_by_login(USER_LOGIN)

    # delete a user
    okta.delete_user(USER_NAME)

    # get groups of reference user
    user = okta.get_user_by_login(USER_LOGIN)
    groups = user.get_member_groups()
    # or
    user = okta.get_user_by_login(USER_LOGIN)
    user.delete()


