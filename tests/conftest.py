"""Reusable test fixtures for oktalib testing."""

import base64
import contextlib
import gzip
import json
import os
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from types import TracebackType
from urllib.parse import urlparse

import pytest
from _pytest.fixtures import SubRequest
from betamax import Betamax
from betamax.cassette import Cassette, Interaction
from betamax.serializers import JSONSerializer
from requests import Session

from oktalib import Okta

REQUEST_HEADERS_TO_REMOVE = [
    'User-Agent',
    'Authorization',
    'Connection',
    'Accept',
    'Accept-Encoding',
    'Cookie',
]
RESPONSE_HEADERS_TO_REMOVE = [
    'Date',
    'Server',
    'Set-Cookie',
    'Cache-Control',
    'Strict-Transport-Security',
    'Content-Security-Policy',
    'X-Content-Type-Options',
    'X-Frame-Options',
    'Access-Control-Allow-Origin',
    'Access-Control-Allow-Headers',
    'Access-Control-Allow-Methods',
    'Access-Control-Max-Age',
    'X-Okta-Request-Id',
    'X-Rate-Limit-Limit',
    'X-Rate-Limit-Remaining',
    'X-Rate-Limit-Reset',
    'Content-Length',
]

CASSETTE_DIR = Path(__file__).parent / 'cassettes'
# Key under which the session start time is stashed for the end-of-session sanitizer.
_SESSION_START = pytest.StashKey[float]()


def _redact_shared_secrets(obj: object) -> object:
    """Return a copy of ``obj`` with every ``sharedSecret`` value replaced.

    The marker stays valid base32 so pyotp can still parse it on replay (betamax
    matches on request URL/method, not body, so the passcode value is ignored).
    """
    if isinstance(obj, dict):
        return {
            key: 'REDACTED' if key == 'sharedSecret' else _redact_shared_secrets(value)
            for key, value in obj.items()
        }
    if isinstance(obj, list):
        return [_redact_shared_secrets(item) for item in obj]
    return obj


def sanitize_response_body(body: dict, host: str) -> None:
    """Redact the TOTP ``sharedSecret`` and the real Okta host from a body, in place.

    betamax's placeholders can't reach into gzipped response bodies, so we decode,
    redact, and re-encode here, preserving the original encoding so replay works.

    Args:
        body: The ``response['body']`` dict from a betamax cassette interaction.
        host: The real Okta host to replace with ``example.com`` (e.g.
            ``schubergphilis.oktapreview.com``); pass an empty string when the
            host is unknown (e.g. on replay), which skips host redaction.

    """
    is_base64 = 'base64_string' in body
    raw = base64.b64decode(body['base64_string']) if is_base64 else body.get('string', '').encode()
    is_gzip = raw[:2] == b'\x1f\x8b'  # gzip magic bytes
    try:
        text = gzip.decompress(raw).decode() if is_gzip else raw.decode()
    except (OSError, UnicodeDecodeError):
        return  # binary or corrupt body: not text, so nothing to redact

    redacted = text
    if 'sharedSecret' in redacted:
        with contextlib.suppress(ValueError):
            redacted = json.dumps(_redact_shared_secrets(json.loads(redacted)))
    if host:
        redacted = redacted.replace(host, 'example.com')
    if redacted == text:
        return

    if is_base64:
        payload = gzip.compress(redacted.encode(), mtime=0) if is_gzip else redacted.encode()
        body['base64_string'] = base64.b64encode(payload).decode('ascii')
    else:
        body['string'] = redacted


def _normalize_host(raw: str) -> str:
    """Add an https scheme (if missing) and strip a trailing slash.

    An empty string is returned unchanged, so callers can distinguish
    "no host configured".
    """
    if raw and not raw.startswith(('http://', 'https://')):
        raw = f'https://{raw}'
    return raw.rstrip('/')


def _okta_base_url() -> str:
    """Full base URL for the Okta client, defaulting to the placeholder host."""
    return _normalize_host(os.environ.get('OKTA_HOST', 'https://example.com'))


def _okta_hostname() -> str:
    """Bare host to redact from cassettes (e.g. 'schubergphilis.oktapreview.com'), or ''."""
    return urlparse(_normalize_host(os.environ.get('OKTA_HOST', ''))).hostname or ''


def configure_betamax(token: str, base_url: str | None = None) -> None:
    """Configures betamax for oktalib testing.

    Args:
        token: The Okta API token to authenticate with.
        base_url: The base URL to redact if provided.

    Returns:
        None

    """

    class PrettyJSONSerializer(JSONSerializer):
        """Custom JSON serializer that pretty-prints cassettes for readability."""

        name = 'prettyjson'

        def serialize(self, cassette_data: dict) -> str:
            """Serialize cassette data with indentation for human readability."""
            return json.dumps(cassette_data, sort_keys=True, indent=2, ensure_ascii=False)

    Betamax.register_serializer(PrettyJSONSerializer)

    with Betamax.configure() as config:
        cassette_dir = 'tests/cassettes'
        # make directory if it does not exist.
        Path(cassette_dir).mkdir(parents=True, exist_ok=True)
        config.cassette_library_dir = cassette_dir
        config.default_cassette_options['record_mode'] = 'once'
        config.default_cassette_options['serialize_with'] = 'prettyjson'

        # Redact token
        config.define_cassette_placeholder('<AUTH_TOKEN>', token)
        if base_url:
            config.define_cassette_placeholder('https://example.com', base_url)

        # Strip both request and response headers in one callback
        def strip_sensitive_headers(
            interaction: Interaction,
            cassette: Cassette,  # noqa: ARG001
        ) -> None:
            # pylint: disable='unused-argument'
            # Create lowercase sets for case-insensitive comparison
            req_headers_lower = {h.lower() for h in REQUEST_HEADERS_TO_REMOVE}
            resp_headers_lower = {h.lower() for h in RESPONSE_HEADERS_TO_REMOVE}

            # request headers - remove case-insensitively
            req_headers = interaction.data['request']['headers']
            headers_to_remove = [key for key in req_headers if key.lower() in req_headers_lower]
            for key in headers_to_remove:
                req_headers.pop(key)

            # response headers - remove case-insensitively
            resp_headers = interaction.data['response']['headers']
            headers_to_remove = [key for key in resp_headers if key.lower() in resp_headers_lower]
            for key in headers_to_remove:
                resp_headers.pop(key)

        config.before_record(callback=strip_sensitive_headers)


