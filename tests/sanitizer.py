"""Redaction of secrets and personal data from betamax cassettes.

Cassettes are recorded against a real Okta org, so every recorded body may carry
personal data: Okta profiles are extensible, and an org can put anything in them.
That rules out a denylist of known-bad field names, since the next custom
attribute someone adds would sail straight through. Profiles are therefore
handled with an **allowlist** (:data:`PROFILE_KEPT`), and everything else inside
a profile is replaced.

Two rules for anyone writing a recorded test:

- **Assertions must hold for both the live value and its redacted replacement.**
  A test runs against real data while recording and against sanitized data on
  replay, so ``assert user.email`` and ``assert '@' in user.email`` are safe
  while ``assert user.email == 'someone@corp.com'`` is not.
- **Keep identifying values out of request URIs.** betamax matches on method and
  URI, so a URI cannot be rewritten here without making the cassette
  unmatchable. Use a fixture the test creates itself when it needs to address a
  specific user.

"""

import base64
import contextlib
import gzip
import hashlib
import json
from typing import Any

# Profile keys kept verbatim. ``Group`` refuses to build without ``profile.name``,
# and the app-user role fields are features the library exposes; neither names a
# person. ``description`` is deliberately absent: group profiles use it harmlessly,
# but a recorded *user* profile had a person's name in it.
PROFILE_KEPT = frozenset({'name', 'role', 'samlRoles'})

# Keys holding an email-shaped identifier, replaced with a deterministic stand-in
# wherever they appear, so that one value maps to one stand-in and any correspondence
# in the original data survives. Not scoped to profiles: an app user carries the login
# again under ``credentials.userName``. Note this is nothing to do with postal
# addresses — ``streetAddress`` and friends are redacted outright by the allowlist.
EMAIL_KEYS = frozenset({'email', 'login', 'secondEmail', 'userName'})

# Keys replaced with a deterministic label rather than an email, anywhere they appear.
PERSONAL_NAME_KEYS = frozenset(
    {'firstName', 'lastName', 'middleName', 'displayName', 'nickName', 'honorificPrefix', 'honorificSuffix'}
)

# Keys redacted wherever they appear, profile or not, in requests and responses
# alike. Redacted whole: a secret nested under one of these must not survive by
# hiding one level deeper, as ``credentials.password.value`` would. This list only
# needs the keys that appear *outside* a profile; anything unrecognised inside one
# is already replaced by :func:`sanitize_profile`.
SECRET_KEYS = frozenset(
    {
        'client_secret',
        'client_assertion',
        'secret_hash',
        'sharedSecret',
        'password',
        'privateKey',
        'private_key',
    }
)

# Keys holding free-form operator-facing text, redacted wherever they appear. A
# provisioning task's ``errorString`` names the affected person outright ("Automatic
# provisioning of user <name> to app <app> failed: ..."), and such text is unbounded —
# one error observed on a real org echoed back the org's entire password policy. There
# is no safe way to keep a sample, so none is kept. Note this excludes Okta's own
# ``errorSummary``, which is a generic API-level message like "Bad request".
FREE_TEXT_KEYS = frozenset({'errorString', 'pushErrorMessage'})

REDACTED = 'REDACTED'
PSEUDONYM_DOMAIN = 'example.com'
PSEUDONYM_PREFIX = 'user-'


def fingerprint(value: object, length: int = 8) -> str:
    """A short, stable digest of a value, used to build its stand-in.

    Args:
        value: The original value to derive a digest from
        length: The number of hex characters to keep

    Returns:
        str: The truncated hex digest

    """
    return hashlib.sha256(str(value).encode()).hexdigest()[:length]


def pseudonymous_email(value: object) -> object:
    """Replace an email, login or username with a stand-in at example.com.

    The stand-in is derived from the value, so one value always yields one
    stand-in. Already replaced values are returned untouched, which keeps
    sanitizing twice a no-op rather than producing a new stand-in each pass.

    Args:
        value: The original email-shaped identifier

    Returns:
        The stand-in email, or the value unchanged if it is empty, not a string,
        or already a stand-in

    """
    if not isinstance(value, str) or not value:
        return value
    if value.startswith(PSEUDONYM_PREFIX) and value.endswith(f'@{PSEUDONYM_DOMAIN}'):
        return value
    return f'{PSEUDONYM_PREFIX}{fingerprint(value)}@{PSEUDONYM_DOMAIN}'


def pseudonymous_label(key: str, value: object) -> object:
    """Replace a personal name with a deterministic label derived from it.

    Args:
        key: The profile key the value belongs to, used as the label prefix
        value: The original name

    Returns:
        The stand-in label, or the value unchanged if it is empty or already a
        stand-in

    """
    if not isinstance(value, str) or not value:
        return value
    if value.startswith(f'{key}-'):
        return value
    return f'{key}-{fingerprint(value, 6)}'


