"""Tests for the cassette sanitizer.

The sanitizer is what stands between a recorded org and the repository, so it is
tested directly rather than only through the cassettes it produces.
"""
# pylint: disable=redefined-outer-name

import base64
import gzip
import json

import pytest

from tests.sanitizer import (
    REDACTED,
    host_aliases,
    redact_text,
    sanitize_body,
    sanitize_interaction,
    sanitize_payload,
    sanitize_profile,
)


@pytest.fixture
def user_profile():
    """A user profile with the extensible attributes a real org adds to it."""
    return {
        # Deliberately different: Okta does not require a login to match the email.
        'login': 'someone.real@corp.example.org',
        'email': 's.real.private@corp.example.org',
        'firstName': 'Someone',
        'lastName': 'Real',
        'title': 'Principal Engineer',
        'employeeNumber': '123456',
        'mobilePhone': '+31600000000',
        'manager': 'Another Person',
        'customPasswordHash': '$6$rounds=5000$abcdefgh$0123456789',
        'isContractor': False,
        'costCenter': None,
    }


def test_unknown_profile_attributes_are_redacted(user_profile):
    """An attribute the sanitizer has never heard of must not survive.

    Okta profiles are extensible, so this is the case a denylist would miss.
    """
    sanitized = sanitize_profile(user_profile)
    assert sanitized['title'] == REDACTED
    assert sanitized['employeeNumber'] == REDACTED
    assert sanitized['mobilePhone'] == REDACTED
    assert sanitized['manager'] == REDACTED


def test_profile_keys_are_preserved(user_profile):
    """Every key survives so the payload shape and the redaction stay visible."""
    assert set(sanitize_profile(user_profile)) == set(user_profile)


def test_emails_become_stand_ins(user_profile):
    """Logins and emails are replaced by a stand-in at example.com.

    Both originals are checked, since the login and the email differ.
    """
    sanitized = sanitize_profile(user_profile)
    assert sanitized['login'].endswith('@example.com')
    assert sanitized['email'].endswith('@example.com')
    dumped = json.dumps(sanitized)
    assert user_profile['login'] not in dumped
    assert user_profile['email'] not in dumped


def test_one_email_maps_to_one_stand_in_everywhere():
    """A given email redacts to the same stand-in wherever it appears.

    This is a claim about the *value*, not about the fields: a login and an email
    are independent and often differ. What matters is that redaction is a function
    of the value alone, so the same email is replaced identically no matter which
    key holds it or where in the tree it sits.

    Replay depends on it, because Okta repeats one identity in several places — an
    app user carries its owner's login again under ``credentials.userName`` — and
    the inside-a-profile and outside-a-profile cases run through different branches
    of the sanitizer. If those branches disagreed, a recorded test correlating an
    assignment with its user would break on replay.

    It is also why the stand-in is a digest of the value rather than a counter or a
    random id: with no shared state the same email redacts identically in every
    cassette, and re-sanitizing does not churn the files.
    """
    email = 'someone.real@corp.example.org'
    in_profile = sanitize_profile({'login': email})['login']
    in_other_profile_field = sanitize_profile({'email': email})['email']
    outside_any_profile = sanitize_payload({'credentials': {'userName': email}})['credentials']['userName']

    assert in_profile == in_other_profile_field
    assert in_profile == outside_any_profile


def test_distinct_emails_stay_distinct(user_profile):
    """A login and an email that differ must not be collapsed into one stand-in.

    The reverse of the property above, and the reason the fixture gives the two
    fields different values: redaction must not invent a correspondence that the
    real data does not have.
    """
    sanitized = sanitize_profile(user_profile)
    assert sanitized['login'] != sanitized['email']


def test_different_people_map_to_different_stand_ins():
    """Two users stay distinguishable after redaction."""
    first = sanitize_profile({'login': 'one@corp.example.org'})
    second = sanitize_profile({'login': 'two@corp.example.org'})
    assert first['login'] != second['login']


def test_names_become_labels(user_profile):
    """Personal names are replaced, and no longer appear anywhere in the payload."""
    sanitized = sanitize_profile(user_profile)
    assert sanitized['firstName'].startswith('firstName-')
    assert sanitized['lastName'].startswith('lastName-')
    assert 'Someone' not in json.dumps(sanitized)
    assert 'Real' not in json.dumps(sanitized)


def test_a_secret_parked_in_a_profile_attribute_is_redacted(user_profile):
    """A password hash in a custom attribute needs no special case to be caught.

    The allowlist covers it because the key is not on the allowlist, which is the
    point: no list of known secret names has to anticipate it.
    """
    sanitized = sanitize_profile(user_profile)
    assert sanitized['customPasswordHash'] == REDACTED
    assert '$6$' not in json.dumps(sanitized)


