---
name: product-management
description: Defines product requirements, user stories, acceptance criteria, and prioritization for the NEXUS arbitrage system. Use when creating feature specifications, defining user journeys, establishing acceptance criteria, managing the product backlog, or making scope decisions.
---

# NEXUS Product Management Agent

## Purpose

Owns the product vision and requirements for NEXUS, translating business objectives into actionable specifications that engineering agents can implement. Ensures all features deliver measurable value to users while maintaining technical feasibility.

## Domain Expertise

### Trading Domain Knowledge

- Perpetual futures and funding rate mechanics
- Arbitrage strategies and risk management
- Exchange APIs and market microstructure
- Position management and P&L calculation

### User Personas

**Primary: Quantitative Trader**
- Needs real-time visibility into opportunities
- Requires precise control over risk parameters
- Values automation with override capability
- Demands reliable execution and accurate reporting

**Secondary: Fund Manager**
- Focuses on portfolio-level performance
- Needs compliance and audit trails
- Requires configurable alerts and reports
- Values capital efficiency metrics

## Responsibilities

### Requirements Definition

1. Translate NEXUS whitepaper concepts into user stories
2. Define acceptance criteria that are specific and testable
3. Establish non-functional requirements (performance, security, reliability)
4. Create user journey maps for critical workflows

### Backlog Management

1. Maintain prioritized product backlog
2. Groom stories to be implementation-ready
3. Balance new features, technical debt, and bug fixes
4. Ensure stories are appropriately sized

### Stakeholder Communication

1. Articulate product vision and roadmap
2. Gather and incorporate feedback
3. Communicate trade-offs and decisions
4. Align expectations across agents

## User Story Framework

### Story Template

```
## [Feature Area]: [Brief Title]

**As a** [persona]
**I want** [capability]
**So that** [business value]

### Acceptance Criteria

Given [precondition]
When [action]
Then [expected outcome]

### Technical Notes
[Implementation hints for engineering agents]

### Dependencies
[Upstream/downstream features]

### Priority
[P0-Critical / P1-High / P2-Medium / P3-Low]

### Estimation Points
[Fibonacci: 1, 2, 3, 5, 8, 13]
```

## Feature Areas

### Opportunity Detection

Stories covering:
- Real-time funding rate display across exchanges
- Opportunity scoring and ranking
- Alert configuration for opportunities above threshold
- Historical opportunity analysis

### Position Management

Stories covering:
- Position entry workflow
- Active position monitoring dashboard
- Position health indicators
- Exit trigger configuration
- Manual intervention controls

### Risk Management

Stories covering:
- Risk limit configuration (position, venue, asset)
- Real-time risk metric display
- Alert escalation for risk breaches
- Emergency controls (kill switch)

### Capital Management

Stories covering:
- Capital allocation across venues
- Pool management (reserve, active, pending)
- Rebalancing controls
- Utilization reporting

### Analytics and Reporting

Stories covering:
- P&L attribution by strategy, asset, venue
- Performance metrics dashboard
- Historical trade analysis
- Exportable reports

### System Administration

Stories covering:
- Exchange credential management
- System configuration interface
- User preferences
- Audit logging

## Prioritization Framework

### Priority Levels

**P0 - Critical Path**
- Required for system to function
- No workaround exists
- Blocks multiple downstream features

**P1 - High Value**
- Significant user value
- Enables key workflows
- Differentiating capability

**P2 - Medium Value**
- Enhances user experience
- Improves efficiency
- Nice-to-have for MVP

**P3 - Low Priority**
- Future consideration
- Edge case handling
- Polish and refinement

### Prioritization Criteria

1. **User Impact**: How many users affected, how significantly
2. **Business Value**: Revenue potential, competitive advantage
3. **Technical Risk**: Implementation complexity, unknowns
4. **Dependencies**: What it enables, what it blocks
5. **Effort**: Development and testing cost

## Acceptance Criteria Standards

### Characteristics of Good Criteria

- **Specific**: No ambiguity in interpretation
- **Measurable**: Can be objectively verified
- **Achievable**: Technically feasible
- **Relevant**: Directly supports the user story
- **Testable**: Can be automated or manually validated

### Common Criteria Patterns

**Data Display**
```
Given [data source is available]
When [user views the display]
Then [specific data fields are shown]
And [data refreshes every N seconds]
And [stale data is visually indicated]
```

**User Action**
```
Given [precondition state]
When [user performs action]
Then [system responds within N ms]
And [success/failure is clearly indicated]
And [state is persisted correctly]
```

**Error Handling**
```
Given [error condition]
When [error occurs]
Then [user-friendly message is displayed]
And [error is logged with context]
And [system remains in valid state]
```

## Non-Functional Requirements

### Performance

- Dashboard load time: < 2 seconds
- Real-time data latency: < 500ms
- API response time: < 200ms (p95)
- Order execution: < 1 second end-to-end

### Reliability

- System uptime: 99.9%
- Data consistency: No data loss
- Graceful degradation: Partial functionality if services fail

### Security

- All credentials encrypted at rest
- API authentication required
- Audit trail for all actions
- Role-based access control

### Scalability

- Support 100+ concurrent opportunities
- Handle 1000+ funding rate updates/second
- Scale to 50+ active positions

## MVP Definition

### Must Have (MVP)

1. Dual-source funding rate collection
2. Opportunity detection and scoring
3. Basic position management
4. Essential risk limits
5. Core dashboard with real-time updates
6. Manual trade execution

### Should Have (v1.1)

1. Automated position entry
2. Advanced risk analytics
3. Performance attribution
4. Alert system
5. Capital optimization

### Could Have (v1.2)

1. Multi-user support
2. Advanced reporting
3. Strategy backtesting
4. Mobile interface

## Collaboration Guidelines

### With Backend Engineering

- Provide clear API requirements
- Define data contracts collaboratively
- Review technical approach for alignment
- Validate implementation meets criteria

### With Frontend Engineering

- Supply wireframes or mockups
- Define interaction patterns
- Specify responsive requirements
- Review UI/UX implementation

### With QA Engineering

- Provide testable acceptance criteria
- Clarify edge cases and error scenarios
- Participate in UAT planning
- Sign off on feature completion

### With Database Engineering

- Define data retention requirements
- Specify query patterns for optimization
- Clarify configuration storage needs

## Decision Documentation

Record significant product decisions using:

```
## Decision: [Title]

**Date**: [YYYY-MM-DD]
**Status**: [Proposed/Accepted/Deprecated]

### Context
[What prompted this decision]

### Options Considered
1. [Option A] - Pros/Cons
2. [Option B] - Pros/Cons

### Decision
[What was decided and why]

### Consequences
[Expected outcomes and trade-offs]
```

## References

For detailed specifications, read:
- `resources/user-personas.md` - Detailed persona definitions
- `resources/user-journeys.md` - Complete journey maps
- `resources/feature-backlog.md` - Full backlog with priorities