def extract_pytest_path(pytest_path: str) -> tuple[str, str]:
    """Extracts the filename (without .py) and test function name from a pytest node id.

    Example:
        >>> extract_pytest_path('tests/test_oktalib.py::test_example_api_call')
        ("test_oktalib", "test_example_api_call")
    """
    if '::' in pytest_path:
        file_path, test_name = pytest_path.split('::', 1)
    else:
        file_path, test_name = pytest_path, ''

    filename = Path(file_path).stem
    return filename, test_name


def get_cassette(request: SubRequest, recorder: Betamax) -> Callable[[], AbstractContextManager]:
    """Provide a context manager for using cassettes.

    Cassette name is derived from the test node id automatically.
    Removes cassette file if no interactions were recorded.
    """
    # nodeid looks like "tests/test_api.py::test_method[param]"
    filename, test_name = extract_pytest_path(request.node.nodeid)
    cassette_name = f'{filename}_{test_name}'
    cassette_path = str(Path(recorder.config.cassette_library_dir, f'{cassette_name}.json'))
    ctx = recorder.use_cassette(cassette_name)

    class CassetteCtx:
        """A cassette context manager."""

        def __call__(self) -> 'CassetteCtx':
            """Allow the fixture to be used as ``with okta_cassette():``.

            Returns self so the ``with`` statement uses this wrapper's
            __enter__/__exit__ (which scrubs secrets on exit), not betamax's.
            """
            return self

        def __enter__(self) -> Betamax:
            """Enter the cassette context."""
            return ctx.__enter__()

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_val: BaseException | None,
            exc_tb: TracebackType | None,
        ) -> bool | None:
            """Exit the cassette context and clean up empty cassettes.

            Secret/host sanitization is handled once per session by
            ``pytest_sessionfinish`` so it covers every cassette regardless of
            how it was recorded, not only those created through this fixture.
            """
            result = ctx.__exit__(exc_type, exc_val, exc_tb)
            cassette = Path(cassette_path)
            # remove the file if betamax recorded no interactions
            if cassette.exists():
                data = json.loads(cassette.read_text(encoding='utf-8'))
                if not data.get('http_interactions'):
                    cassette.unlink()
            return result

    return CassetteCtx()


@pytest.fixture(scope='session')
def okta_service() -> Okta:
    """Return a library instance with an authenticated session."""
    host = _okta_base_url()
    token = os.environ.get('OKTA_API_KEY', 'fake_api_key')
    if token == 'fake_api_key':

        def _get_authenticated_session(
            self,
        ) -> Session:  # noqa: ARG001
            # pylint: disable='unused-argument'
            """Create an authenticated session without actual authentication."""
            return Session()

        Okta._setup_session = _get_authenticated_session
    configure_betamax(token=token, base_url=host)
    return Okta(host=host, token=token)


@pytest.fixture(scope='session')
def okta_recorder(okta_service: Okta) -> Betamax:  # pylint: disable=redefined-outer-name
    """Attach Betamax recorder to the okta library's session."""
    return Betamax(okta_service.session)


@pytest.fixture()
def okta_cassette(
    okta_recorder: Betamax,  # pylint: disable=redefined-outer-name
    request: SubRequest,
) -> Callable[[], AbstractContextManager]:
    """Create a cassette recorder for okta."""
    return get_cassette(request=request, recorder=okta_recorder)


def _sanitize_cassette_file(path: Path, host: str) -> None:
    """Redact the TOTP shared secret and real host from one cassette file, in place."""
    data = json.loads(path.read_text(encoding='utf-8'))
    original = json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False)
    for interaction in data.get('http_interactions', []):
        sanitize_response_body(interaction['response']['body'], host)
    sanitized = json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False)
    if sanitized != original:
        path.write_text(sanitized, encoding='utf-8')


def pytest_sessionstart(session: pytest.Session) -> None:
    """Record when the session started so we only sanitize cassettes written during it."""
    session.stash[_SESSION_START] = time.time()


def pytest_sessionfinish(session: pytest.Session) -> None:
    """Sanitize every cassette recorded or updated during this session.

    Runs once after all tests and fixture teardowns, so it covers cassettes made
    through any path (okta_cassette, raw betamax, module-scoped fixtures) without
    interfering with the live recording flow. Redaction is a no-op on unchanged
    files, so this never rewrites already-clean cassettes.
    """
    started = session.stash.get(_SESSION_START, 0.0)
    host = _okta_hostname()
    for path in CASSETTE_DIR.glob('*.json'):
        if path.stat().st_mtime >= started:
            _sanitize_cassette_file(path, host)
