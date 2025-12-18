---
name: backend-engineering
description: Designs and implements microservices, APIs, and business logic for the NEXUS arbitrage system. Use when building backend services, implementing trading logic, creating API endpoints, integrating with exchanges, handling real-time data processing, or designing event-driven architectures.
---

# NEXUS Backend Engineering Agent

## Purpose

Builds the core microservices powering NEXUS, implementing the funding rate arbitrage logic, exchange integrations, and real-time data pipelines. Delivers production-grade, scalable services following best practices for financial systems.

## Technical Stack

### Core Technologies

- **Language**: Python 3.11+ (primary), TypeScript (where appropriate)
- **Framework**: FastAPI for REST APIs
- **Async**: asyncio for concurrent operations
- **Message Broker**: Redis Pub/Sub or RabbitMQ for event streaming
- **Caching**: Redis for hot data
- **Task Queue**: Celery for background jobs

### Infrastructure

- **Containerization**: Docker with multi-stage builds
- **Orchestration**: Docker Compose (dev), Kubernetes (prod)
- **Database**: PostgreSQL (via database-engineering agent)
- **Monitoring**: Prometheus metrics, structured logging

## Microservice Architecture

### Service Decomposition

```
nexus/
├── services/
│   ├── gateway/              # API Gateway / BFF
│   ├── data-collector/       # Exchange data ingestion
│   ├── funding-aggregator/   # Dual-source rate aggregation
│   ├── opportunity-detector/ # Opportunity scanning & scoring
│   ├── execution-engine/     # Order execution
│   ├── position-manager/     # Position lifecycle
│   ├── risk-manager/         # Risk monitoring & limits
│   ├── capital-allocator/    # Capital management
│   ├── analytics/            # Performance tracking
│   └── notification/         # Alerts & notifications
├── shared/
│   ├── models/               # Shared data models
│   ├── events/               # Event definitions
│   └── utils/                # Common utilities
└── infrastructure/
    ├── docker/
    └── kubernetes/
```

### Service Boundaries

Each service:
- Owns its domain logic completely
- Has its own database schema (or schema namespace)
- Communicates via well-defined APIs or events
- Can be deployed independently
- Has its own test suite

## Service Specifications

### Data Collector Service

**Responsibility**: Ingest funding rates from exchange APIs

**Key Components**:
- Exchange provider adapters (Binance, Bybit, OKX, etc.)
- Rate limiter per exchange
- Connection pool management
- Retry and fallback logic

**Events Published**:
- `funding_rate.updated` - New rate received
- `exchange.health_changed` - Exchange status change

**Configuration** (stored in database):
- Exchange credentials (encrypted)
- Refresh intervals per exchange
- Rate limit settings

### Funding Aggregator Service

**Responsibility**: Merge dual-source data (Exchange APIs + ArbitrageScanner)

**Key Components**:
- ArbitrageScanner client
- Reconciliation engine
- Unified snapshot builder
- Discrepancy detector

**Events Published**:
- `unified_snapshot.ready` - New aggregated data
- `data.discrepancy_detected` - Source mismatch

**Configuration**:
- ArbitrageScanner endpoints
- Reconciliation tolerance thresholds
- Fallback preferences

### Opportunity Detector Service

**Responsibility**: Identify and score arbitrage opportunities

**Key Components**:
- Quick scanner (using maxSpread)
- Deep validator
- UOS scoring engine
- Opportunity ranker

**Events Published**:
- `opportunity.discovered` - New opportunity found
- `opportunity.expired` - Opportunity no longer viable

**Configuration**:
- Minimum spread thresholds
- UOS scoring weights
- Asset/exchange filters

### Execution Engine Service

**Responsibility**: Execute trades across exchanges

**Key Components**:
- Order router
- Execution handlers per exchange
- Slippage tracker
- Partial fill manager

**Events Published**:
- `order.submitted`
- `order.filled`
- `order.failed`
- `execution.completed`

**Configuration**:
- Order type preferences
- Slippage tolerances
- Timeout settings

### Position Manager Service

**Responsibility**: Track and manage active positions

**Key Components**:
- Position lifecycle state machine
- Leg synchronizer
- P&L calculator
- Exit trigger evaluator

**Events Published**:
- `position.opened`
- `position.health_changed`
- `position.closing`
- `position.closed`

**Configuration**:
- Hold time limits
- Delta tolerances
- Health thresholds

### Risk Manager Service

**Responsibility**: Monitor and enforce risk limits

**Key Components**:
- Limit checker (position, venue, asset, portfolio)
- VaR calculator
- Drawdown monitor
- Emergency protocol handler

