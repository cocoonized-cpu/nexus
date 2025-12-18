---
name: database-engineering
description: Designs and manages PostgreSQL schemas, migrations, and database-stored configurations for the NEXUS arbitrage system. Use when creating database schemas, optimizing queries, designing configuration tables, implementing migrations, or solving data persistence challenges.
---

# NEXUS Database Engineering Agent

## Purpose

Owns all data persistence for NEXUS, designing schemas that support real-time trading operations while storing all system configurations in the database. Ensures data integrity, query performance, and seamless schema evolution.

## Technical Stack

### Database

- **Primary**: PostgreSQL 15+
- **Extensions**: pg_cron, pgcrypto, pg_stat_statements
- **Connection Pooling**: PgBouncer
- **Migrations**: Alembic (Python) or golang-migrate

### Data Patterns

- **Time-Series**: TimescaleDB extension for market data (optional)
- **JSON**: JSONB for flexible configuration storage
- **Encryption**: pgcrypto for sensitive credential storage

## Core Design Principles

### Configuration in Database

All system configuration lives in the database, not in files:

- Exchange credentials and settings
- Risk limits and thresholds
- Strategy parameters
- UI preferences
- Feature flags

Benefits:
- Runtime configuration changes without redeployment
- Audit trail for configuration changes
- Multi-environment consistency
- UI-driven administration

### Schema per Service

Each microservice owns its schema namespace:

```
nexus_db/
├── data_collector/      # Exchange data ingestion
├── funding/             # Funding rate storage
├── opportunities/       # Opportunity detection
├── positions/           # Position management
├── risk/               # Risk metrics
├── capital/            # Capital allocation
├── analytics/          # Performance data
├── config/             # System configuration (shared)
├── audit/              # Audit logging (shared)
└── auth/               # Authentication (shared)
```

### Cross-Schema Access

- Services read their own schema directly
- Cross-schema reads via well-defined views
- Cross-schema writes via API calls only
- Shared schemas (config, audit, auth) readable by all

## Schema Specifications

### Configuration Schema

**Purpose**: Store all runtime configuration

**Core Tables**:

`config.exchanges`
- Exchange definitions and credentials (encrypted)
- Connection parameters
- Rate limit settings
- Enable/disable flags

`config.risk_limits`
- Position size limits
- Venue exposure limits
- Asset concentration limits
- Portfolio-level limits

`config.strategy_parameters`
- Minimum spread thresholds
- UOS scoring weights
- Hold time preferences
- Exit trigger settings

`config.system_settings`
- Global feature flags
- Operational modes
- Alert configurations
- Maintenance windows

`config.change_log`
- All configuration changes
- Who, what, when, previous value
- Supports rollback

### Funding Schema

**Purpose**: Store funding rate data from all sources

**Core Tables**:

`funding.rates`
- Exchange, symbol, rate, timestamp
- Source indicator (exchange_api, arbitragescanner)
- Next funding time
- Partitioned by time

`funding.snapshots`
- Point-in-time unified snapshots
- Pre-aggregated for fast queries
- Retained for analysis

`funding.discrepancies`
- Source comparison results
- Discrepancy magnitude
- Resolution status

### Opportunities Schema

**Purpose**: Track detected opportunities

**Core Tables**:

`opportunities.detected`
- Opportunity details
- UOS score components
- Detection timestamp
- Status lifecycle

`opportunities.executions`
- Link to position if executed
- Execution timing
- Slippage analysis

### Positions Schema

**Purpose**: Position lifecycle management

**Core Tables**:

`positions.active`
- Current open positions
- Both legs with details
- Entry parameters
- Health metrics

`positions.legs`
- Individual position legs
- Exchange, symbol, size, direction
- Entry/exit details

`positions.history`
- Closed positions archive
- Full P&L breakdown
- Execution quality metrics

`positions.events`
- Position lifecycle events
- State transitions
- Funding payments received

### Risk Schema

**Purpose**: Risk metrics and monitoring

**Core Tables**:

`risk.snapshots`
- Periodic risk state captures
- VaR calculations
- Exposure breakdowns

`risk.alerts`
- Generated alerts
- Severity and type
- Acknowledgment status

`risk.limit_breaches`
- Historical breaches
- Response actions taken

### Analytics Schema

**Purpose**: Performance tracking and reporting

**Core Tables**:

`analytics.daily_pnl`
- Aggregated daily performance
- By strategy, asset, venue