def test_nulls_and_flags_are_kept(user_profile):
    """Neither a null nor a boolean identifies anyone, so both stay readable."""
    sanitized = sanitize_profile(user_profile)
    assert sanitized['costCenter'] is None
    assert sanitized['isContractor'] is False


def test_group_name_survives():
    """Group refuses to build without profile.name, so it must not be redacted."""
    assert sanitize_profile({'name': 'A group'})['name'] == 'A group'


def test_profile_description_is_redacted():
    """description is shared between group and user profiles, so it cannot be kept.

    A recorded user profile carried a person's name in this field, which is why it
    is not on the allowlist despite being harmless on a group.
    """
    assert sanitize_profile({'description': '[Dummy account for a real person]'})['description'] == REDACTED


def test_a_login_outside_a_profile_is_replaced():
    """An app user repeats the login under credentials.userName, outside any profile.

    Scoping the email keys to profiles let this one through into a cassette.
    """
    sanitized = sanitize_payload({'credentials': {'userName': 'someone.real@corp.example.org'}})
    assert sanitized['credentials']['userName'].endswith('@example.com')
    assert 'someone.real' not in json.dumps(sanitized)


def test_a_task_error_string_is_redacted():
    """A provisioning task's error names the affected person, so it cannot be kept.

    The text is free-form and unbounded — one real error echoed back an org's whole
    password policy — so no sample of it survives into a cassette.
    """
    payload = {
        '_embedded': {
            'task': {
                'id': 'aat1',
                'status': 'PROVISIONING_FAILED',
                'errorString': 'Automatic provisioning of user Someone Real to app AD failed: reason',
            }
        }
    }
    sanitized = sanitize_payload(payload)
    task = sanitized['_embedded']['task']
    assert task['errorString'] == REDACTED
    assert task['status'] == 'PROVISIONING_FAILED'
    assert task['id'] == 'aat1'
    assert 'Someone Real' not in json.dumps(sanitized)


def test_okta_error_summaries_are_kept():
    """Okta's own API error messages are generic, and useful when a replay fails."""
    sanitized = sanitize_payload({'errorCode': 'E0000031', 'errorSummary': 'Bad request.'})
    assert sanitized['errorSummary'] == 'Bad request.'


def test_a_name_outside_a_profile_is_replaced():
    """Personal names are replaced wherever they appear, not only inside a profile."""
    sanitized = sanitize_payload({'_embedded': {'user': {'displayName': 'Someone Real'}}})
    assert 'Someone Real' not in json.dumps(sanitized)


def test_app_user_roles_survive():
    """The role fields the library exposes are features, not personal data."""
    sanitized = sanitize_profile({'role': 'Admin', 'samlRoles': ['RoleA', 'RoleB']})
    assert sanitized == {'role': 'Admin', 'samlRoles': ['RoleA', 'RoleB']}


def test_sanitizing_twice_changes_nothing(user_profile):
    """Redaction is idempotent, so re-running it does not churn cassettes."""
    once = sanitize_profile(user_profile)
    assert sanitize_profile(once) == once


def test_secrets_are_redacted_anywhere():
    """Secret keys are redacted regardless of where they sit in the payload."""
    payload = {'credentials': {'oauthClient': {'client_secret': 'sh-secret', 'client_id': '0oa1'}}}
    sanitized = sanitize_payload(payload)
    assert sanitized['credentials']['oauthClient']['client_secret'] == REDACTED
    assert sanitized['credentials']['oauthClient']['client_id'] == '0oa1'


def test_a_nested_secret_cannot_hide_one_level_deeper():
    """credentials.password.value must not survive by being a dict."""
    sanitized = sanitize_payload({'credentials': {'password': {'value': 'hunter2'}}})
    assert sanitized['credentials']['password'] == REDACTED
    assert 'hunter2' not in json.dumps(sanitized)


def test_profiles_inside_a_list_are_redacted():
    """A listing of users is a list of objects, each with its own profile."""
    payload = [{'id': '00u1', 'profile': {'login': 'a@corp.example.org', 'title': 'Boss'}}]
    sanitized = sanitize_payload(payload)
    assert sanitized[0]['profile']['title'] == REDACTED
    assert sanitized[0]['id'] == '00u1'