**Events Published**:
- `risk.limit_warning`
- `risk.limit_breach`
- `risk.emergency_triggered`

**Configuration**:
- All risk limits (stored in database)
- Alert thresholds
- Emergency protocols

## API Design Standards

### REST Conventions

- Use plural nouns for resources: `/opportunities`, `/positions`
- HTTP methods match semantics: GET (read), POST (create), PUT (update), DELETE (remove)
- Return appropriate status codes
- Include pagination for list endpoints
- Version APIs: `/api/v1/...`

### Response Format

```python
{
    "success": true,
    "data": { ... },
    "meta": {
        "timestamp": "2025-12-16T20:00:00Z",
        "request_id": "uuid"
    }
}

# Error response
{
    "success": false,
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "Human readable message",
        "details": { ... }
    }
}
```

### WebSocket Events

For real-time data, use structured events:

```python
{
    "event": "funding_rate.update",
    "channel": "rates:BTCUSDT",
    "data": { ... },
    "timestamp": "2025-12-16T20:00:00.123Z"
}
```

## Event-Driven Patterns

### Event Schema

```python
{
    "event_id": "uuid",
    "event_type": "funding_rate.updated",
    "source": "data-collector",
    "timestamp": "2025-12-16T20:00:00.123Z",
    "correlation_id": "uuid",  # For tracing
    "payload": { ... }
}
```

### Event Categories

- **Domain Events**: Business state changes
- **Integration Events**: Cross-service communication
- **System Events**: Health, metrics, errors

### Saga Pattern

For multi-service transactions (e.g., opening a position):

1. Position Manager initiates saga
2. Capital Allocator reserves funds
3. Execution Engine places orders
4. On success: Position created
5. On failure: Compensating transactions rollback

## Error Handling

### Error Categories

- **Transient**: Retry with backoff (network issues)
- **Permanent**: Fail fast (validation errors)
- **Partial**: Handle gracefully (one leg fails)

### Retry Strategy

```python
# Exponential backoff with jitter
max_retries = 3
base_delay = 1.0
max_delay = 30.0

for attempt in range(max_retries):
    delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)
```

### Circuit Breaker

Implement circuit breaker for exchange API calls:
- **Closed**: Normal operation
- **Open**: Fail fast after threshold failures
- **Half-Open**: Test recovery periodically

## Real-Time Processing

### Data Flow

```
Exchange APIs ─┐
               ├─► Data Collector ─► Redis Pub/Sub ─► Consumers
ArbitrageScanner─┘

Consumers:
├── Funding Aggregator (reconciliation)
├── Opportunity Detector (scanning)
├── Risk Manager (monitoring)
└── WebSocket Gateway (UI updates)
```

### Latency Requirements

- Exchange data → Cache: < 100ms
- Opportunity detection cycle: < 500ms
- Risk check: < 50ms
- WebSocket broadcast: < 100ms

## Security Practices

### Credential Management

- Store exchange API keys encrypted in database
- Use environment variables for service secrets
- Rotate credentials regularly
- Never log sensitive data

### API Security

- Require authentication for all endpoints
- Implement rate limiting
- Validate all inputs
- Sanitize outputs

## Testing Requirements

### Unit Tests

- Test business logic in isolation
- Mock external dependencies
- Cover edge cases and error paths
- Minimum 80% code coverage

### Integration Tests

- Test service-to-service communication
- Use test containers for dependencies
- Verify event publishing/consumption
- Test database interactions

### Contract Tests

- Verify API contracts between services
- Test event schema compatibility
- Catch breaking changes early

## Observability

### Logging

- Structured JSON logs
- Include correlation IDs
- Log at appropriate levels
- Avoid logging sensitive data

### Metrics

- Request latency (histogram)
- Error rates (counter)
- Active connections (gauge)
- Business metrics (opportunities found, orders executed)

### Tracing

- Propagate trace context across services
- Tag spans with relevant metadata
- Sample appropriately for production

## Collaboration Guidelines

### With Database Engineering

- Define data requirements before implementation
- Request schema changes through proper channels
- Coordinate migration timing

### With Frontend Engineering

- Publish API documentation (OpenAPI)
- Provide WebSocket event schemas
- Support CORS appropriately

### With QA Engineering

- Write testable code
- Provide test hooks where needed
- Document test data requirements

### With DevOps

- Follow containerization standards
- Expose health check endpoints
- Configure for environment-based settings

## References

For detailed specifications, read:
- `resources/service-contracts.md` - API specifications
- `resources/event-catalog.md` - Event schemas
- `resources/exchange-adapters.md` - Exchange integration details
