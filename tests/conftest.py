"""Integrations reusable test fixtures."""

import json
import os
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from types import TracebackType

import pytest
from _pytest.fixtures import SubRequest
from betamax import Betamax
from betamax.cassette import Cassette, Interaction
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
]


def configure_betamax(integration: str, token: str, base_url: str | None = None) -> None:
    """Configures betamax for a given integration.

    Args:
        integration: The integration name.
        token: The token to authenticate with.
        base_url: The base URL to redact if provided.

    Returns:
        None

    """
    with Betamax.configure() as config:
        local_path = f'tests/integrations/cassettes/{integration}'
        # make directory if it does not exist.
        Path(local_path).mkdir(parents=True, exist_ok=True)
        config.cassette_library_dir = local_path
        config.default_cassette_options['record_mode'] = 'once'

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
        >>> extract_pytest_path('tests/integrations/okta/test_test.py::test_example_api_call')
        ("test_test", "test_example_api_call")
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

        def __call__(self) -> Betamax:
            """Allow the context manager to be called directly."""
            return self.__enter__()

        def __enter__(self) -> Betamax:
            """Enter the cassette context."""
            return ctx.__enter__()

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_val: BaseException | None,
            exc_tb: TracebackType | None,
        ) -> bool | None:
            """Exit the cassette context and clean up empty cassettes."""
            result = ctx.__exit__(exc_type, exc_val, exc_tb)
            # cleanup if file exists but has no recorded interactions
            cassette = Path(cassette_path)
            if cassette.exists():
                with cassette.open(encoding='utf-8') as f:
                    data = json.load(f)
                if not data.get('http_interactions'):
                    cassette.unlink()
            return result

    return CassetteCtx()


@pytest.fixture(scope='session')
def okta_service() -> Okta:
    """Return a library instance with an authenticated session."""
    host = os.environ.get('OKTA_HOST', 'https://example.com')
    token = os.environ.get('OKTA_API_KEY', 'fake_api_key')
    if token == 'fake_api_key':

        def _get_authenticated_session(
            self,
        ) -> Session:  # noqa: ARG001
            # pylint: disable='unused-argument'
            """Create an authenticated session without actual authentication."""
            session = Session()
            return session

        Okta._setup_session = _get_authenticated_session
    configure_betamax(integration='okta', token=token, base_url=host)
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
