# Contributing to SecurePacket Analyzer Pro

Thank you for your interest in contributing! This document provides guidelines and information for contributors.

## Code of Conduct

Please read our [Code of Conduct](CODE_OF_CONDUCT.md) before contributing.

## Getting Started

### Prerequisites

- Python 3.12+
- Git
- pip

### Development Setup

```bash
# Fork and clone the repository
git clone https://github.com/your-username/SecurePacket-Analyzer-Pro.git
cd SecurePacket-Analyzer-Pro

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install development dependencies
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install

# Run the test suite
pytest
```

## Development Workflow

1. Create a feature branch from `main`
2. Make your changes
3. Write or update tests
4. Run the full test suite
5. Ensure all linters pass
6. Submit a pull request

### Branch Naming

- `feature/description` — New features
- `fix/description` — Bug fixes
- `docs/description` — Documentation changes
- `refactor/description` — Code refactoring

### Code Style

- Follow PEP 8 (enforced by Ruff)
- Use type hints on all function signatures
- Write docstrings for public APIs
- Use Black for formatting
- Use isort for import sorting

```bash
# Format code
black src/ tests/
isort src/ tests/

# Lint
ruff check src/ tests/

# Type check
mypy src/
```

### Commit Messages

Use conventional commit messages:

```
feat: add packet capture engine
fix: resolve database connection issue
docs: update installation guide
refactor: simplify configuration loading
test: add workspace manager tests
```

## Pull Request Guidelines

- Fill out the PR template completely
- Reference any related issues
- Include screenshots for UI changes
- Update documentation as needed
- Ensure CI passes before requesting review

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_config.py
```

## Reporting Issues

- Use the GitHub issue template
- Include steps to reproduce
- Include environment details
- Include relevant log output

## Accessibility

All UI contributions must meet WCAG 2.2 AA standards. See [docs/accessibility.md](docs/accessibility.md) for guidelines.

## Security

If you find a security vulnerability, please report it privately. See [SECURITY.md](SECURITY.md) for details.
