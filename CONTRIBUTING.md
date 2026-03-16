# Contributing to Port Authority

Thank you for your interest in contributing to Port Authority! This document provides guidelines and instructions for contributing.

## Development Setup

### Prerequisites

- Python 3.12 or higher
- Git

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/port-authority.git
   cd port-authority
   ```

2. Create a virtual environment and install development dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -e ".[dev]"
   ```

3. Install pre-commit hooks:
   ```bash
   pre-commit install
   ```

## Development Workflow

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=port_authority --cov-report=term-missing

# Run specific test file
pytest tests/test_db.py
```

### Code Quality

This project uses the following tools to maintain code quality:

- **ruff**: Fast Python linter and formatter
- **mypy**: Static type checker
- **pre-commit**: Git hooks for automated checks

Run checks manually:

```bash
# Format code
ruff format

# Lint code
ruff check

# Type check
mypy src

# Run all pre-commit hooks
pre-commit run --all-files
```

### Project Structure

```
port-authority/
├── src/port_authority/
│   ├── __init__.py      # Package initialization
│   ├── cli.py           # CLI commands
│   ├── db.py            # SQLite database layer
│   └── server.py        # FastAPI HTTP server
├── tests/
│   ├── test_db.py       # Database tests
│   └── test_server.py   # API tests
├── pyproject.toml       # Project configuration
├── README.md            # User documentation
└── CONTRIBUTING.md      # This file
```

## Making Changes

### Branch Naming

- Feature: `feature/description-of-feature`
- Bug fix: `fix/description-of-bug`
- Documentation: `docs/description-of-change`

### Commit Messages

Follow these guidelines for commit messages:

- Use the present tense ("Add feature" not "Added feature")
- Use the imperative mood ("Move cursor to..." not "Moves cursor to...")
- Limit the first line to 72 characters or less
- Reference issues and pull requests liberally after the first line

Example:
```
Add preferred port option to CLI

Allow users to request a specific port when assigning. Returns error
if the preferred port is already in use.

Closes #42
```

### Pull Request Process

1. Create a feature branch from `main`
2. Make your changes, following the code style guidelines
3. Add or update tests as needed
4. Ensure all tests pass and coverage remains high
5. Update documentation if needed
6. Submit a pull request

#### Pull Request Checklist

- [ ] Code follows the project's style guidelines
- [ ] Tests pass locally
- [ ] New tests added for new functionality
- [ ] Documentation updated if needed
- [ ] Commit messages follow guidelines
- [ ] PR description clearly describes the change

## Coding Standards

### Python Style

- Follow PEP 8
- Use type hints for all function signatures
- Write docstrings for public functions and classes
- Keep functions focused and under 50 lines when possible
- Use descriptive variable names

### Example

```python
def assign_port(
    conn: sqlite3.Connection,
    project: str,
    allocation_type: str = "persistent",
    lan_exposed: bool = False,
    description: str = "",
    preferred_port: int | None = None,
) -> dict:
    """Assign a port to a project.
    
    Args:
        conn: Database connection
        project: Unique project identifier
        allocation_type: Either 'persistent' or 'ephemeral'
        lan_exposed: Whether the service is exposed on LAN
        description: Optional project description
        preferred_port: Request a specific port number
        
    Returns:
        Dictionary with assignment details
        
    Raises:
        PortConflictError: If preferred port is already assigned
        NoPortAvailableError: If no ports are available
    """
    # Implementation
```

## Reporting Issues

### Bug Reports

When reporting bugs, please include:

1. Python version
2. Operating system
3. Steps to reproduce
4. Expected behavior
5. Actual behavior
6. Error messages or logs

### Feature Requests

For feature requests, please:

1. Describe the feature clearly
2. Explain the use case
3. Provide examples if possible

## Questions?

Feel free to open an issue for questions or discussions about the project.

## License

By contributing to Port Authority, you agree that your contributions will be licensed under the MIT License.
