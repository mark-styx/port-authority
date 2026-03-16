# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial public release
- Port assignment with persistent and ephemeral allocation types
- LAN-exposed service tracking
- HTTP API server with FastAPI
- CLI with offline fallback support
- SQLite database with WAL mode
- Configurable port range (default: 8000-9999)
- Preferred port requests
- Idempotent port assignment

## [0.1.0] - 2026-03-16

### Added
- Core port assignment functionality
- FastAPI server on port 7600
- CLI commands: assign, release, lookup, ls, next, status, serve
- Direct database access for offline mode
- Automatic schema migration
- Port conflict detection
- Project description support

[Unreleased]: https://github.com/yourusername/port-authority/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/yourusername/port-authority/releases/tag/v0.1.0
