# geo-ip-custom-block Development Guidelines

Auto-generated from all feature plans. Last updated: 2025-10-15

## Active Technologies
- Python 3.11+ + requests, Docker (001-geolocation-ip-blocker)

## Project Structure
```
src/
├── models/      # Data structures (GeoLocation, NetworkRange, AppState)
├── services/    # Business logic (API clients, CSV processing, state management)
├── cli/         # Entry point and workflow orchestration
└── lib/         # Shared utilities (logging, validation, exceptions)

tests/
├── contract/    # API contract tests
├── integration/ # End-to-end workflow tests
└── unit/        # Component unit tests
```

## Commands
cd src; pytest; flake8 src/; black src/; mypy src/

## Code Style
Python 3.11+: Follow PEP 8 with comprehensive type hints, modular design, composition over inheritance

## Recent Changes
- 001-geolocation-ip-blocker: Added Python 3.11+ + requests, Docker containerized GeoIP processing system

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