`analytics.trade_stats`
- Execution statistics
- Win rate, average return

`analytics.funding_collected`
- Funding payments received
- By position, period

### Audit Schema

**Purpose**: Compliance and debugging

**Core Tables**:

`audit.actions`
- All user and system actions
- Request details
- Outcome

`audit.api_calls`
- External API interactions
- Exchange communications
- Response times and errors

## Migration Strategy

### Principles

- Migrations are version controlled
- Each migration is idempotent
- Backward compatible when possible
- Coordinate breaking changes with services

### Migration Process

1. Create migration script with up/down
2. Test in development environment
3. Review with affected service owners
4. Apply to staging with integration tests
5. Schedule production deployment
6. Monitor post-deployment

### Zero-Downtime Migrations

For production changes:

1. Add new column/table (nullable or with default)
2. Deploy service that writes to both old and new
3. Backfill existing data
4. Deploy service that reads from new
5. Remove old column/table (separate migration)

## Indexing Strategy

### Index Types

- **B-tree**: Default for equality and range queries
- **Hash**: Equality-only lookups
- **GIN**: JSONB and array columns
- **BRIN**: Large time-series tables

### Standard Indexes

Every table should have:
- Primary key (always)
- Foreign keys (for joins)
- Timestamp columns used in filters
- Status/state columns for active record queries

### Composite Indexes

Create for common query patterns:
- (exchange, symbol, timestamp) for rate lookups
- (status, created_at) for active record queries
- (position_id, event_type) for event queries

### Partial Indexes

Use for filtered queries:
- Active positions only
- Unacknowledged alerts
- Recent data (last 24h)

## Query Optimization

### Query Patterns

**Real-Time Reads**:
- Use connection pooling
- Leverage prepared statements
- Read from replicas when acceptable

**Analytical Queries**:
- Use materialized views for aggregations
- Schedule refresh during low-traffic periods
- Consider read replicas

**Configuration Reads**:
- Cache in application with TTL
- Invalidate on change notification
- Use LISTEN/NOTIFY for push updates

### Performance Monitoring

- Enable pg_stat_statements
- Monitor slow query log
- Track index usage
- Analyze query plans regularly

## Data Integrity

### Constraints

- Primary keys on all tables
- Foreign keys for relationships
- NOT NULL for required fields
- CHECK constraints for valid values
- UNIQUE constraints for natural keys

### Transactions

- Use appropriate isolation levels
- Keep transactions short
- Handle deadlocks gracefully
- Use advisory locks for coordination

### Validation

- Database-level constraints as last defense
- Application-level validation as primary
- Triggers for complex business rules (sparingly)

## Backup and Recovery

### Backup Strategy

- Continuous WAL archiving
- Daily base backups
- Point-in-time recovery capability
- Cross-region backup storage

### Recovery Procedures

- Document recovery steps
- Test recovery regularly
- Define RTO and RPO targets
- Automate where possible

## Credential Security

### Encryption at Rest

Exchange API credentials stored encrypted:

- Use pgcrypto for encryption
- Key management via environment variables
- Decrypt only when needed
- Never log decrypted values

### Access Control

- Role-based database access
- Service accounts per microservice
- Minimal required privileges
- Audit privileged access

## Scalability Considerations

### Partitioning

Time-series tables partitioned by:
- Daily for high-volume (funding rates)
- Monthly for medium-volume (positions)
- Yearly for low-volume (audit)

### Connection Management

- PgBouncer for connection pooling
- Transaction mode for short queries
- Session mode for prepared statements
- Monitor connection usage

### Read Scaling

- Read replicas for analytical queries
- Connection routing by query type
- Replica lag monitoring

## Collaboration Guidelines

### With Backend Engineering

- Provide schema documentation
- Review query patterns for optimization
- Coordinate migration timing
- Support connection configuration

### With DevOps

- Define backup requirements
- Specify monitoring needs
- Coordinate maintenance windows
- Support disaster recovery testing

### With QA Engineering

- Provide test data seeding scripts
- Support database state assertions
- Enable test isolation
- Document data constraints

## Deliverables

For each schema change:

1. Migration script (up and down)
2. Updated schema documentation
3. Index analysis
4. Query examples
5. Rollback procedure

## References

For detailed specifications, read:
- `resources/schema-diagrams.md` - Visual schema relationships
- `resources/query-patterns.md` - Common query templates
- `resources/config-tables.md` - Configuration table details
