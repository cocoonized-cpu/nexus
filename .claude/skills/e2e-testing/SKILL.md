---
name: e2e-testing
description: Implements end-to-end test automation using Playwright for the NEXUS arbitrage system. Use when creating automated UI tests, implementing user journey validations, setting up Playwright test infrastructure, debugging test failures, or performing user acceptance testing automation.
---

# NEXUS E2E Testing Agent

## Purpose

Automates end-to-end user journeys using Playwright, ensuring critical trading workflows function correctly from the user's perspective. Validates that the entire system—frontend, backend, database—works together seamlessly.

## Technical Stack

### Core Framework

- **Test Framework**: Playwright Test
- **Language**: TypeScript
- **Assertions**: Playwright expect + custom matchers
- **Reporting**: Playwright HTML Reporter + Allure

### Supporting Tools

- **Visual Testing**: Playwright screenshots + Percy (optional)
- **API Testing**: Playwright API context
- **Accessibility**: @axe-core/playwright

## Project Structure

```
e2e/
├── tests/
│   ├── opportunities/      # Opportunity-related journeys
│   ├── positions/          # Position management journeys
│   ├── risk/              # Risk monitoring journeys
│   ├── configuration/     # Settings and config journeys
│   └── smoke/             # Quick validation tests
├── pages/                  # Page Object Models
│   ├── dashboard.page.ts
│   ├── opportunities.page.ts
│   ├── positions.page.ts
│   ├── risk.page.ts
│   └── settings.page.ts
├── fixtures/               # Test fixtures and setup
│   ├── auth.fixture.ts
│   ├── data.fixture.ts
│   └── websocket.fixture.ts
├── utils/                  # Helper utilities
│   ├── api-client.ts
│   ├── database.ts
│   ├── websocket-mock.ts
│   └── test-data.ts
├── playwright.config.ts
└── global-setup.ts
```

## Page Object Model

### Design Principles

- One page object per logical page/component
- Encapsulate selectors within page objects
- Expose meaningful actions, not raw elements
- Handle waiting and assertions internally

### Page Object Template

```typescript
// Structure only - no implementation details

class OpportunitiesPage {
  // Locators as properties
  // Navigation methods
  // Action methods (filter, sort, select)
  // Assertion methods (verify opportunity displayed)
  // Data extraction methods
}
```

### Selector Strategy

Priority order for selectors:
1. `data-testid` attributes (most stable)
2. Accessible roles and labels
3. Text content (for user-visible elements)
4. CSS selectors (last resort)

Request `data-testid` from frontend-engineering for:
- Interactive elements (buttons, inputs)
- Data containers (tables, cards)
- Dynamic content areas
- Modal/dialog triggers

## Test Categories

### Smoke Tests

**Purpose**: Quick validation that core functionality works

**Scope**:
- Application loads
- Authentication works
- Dashboard displays data
- Navigation functions

**Execution**: Every deployment, < 5 minutes

### Critical Path Tests

**Purpose**: Validate essential user journeys

**Journeys**:
1. View and analyze opportunities
2. Open a new position
3. Monitor active positions
4. Close a position
5. Configure risk limits

**Execution**: Every PR, < 15 minutes

### Regression Tests

**Purpose**: Comprehensive feature coverage

**Scope**:
- All user-facing features
- Error handling paths
- Edge cases
- Cross-browser validation

**Execution**: Nightly, < 60 minutes

### Visual Regression Tests

**Purpose**: Detect unintended UI changes

**Scope**:
- Key page screenshots
- Component states
- Responsive breakpoints

**Execution**: Weekly or on UI changes

## Critical User Journeys

### Journey 1: Opportunity Discovery

**Scenario**: User finds and analyzes arbitrage opportunities

**Steps**:
1. Navigate to opportunities page
2. Apply filters (min spread, exchanges)
3. Sort by UOS score
4. Select an opportunity
5. View detailed analysis
6. Compare with alternatives

**Validations**:
- Data loads within 2 seconds
- Filters apply correctly
- Sorting works accurately
- Details match list data
- Real-time updates reflect

### Journey 2: Position Entry

**Scenario**: User opens a new arbitrage position

**Steps**:
1. Select opportunity
2. Configure position size
3. Review execution preview
4. Confirm execution
5. Verify position appears

**Validations**:
- Preview shows accurate estimates
- Confirmation requires explicit action
- Position appears in active list
- Both legs show correct status
- P&L calculation starts

### Journey 3: Position Management

**Scenario**: User monitors and manages active position

**Steps**:
1. Navigate to positions
2. View position details
3. Check health metrics
4. Adjust exit parameters
5. Monitor funding collection

**Validations**:
- Real-time P&L updates
- Health status accurate
- Configuration saves correctly
- Funding events recorded

### Journey 4: Position Exit

**Scenario**: User closes an active position

**Steps**:
1. Select position to close
2. Review exit preview
3. Confirm closure
4. Verify execution
5. Check final P&L

**Validations**:
- Both legs close properly
- Final P&L calculated correctly
- Position moves to history
- Capital released

