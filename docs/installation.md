# Installation

## For Users

### Using uv (Preferred)

```bash
uv add oktalib
```

### Using pip (Legacy)

```bash
pip install oktalib
```

## For Developers

If you want to contribute to oktalib or run it from source, follow the development setup.

### Prerequisites

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/) - Modern Python package manager

### Setup Development Environment

1. Fork and clone the repository:
   ```bash
   git clone https://github.com/YOUR_USERNAME/oktalib.git
   cd oktalib
   ```

2. Install dependencies (including dev dependencies):
   ```bash
   uv sync --all-extras --dev
   ```

3. Verify the setup:
   ```bash
   uv run pytest
   ```

### Development Workflow

This project follows the [Paleofuturistic Python](https://github.com/schubergphilis/paleofuturistic_python) development flow.

**Code Quality:**
```bash
# Format code
uv run ruff format

# Lint code
uv run ruff check

# Type check
uv run mypy
```

**Testing:**
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

**Build:**
```bash
# Build package (to validate it works)
uv build
```

**Documentation:**
```bash
# Preview documentation locally
uv run mkdocs serve
```

## Next Steps

- [Usage Guide](usage.md) - Learn how to use oktalib
- [API Reference](api.md) - Explore the full API
- [Contributing](contributing.md) - Contribute to the project
