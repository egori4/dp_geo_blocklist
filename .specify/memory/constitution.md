<!--
Sync Impact Report:
- Version change: none → 1.0.0 (Initial constitution)
- Modified principles: N/A (new constitution)
- Added sections: All core sections established
- Removed sections: N/A
- Templates requiring updates: ⚠ pending (plan-template.md, spec-template.md, tasks-template.md)
- Follow-up TODOs: Review and align dependent templates with new principles
-->

# Geo-IP Custom Block Constitution

## Core Principles

### I. Code Quality & Architecture
Python 3.11+ with comprehensive type hints throughout the codebase. Strict adherence to PEP 8 style guidelines with automated enforcement. Modular design following single-responsibility principle - each module has one clear purpose. Comprehensive error handling using specific exception types rather than generic exceptions. Minimize external dependencies beyond stdlib (exceptions: requests for HTTP operations). Prefer composition over inheritance to maintain flexibility and testability.

### II. Security & Reliability
All API credentials MUST be provided via environment variables - hardcoded credentials are strictly forbidden. Validate all external inputs including API responses, CSV data, and configuration files. All operations MUST be idempotent - safe to run multiple times without adverse effects. Implement graceful degradation for non-critical failures while maintaining core functionality. Ensure atomic state updates following all-or-nothing principles for data integrity.

### III. Logging & Observability (NON-NEGOTIABLE)
Structured logging with mandatory fields: timestamp, level, component, message. Log levels strictly enforced: DEBUG for development details, INFO for operational events, WARNING for recoverable issues, ERROR for failures requiring attention. Syslog integration required for centralized monitoring in production environments. Maintain comprehensive audit trail of all IP operations (add/remove) with timestamps for security compliance. Log file rotation handled externally by host system.

### IV. Data Management
State persistence in JSON format for human readability and debugging. History logs in JSONL (newline-delimited JSON) format for efficient append operations and streaming processing. CSV processing MUST use memory-efficient streaming for large datasets. File downloads cached with MD5 validation to ensure data integrity. Delta-based synchronization - transmit only changes, never full lists, to minimize bandwidth and API usage.

### V. Container & Deployment
Stateless container design with all persistent state in mounted volumes. Single responsibility execution model: fetch data, process updates, execute changes, then exit cleanly. No internal scheduling - triggered externally via cron or orchestration systems. Installation via validated bash script with comprehensive error checking. Docker best practices: non-root user execution, minimal base images, explicit volume declarations.

### VI. Testing Standards
Unit tests required for all core logic including CSV parsing, delta calculation, and network formatting. Integration tests with mocked API responses to validate external service interactions. Configuration validation before any execution to prevent runtime failures. Dry-run mode implementation for safe testing without actual API calls or system modifications.

## Security Requirements

All security implementations follow defense-in-depth principles. Input validation occurs at every boundary with explicit allow-lists where possible. API rate limiting respected with exponential backoff for resilience. File operations use secure temporary directories with proper cleanup. Network operations validate SSL certificates and use timeout configurations to prevent hanging operations.

## Performance Standards

Memory usage optimization for processing large IP lists without exceeding reasonable container limits. Network operations designed for reliability over speed with appropriate timeout values. File I/O operations use buffered reads/writes for efficiency. CPU usage remains bounded through streaming approaches rather than loading entire datasets into memory.

## Governance

This constitution supersedes all other development practices and guidelines. All code reviews MUST verify compliance with these principles before approval. Complexity in design or implementation requires explicit justification and documentation. Amendments to this constitution require version increment, documentation of changes, and migration plan for existing code. Any deviation from these principles requires documented exception approval with mitigation strategies.

**Version**: 1.0.0 | **Ratified**: 2025-10-15 | **Last Amended**: 2025-10-15
