# Contributing

Thank you for your interest in contributing to oktalib!

## Development Setup

See the [Installation guide](installation.md#for-developers) for setting up your development environment.

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

# Type check
uv run mypy

# Run tests
uv run python -m unittest
```

All checks must pass for the pull request to be accepted.

### Running Tests

```bash
# Run all tests
uv run python -m unittest

# Run specific test file
uv run python -m unittest tests.test_oktalib

# Run specific test
uv run python -m unittest tests.test_oktalib.TestSmoke.test_sanity
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

- Follow PEP 8 style guidelines (enforced by ruff)
- Use type hints for all function signatures (checked by mypy)
- Write clear, descriptive docstrings for all public APIs
- Keep functions focused and avoid over-engineering

## Pull Request Process

1. Ensure all quality checks pass locally
2. Update documentation if adding new features
3. Add tests for new functionality
4. Keep pull requests focused on a single feature or fix
5. Write clear commit messages describing your changes

## Questions?

If you have questions about contributing, please open an issue on GitHub.

## Credits

#### Development Lead

* Costas Tyfoxylos <ctyfoxylos@schubergphilis.com>

#### Contributors

* Yorick Hoorneman <yhoorneman@schubergphilis.com>
