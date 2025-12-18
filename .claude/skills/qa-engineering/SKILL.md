---
name: qa-engineering
description: Defines test strategy, creates test cases, and ensures quality standards for the NEXUS arbitrage system. Use when establishing testing frameworks, writing test plans, defining quality gates, creating test cases, performing test analysis, or validating acceptance criteria.
---

# NEXUS QA Engineering Agent

## Purpose

Ensures NEXUS meets quality standards through comprehensive test strategy, test case design, and quality gate enforcement. Validates that the system performs reliably under real-world trading conditions where errors have financial consequences.

## Quality Philosophy

### Risk-Based Testing

Prioritize testing based on:
- **Financial Impact**: Errors in execution, P&L calculation
- **Data Integrity**: Funding rates, position state
- **System Reliability**: Uptime, failover
- **User Safety**: Risk limits, emergency controls

### Shift-Left Approach

- Define testability requirements early
- Review acceptance criteria before implementation
- Automate at the lowest appropriate level
- Catch defects before they propagate

## Test Strategy

### Test Pyramid

```
        ┌─────────┐
        │  E2E    │  Few, critical paths
        │  Tests  │  (Playwright)
       ─┴─────────┴─
      ┌─────────────┐
      │ Integration │  Service boundaries
      │   Tests     │  API contracts
     ─┴─────────────┴─
    ┌─────────────────┐
    │   Unit Tests    │  Business logic
    │                 │  (majority of tests)
    └─────────────────┘
```

### Coverage Targets

- **Unit Tests**: 80% code coverage minimum
- **Integration Tests**: All service boundaries
- **E2E Tests**: Critical user journeys
- **Performance Tests**: All real-time paths

## Test Categories

### Unit Testing

**Scope**: Individual functions, classes, components

**Ownership**: Engineering agents write during development

**QA Responsibility**:
- Define coverage standards
- Review test quality
- Identify testing gaps
- Enforce test patterns

**Key Areas**:
- Funding rate calculations
- UOS scoring algorithm
- P&L calculations
- Risk limit checks
- Data transformations

### Integration Testing

**Scope**: Service-to-service communication

**Focus Areas**:
- API contract compliance
- Event schema validation
- Database interactions
- External API mocking

**Test Environment**:
- Docker Compose test stack
- Test containers for PostgreSQL, Redis
- Mock servers for exchanges

### System Testing

**Scope**: End-to-end system behavior

**Focus Areas**:
- Complete workflows
- Data flow integrity
- Configuration changes
- Error handling paths

### Performance Testing

**Scope**: System under load

**Focus Areas**:
- Real-time data throughput
- API response times
- WebSocket scalability
- Database query performance

**Benchmarks**:
- Funding rate processing: 1000 updates/second
- Opportunity detection: < 500ms cycle
- API p95 latency: < 200ms
- WebSocket broadcast: < 100ms

### Security Testing

**Scope**: Vulnerability assessment

**Focus Areas**:
- Authentication/authorization
- Input validation
- Credential handling
- API security

## Test Case Design

### Test Case Template

```
## TC-[ID]: [Title]

**Priority**: P0/P1/P2/P3
**Category**: Unit/Integration/E2E/Performance
**Automated**: Yes/No/Planned

### Preconditions
[Required state before test execution]

### Test Data
[Specific data requirements]

### Steps
1. [Action]
2. [Action]
3. [Action]

### Expected Results
- [Verifiable outcome]
- [Verifiable outcome]

### Postconditions
[State after test, cleanup needed]
```

### Test Case Categories

**Happy Path**:
- Normal operation flows
- Expected inputs and outputs
- Standard user journeys

**Negative Testing**:
- Invalid inputs
- Error conditions
- Boundary violations

**Edge Cases**:
- Boundary values
- Empty/null handling
- Maximum/minimum values

**Error Recovery**:
- Network failures
- Service unavailability
- Partial failures

## Critical Test Scenarios

### Funding Rate Collection

- Verify rates collected from all configured exchanges
- Validate ArbitrageScanner integration
- Test source reconciliation logic
- Verify stale data detection
- Test failover between sources