### Journey 5: Risk Configuration

**Scenario**: User configures risk limits

**Steps**:
1. Navigate to settings
2. Modify risk limits
3. Save configuration
4. Trigger limit condition
5. Verify enforcement

**Validations**:
- Changes persist after save
- New limits apply immediately
- Breach detected correctly
- Alert generated

## Test Data Management

### Data Strategies

**API Seeding**:
- Create test data via backend APIs
- Faster than UI-based setup
- Consistent state

**Database Seeding**:
- Direct database population
- For complex scenarios
- Reset between tests

**Mock Data**:
- WebSocket message mocking
- External API simulation
- Controlled scenarios

### Test Isolation

- Each test starts with known state
- Tests clean up after themselves
- No inter-test dependencies
- Parallel execution safe

### Fixture Design

**Authentication Fixture**:
- Handles login/session management
- Reuses auth state where possible
- Supports multiple user types

**Data Fixture**:
- Seeds required test data
- Provides cleanup
- Supports scenario variations

**WebSocket Fixture**:
- Mocks real-time data
- Controls timing and content
- Supports connection scenarios

## Real-Time Testing

### WebSocket Testing Strategy

**Challenges**:
- Asynchronous updates
- Timing dependencies
- Connection state

**Approaches**:

1. **Wait for Updates**:
   - Wait for specific data to appear
   - Use polling with timeout
   - Assert on final state

2. **Mock WebSocket**:
   - Inject controlled messages
   - Test specific scenarios
   - Deterministic timing

3. **Event Verification**:
   - Subscribe to events
   - Verify event sequence
   - Check data accuracy

### Timing Considerations

- Allow for network latency
- Use intelligent waits (not fixed delays)
- Set appropriate timeouts
- Handle loading states

## Cross-Browser Testing

### Browser Matrix

**Primary** (every run):
- Chromium (latest)

**Secondary** (nightly):
- Firefox (latest)
- WebKit (latest)

**Optional** (periodic):
- Mobile Chrome
- Mobile Safari

### Browser-Specific Handling

- Use conditional logic sparingly
- Document known differences
- Report browser-specific bugs

## CI/CD Integration

### Pipeline Stages

```
PR Pipeline:
  ├── Smoke Tests (required, blocking)
  └── Critical Path Tests (required, blocking)

Merge Pipeline:
  ├── Smoke Tests
  ├── Critical Path Tests
  └── Regression Tests (non-blocking)

Nightly Pipeline:
  ├── Full Regression Suite
  ├── Cross-Browser Tests
  └── Visual Regression Tests
```

### Parallel Execution

- Shard tests across workers
- Balance test distribution
- Share authentication state
- Isolate test data

### Artifact Collection

On failure:
- Screenshots
- Videos
- Trace files
- Console logs
- Network logs

## Reporting

### Test Reports

**Playwright HTML Report**:
- Built-in detailed reporting
- Screenshots and traces
- Failure analysis

**Allure Report** (optional):
- Historical trends
- Categorization
- Team dashboards

### Metrics to Track

- Pass rate trends
- Execution time trends
- Flaky test rate
- Coverage by journey

## Debugging Failed Tests

### Investigation Steps

1. Review error message and stack trace
2. Examine screenshot at failure
3. Watch test video recording
4. Analyze trace file
5. Check application logs
6. Reproduce locally

### Common Issues

**Timing Issues**:
- Add explicit waits
- Use `waitFor` patterns
- Avoid fixed delays

**Selector Issues**:
- Verify element exists
- Check for dynamic content
- Use more stable selectors

**Data Issues**:
- Verify test data setup
- Check data dependencies
- Ensure isolation

**Environment Issues**:
- Compare local vs CI
- Check service availability
- Verify configuration

## Accessibility Testing

### Automated Checks

- Run axe-core on key pages
- Check WCAG 2.1 AA compliance
- Report violations as defects

### Manual Verification

- Keyboard navigation
- Screen reader compatibility
- Focus management

## User Acceptance Testing Support

### UAT Automation

- Automate repeatable UAT scenarios
- Provide test execution for stakeholders
- Generate acceptance evidence

### UAT Reporting

- Clear pass/fail status
- Screenshots of key states
- Journey completion evidence

## Collaboration Guidelines

### With Frontend Engineering

- Request data-testid attributes
- Report UI inconsistencies
- Coordinate on component changes
- Share selector patterns

### With QA Engineering

- Align on test case coverage
- Coordinate manual vs automated
- Share test data strategies
- Report quality findings

### With Backend Engineering

- Request API test hooks
- Coordinate test data seeding
- Report integration issues

### With DevOps

- Define CI requirements
- Configure test environments
- Optimize pipeline execution
- Manage test artifacts

## Deliverables

For each user journey:

1. Automated test implementation
2. Page objects as needed
3. Test data fixtures
4. Documentation of coverage
5. Maintenance notes

## References

For detailed specifications, read:
- `resources/page-objects.md` - Page object catalog
- `resources/test-data.md` - Test data specifications
- `resources/journey-specs.md` - Detailed journey definitions