def test_non_profile_fields_are_untouched():
    """Everything the library asserts on outside a profile is left alone."""
    payload = {'id': '0oa1', 'label': 'An app', 'signOnMode': 'SAML_2_0', 'status': 'ACTIVE'}
    assert sanitize_payload(payload) == payload


def make_body(payload, gzipped=False, base64_encoded=False):
    """Build a cassette body dict in one of the encodings betamax produces."""
    raw = json.dumps(payload).encode()
    if gzipped:
        raw = gzip.compress(raw, mtime=0)
    if base64_encoded:
        return {'base64_string': base64.b64encode(raw).decode('ascii')}
    return {'string': raw.decode()}


def read_body(body):
    """Decode a cassette body dict back to a parsed payload."""
    raw = base64.b64decode(body['base64_string']) if 'base64_string' in body else body['string'].encode()
    if raw[:2] == b'\x1f\x8b':
        raw = gzip.decompress(raw)
    return json.loads(raw)


@pytest.mark.parametrize(
    ('gzipped', 'base64_encoded'),
    [(False, False), (True, True), (False, True)],
    ids=['plain', 'gzipped-base64', 'base64'],
)
def test_bodies_are_redacted_in_every_encoding(gzipped, base64_encoded):
    """A gzipped body is redacted too, which betamax's own placeholders cannot do."""
    body = make_body({'profile': {'login': 'a@corp.example.org', 'title': 'Boss'}}, gzipped, base64_encoded)
    sanitize_body(body, host='')
    assert read_body(body)['profile']['title'] == REDACTED


def test_the_encoding_is_preserved():
    """A gzipped body stays gzipped, so replay still decodes it."""
    body = make_body({'profile': {'title': 'Boss'}}, gzipped=True, base64_encoded=True)
    sanitize_body(body, host='')
    assert gzip.decompress(base64.b64decode(body['base64_string']))


def test_the_real_host_is_replaced():
    """The org host is replaced, matching the placeholder used for the base url."""
    body = make_body({'_links': {'self': {'href': 'https://real.oktapreview.com/api/v1/users/00u1'}}})
    sanitize_body(body, host='real.oktapreview.com')
    assert read_body(body)['_links']['self']['href'] == 'https://example.com/api/v1/users/00u1'


def test_a_non_json_body_is_left_parseable():
    """The SAML metadata endpoint returns XML, which must survive redaction."""
    xml = '<EntityDescriptor entityID="https://real.oktapreview.com/x"/>'
    body = {'string': xml}
    sanitize_body(body, host='real.oktapreview.com')
    assert body['string'] == '<EntityDescriptor entityID="https://example.com/x"/>'


def test_a_binary_body_is_skipped():
    """A body that is not text is left alone rather than raising."""
    body = {'base64_string': base64.b64encode(b'\x89PNG\r\n\x1a\n\xff\xfe').decode('ascii')}
    before = dict(body)
    sanitize_body(body, host='')
    assert body == before


def test_request_bodies_are_redacted_too():
    """A request body carries whatever the library sent, including a password."""
    interaction = {
        'request': {'body': make_body({'credentials': {'password': {'value': 'hunter2'}}})},
        'response': {'body': make_body({'profile': {'login': 'a@corp.example.org'}})},
    }
    sanitize_interaction(interaction, host='')
    assert read_body(interaction['request']['body'])['credentials']['password'] == REDACTED
    assert read_body(interaction['response']['body'])['profile']['login'].endswith('@example.com')


def test_an_interaction_without_bodies_is_tolerated():
    """A HEAD or 204 interaction has no body to redact."""
    interaction = {'request': {}, 'response': {'body': None}}
    sanitize_interaction(interaction, host='')  # must not raise


def test_host_aliases_include_the_admin_console_host():
    """An app's help link points at the admin host, which is not the org host."""
    assert host_aliases('anorg.oktapreview.com') == [
        'anorg-admin.oktapreview.com',
        'anorg.oktapreview.com',
    ]


def test_host_aliases_are_empty_without_a_host():
    """Replay runs with no host configured, and must not redact on an empty string."""
    assert host_aliases('') == []


def test_host_aliases_of_a_bare_name():
    """A hostname with no domain part has no admin variant to derive."""
    assert host_aliases('localhost') == ['localhost']


def test_the_admin_host_is_redacted_from_a_body():
    """A help link to the admin console is redacted like any other host reference."""
    body = json.dumps({'_links': {'help': {'href': 'https://anorg-admin.oktapreview.com/app/x'}}})
    redacted = redact_text(body, 'anorg.oktapreview.com')
    assert 'anorg-admin' not in redacted
    assert 'example.com/app/x' in redacted