def sanitize_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Redact a profile object, keeping only what the library needs.

    Keys are preserved even when their values are replaced, so the shape of the
    payload survives and the redaction stays auditable. Nulls and booleans are
    kept as they are, since neither identifies anyone.

    Args:
        profile: The profile object from a recorded body

    Returns:
        dict: The redacted profile

    """
    sanitized: dict[str, Any] = {}
    for key, value in profile.items():
        if key in SECRET_KEYS or key in FREE_TEXT_KEYS:
            sanitized[key] = REDACTED
        elif key in PROFILE_KEPT:
            sanitized[key] = sanitize_payload(value)
        elif key in EMAIL_KEYS:
            sanitized[key] = pseudonymous_email(value)
        elif key in PERSONAL_NAME_KEYS:
            sanitized[key] = pseudonymous_label(key, value)
        elif value is None or isinstance(value, bool):
            sanitized[key] = value
        else:
            sanitized[key] = REDACTED
    return sanitized


def sanitize_payload(payload: Any) -> Any:
    """Redact secrets and personal data from a decoded request or response body.

    Args:
        payload: The parsed JSON body, at any depth

    Returns:
        The redacted payload

    """
    if isinstance(payload, dict):
        sanitized: dict[str, Any] = {}
        for key, value in payload.items():
            if key in SECRET_KEYS or key in FREE_TEXT_KEYS:
                sanitized[key] = REDACTED
            elif key in EMAIL_KEYS:
                sanitized[key] = pseudonymous_email(value)
            elif key in PERSONAL_NAME_KEYS:
                sanitized[key] = pseudonymous_label(key, value)
            elif key == 'profile' and isinstance(value, dict):
                sanitized[key] = sanitize_profile(value)
            else:
                sanitized[key] = sanitize_payload(value)
        return sanitized
    if isinstance(payload, list):
        return [sanitize_payload(item) for item in payload]
    return payload


def host_aliases(host: str) -> list[str]:
    """Every hostname of the recording org that a body can carry.

    An app's ``_links.help`` points at the admin console, which lives on a
    separate ``{org}-admin.{domain}`` host rather than the org host the library
    talks to. Redacting only the configured host leaves that one behind.

    Longest first, so replacing them in order cannot leave a fragment of the
    admin host behind after the org host has been substituted out of it.

    Args:
        host: The bare org hostname, or an empty string when it is unknown

    Returns:
        list: The hostnames to redact, empty when no host was given

    """
    if not host:
        return []
    subdomain, _, domain = host.partition('.')
    if not domain:
        return [host]
    return sorted({host, f'{subdomain}-admin.{domain}'}, key=len, reverse=True)


def redact_text(text: str, host: str) -> str:
    """Redact a decoded body, whether or not it is JSON.

    Non-JSON bodies (the SAML metadata endpoint returns XML) are left structurally
    alone and only have the host replaced.

    Args:
        text: The decoded body
        host: The real Okta host to replace with ``example.com``; an empty string
            skips host replacement

    Returns:
        str: The redacted body

    """
    redacted = text
    with contextlib.suppress(ValueError):
        redacted = json.dumps(sanitize_payload(json.loads(redacted)))
    for name in host_aliases(host):
        redacted = redacted.replace(name, PSEUDONYM_DOMAIN)
    return redacted


def sanitize_body(body: dict[str, Any], host: str) -> None:
    """Redact one recorded body in place, preserving its original encoding.

    betamax's placeholders cannot reach into gzipped bodies, so the body is
    decoded, redacted and re-encoded here. Applies to request and response bodies
    alike: a request body carries whatever the library sent, which for user
    creation includes a password.

    Args:
        body: The ``body`` dict from a cassette interaction's request or response
        host: The real Okta host to replace with ``example.com``; pass an empty
            string when the host is unknown (for example on replay), which skips
            host replacement

    """
    is_base64 = 'base64_string' in body
    raw = base64.b64decode(body['base64_string']) if is_base64 else body.get('string', '').encode()
    is_gzip = raw[:2] == b'\x1f\x8b'  # gzip magic bytes
    try:
        text = gzip.decompress(raw).decode() if is_gzip else raw.decode()
    except (OSError, UnicodeDecodeError):
        return  # binary or corrupt body: not text, so nothing to redact

    redacted = redact_text(text, host)
    if redacted == text:
        return

    if is_base64:
        payload = gzip.compress(redacted.encode(), mtime=0) if is_gzip else redacted.encode()
        body['base64_string'] = base64.b64encode(payload).decode('ascii')
    else:
        body['string'] = redacted


def sanitize_interaction(interaction: dict[str, Any], host: str) -> None:
    """Redact both bodies of one cassette interaction in place.

    Args:
        interaction: One entry of a cassette's ``http_interactions``
        host: The real Okta host to replace with ``example.com``

    """
    for side in ('request', 'response'):
        body = interaction.get(side, {}).get('body')
        if isinstance(body, dict):
            sanitize_body(body, host)