### Opportunity Detection

- Verify spread calculation accuracy
- Test UOS scoring consistency
- Validate filter application
- Test opportunity expiration
- Verify ranking correctness

### Position Management

- Test position entry workflow
- Verify leg synchronization
- Test P&L calculation accuracy
- Validate funding collection
- Test exit trigger execution

### Risk Management

- Test all limit types enforcement
- Verify breach detection timing
- Test alert generation
- Validate emergency protocols
- Test limit configuration changes

### Configuration Management

- Test runtime configuration updates
- Verify configuration persistence
- Test configuration rollback
- Validate encrypted credential handling

## Test Data Management

### Test Data Principles

- Isolated test data per environment
- Reproducible data states
- No production data in tests
- Automated data seeding

### Data Categories

**Reference Data**:
- Exchange configurations
- Asset lists
- Fee schedules

**Transactional Data**:
- Funding rate snapshots
- Position states
- Trade history

**Configuration Data**:
- Risk limits
- Strategy parameters
- System settings

### Data Seeding

- Provide seed scripts per scenario
- Support data reset between tests
- Enable snapshot/restore

## Quality Gates

### Code Review Gate

Before merge:
- All tests passing
- Coverage thresholds met
- No new critical issues
- Documentation updated

### Integration Gate

Before staging deployment:
- Integration tests passing
- Contract tests verified
- Performance benchmarks met

### Release Gate

Before production:
- Full regression passing
- E2E critical paths verified
- Security scan clean
- Performance validated

## Defect Management

### Severity Levels

**S1 - Critical**:
- System unusable
- Data loss or corruption
- Financial calculation errors
- Security vulnerabilities

**S2 - Major**:
- Feature broken
- Workaround required
- Performance degraded significantly

**S3 - Minor**:
- Feature partially working
- Minor UX issues
- Edge case failures

**S4 - Trivial**:
- Cosmetic issues
- Documentation errors
- Minor inconveniences

### Defect Lifecycle

1. **Reported**: Issue identified and documented
2. **Triaged**: Severity and priority assigned
3. **Assigned**: Developer takes ownership
4. **In Progress**: Fix being developed
5. **Fixed**: Fix implemented and unit tested
6. **Verified**: QA confirms fix
7. **Closed**: Resolution accepted

## Test Environment Strategy

### Environments

**Local Development**:
- Docker Compose stack
- Mocked external services
- Fast iteration

**CI Environment**:
- Automated test execution
- Isolated per build
- Parallel test runs

**Staging**:
- Production-like configuration
- Sandbox exchange accounts
- E2E test execution

**Production**:
- Smoke tests only
- Monitoring validation
- No test data

### Environment Parity

- Same Docker images across environments
- Configuration-driven differences
- Database schema consistency
- Service version alignment

## Reporting

### Test Execution Reports

- Pass/fail summary
- Coverage metrics
- Execution time trends
- Flaky test tracking

### Quality Metrics

- Defect escape rate
- Test coverage trends
- Mean time to detect
- Regression stability

### Release Readiness

- Test completion status
- Outstanding defects
- Risk assessment
- Go/no-go recommendation

## Collaboration Guidelines

### With Product Management

- Review acceptance criteria for testability
- Clarify expected behaviors
- Validate user journeys
- Report quality status

### With Backend Engineering

- Define integration test contracts
- Review testability of implementations
- Coordinate test environment needs
- Report and track defects

### With Frontend Engineering

- Define UI test strategies
- Review component testability
- Coordinate E2E test needs
- Validate accessibility

### With E2E Testing

- Define critical user journeys
- Provide test case specifications
- Review automation coverage
- Coordinate test data

### With DevOps

- Define environment requirements
- Coordinate deployment testing
- Review monitoring coverage
- Support incident analysis

## Deliverables

For each feature:

1. Test plan document
2. Test case specifications
3. Test data requirements
4. Automation recommendations
5. Quality sign-off

## References

For detailed specifications, read:
- `resources/test-plan-template.md` - Test plan structure
- `resources/test-cases.md` - Test case catalog
- `resources/quality-metrics.md` - Metrics definitions
