# Contributing

Thank you for your interest in contributing to oktalib!

## Quick Start

1. **Setup**: [Install development dependencies](installation.md#for-developers) with `uv sync --all-extras --dev`
2. **Make changes**: Create a branch, implement your feature or fix
3. **Test**: Run `uv run pytest` and ensure all tests pass
4. **Quality checks**: Run `uv run ruff format`, `uv run ruff check`, `uv run pylint src/`, and `uv run mypy`
5. **Submit**: Push to your fork and open a pull request

## Development Setup

See the [Installation guide](installation.md#for-developers) for detailed setup instructions.

## Development Workflow

This project follows the [Paleofuturistic Python](https://github.com/schubergphilis/paleofuturistic_python) development flow.

### Making Changes

1. Fork and clone the repository
2. Create a new branch for your feature or bugfix
3. Make your changes
4. Run the quality checks (see below)
5. Commit your changes
6. Push to your fork
7. Open a pull request

### Code Quality

Before submitting a pull request, ensure all quality checks pass:

```bash
# Format code
uv run ruff format

# Lint code
uv run ruff check

# Additional linting with pylint
uv run pylint src/

# Type check
uv run mypy

# Run tests
uv run pytest
```

All checks must pass for the pull request to be accepted.

### Writing Tests

To enable fast, reusable tests that don't require a network connection, this project uses [Betamax](https://betamax.readthedocs.io/). Betamax captures HTTP interactions and replays them in subsequent test runs, eliminating the need for live API calls.

**Basic Test Structure:**

```python
def test_some_api_call(okta_cassette, okta_service):
    with okta_cassette():
        # Make HTTP calls with okta_service
        # Betamax will record or replay the HTTP interactions
        result = okta_service.get_user_by_login('test@example.com')
        assert result.email == 'test@example.com'
```

**Fixtures:**
- `okta_cassette`: Manages Betamax recording/replay. Wraps your test code with the context manager to capture HTTP interactions.
- `okta_service`: Provides the Okta client instance configured for testing.

For most tests, you'll need both fixtures. The cassette fixture records/replays HTTP traffic, while the service fixture provides the actual client to make API calls.

**Recording against a real org:**

Replaying needs nothing configured — with no credentials the suite runs entirely off the cassettes in `tests/cassettes`, which is how CI runs it. Recording a new one needs a real org, configured through the environment:

| Variable | Needed for | Notes |
| --- | --- | --- |
| `OKTA_HOST` | everything | Include the scheme, e.g. `https://your-org.oktapreview.com`. The library does not normalize it. |
| `OKTA_API_KEY` | recording as an API token | Absent, the suite replaces the session with one that does not authenticate, so recording is skipped rather than failing. |
| `OKTA_CLIENT_ID` | recording as a service app | The client id of an API Services app. |
| `OKTA_PRIVATE_KEY` | recording as a service app | A JWK, the same as json, or a PEM. Never commit it. |
| `OKTA_KEY_ID` | recording as a service app | The id Okta assigned the registered public key. Required with a PEM, which carries none. |
| `OKTA_SCOPES` | recording as a service app | Space separated. Read-only scopes are enough to record with. |

Recorded interactions are scrubbed on the way out by `tests/sanitizer.py` and the header lists in `tests/conftest.py`: tokens, client assertions, DPoP proofs and nonces are replaced, and personal data in bodies is pseudonymised. Read a new cassette before committing it anyway — the scrubbing is a safety net, not a substitute for looking.


### Running Tests

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_oktalib.py

# Run specific test
uv run pytest tests/test_oktalib.py::test_sanity

# Run tests with verbose output
uv run pytest -v
```

### Documentation

Documentation is built with MkDocs and mkdocstrings:

```bash
# Preview documentation locally
uv run mkdocs serve
```

The documentation is automatically generated from docstrings in the source code. When adding new public APIs, ensure they have proper docstrings following the numpy style.

### Building

Validate that the package builds correctly:

```bash
uv build
```

## Code Style

- Follow PEP 8 style guidelines (enforced by ruff and pylint)
- Use type hints for all function signatures (checked by mypy)
- Write clear, descriptive docstrings for all public APIs (numpy style)
- Keep functions focused and avoid over-engineering

All code must pass ruff, pylint, and mypy checks before being merged.

## Pull Request Process

Before submitting your pull request:

1. **Quality checks**: Ensure all checks pass locally (ruff, pylint, mypy, pytest)
2. **Documentation**: Update docs if adding new features or changing existing behavior
3. **Tests**: Add tests for new functionality to maintain code coverage
4. **Scope**: Keep pull requests focused on a single feature or fix
5. **Commit messages**: Write clear, descriptive commit messages

Once submitted, maintainers will review your pull request. Please be responsive to feedback and be prepared to make changes if requested.

## Questions?

If you have questions about contributing, please open an issue on GitHub.

## Credits

#### Development Lead

* Costas Tyfoxylos <ctyfoxylos@schubergphilis.com>

#### Contributors

* Yorick Hoorneman <yhoorneman@schubergphilis.com>
