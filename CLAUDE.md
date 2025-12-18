# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Backend (Python/FastAPI)

```bash
# Install dependencies
pip install -r requirements.txt

# Run linting and formatting
black . && isort . && flake8

# Run all tests with coverage
pytest tests/ -v --cov=src --cov-report=html

# Run single test file or function
pytest tests/unit/test_specific.py -v
pytest tests/unit/test_specific.py::test_function -v

# Run a microservice in dev mode
cd services/<service-name>
uvicorn main:app --reload --port 8001
```

### Frontend (Next.js/TypeScript)

```bash
cd frontend

# Install dependencies
pnpm install

# Run dev server
pnpm dev

# Lint and format
pnpm lint
pnpm format

# Run unit tests
pnpm test

# Run E2E tests
pnpm test:e2e
```

### Docker Development

```bash
# Start all services
docker compose up -d

# Start only infrastructure (for local service development)
docker compose up -d postgres redis

# View logs
docker compose logs -f <service-name>

# Rebuild a specific service
docker compose build <service-name>
```

## Architecture Overview

NEXUS is a funding rate arbitrage system built as event-driven microservices with a real-time dashboard.

### Critical Design Patterns

**Dual-Source Funding Rates**: All funding rate data flows through two sources:
- PRIMARY: Direct exchange APIs (Binance, Bybit, OKX, Hyperliquid, etc.)
- SECONDARY: ArbitrageScanner API for validation and gap-filling
- The `funding-aggregator` service reconciles both sources before downstream consumption

**Configuration in Database**: All runtime configuration lives in PostgreSQL `config` schema, not config files. This includes exchange credentials, risk limits, strategy parameters, and feature flags. Services read config from DB on startup and subscribe to change events.

**Event-Driven Communication**: Services communicate via Redis Pub/Sub events. Each service owns its domain and publishes events for state changes. Other services subscribe to relevant event channels.

### Service Responsibilities

| Service | Purpose |
|---------|---------|
| `gateway` | API Gateway, WebSocket connections, auth |
| `data-collector` | Fetches data from exchange APIs |
| `funding-aggregator` | Merges dual-source funding rates |
| `opportunity-detector` | Scans for arbitrage opportunities, calculates UOS scores |
| `execution-engine` | Places and manages orders across exchanges |
| `position-manager` | Tracks position lifecycle, P&L, exit optimization |
| `risk-manager` | Enforces limits, monitors exposure, triggers emergencies |
| `capital-allocator` | Distributes capital across opportunities |
| `analytics` | Performance tracking, attribution analysis |
| `notification` | Alerts via Telegram, Discord, Email |

### Data Flow

```
Exchange APIs ─┐
               ├→ data-collector → funding-aggregator → opportunity-detector
ArbitrageScanner ─┘                                              │
                                                                  ▼
                                              capital-allocator → execution-engine
                                                                  │
                                                                  ▼
                                              position-manager ← risk-manager
```

## Multi-Agent Development

This project uses specialized Claude agents for development. Invoke by describing tasks in their domain.

| Agent | Domain |
|-------|--------|
| `backend-engineering` | Microservices, APIs, exchange integrations |
| `frontend-engineering` | Dashboard, React components, WebSocket integration |
| `database-engineering` | PostgreSQL schemas, migrations, query optimization |
| `devops-infrastructure` | Docker, CI/CD, Kubernetes, monitoring |
| `qa-engineering` | Test strategy, test cases, quality gates |
| `e2e-testing` | Playwright automation, user journey tests |
| `product-management` | Requirements, user stories, acceptance criteria |
| `project-orchestrator` | Sprint planning, cross-team coordination |

Agent skills are defined in `.claude/skills/*/SKILL.md`.

## Conventions

### Code Style
- Python: Black + isort + flake8
- TypeScript: ESLint + Prettier
- SQL: snake_case naming

### Commits
```
type(scope): description

Types: feat, fix, docs, style, refactor, test, chore
Scope: service name or component
```

### Branches
```
feature/NEXUS-123-description
fix/NEXUS-456-description
```

## Quality Gates

- Unit test coverage: 80% minimum
- All service boundaries have integration tests
- Critical user journeys have E2E tests
- Performance: <200ms API response, <500ms opportunity detection cycle

## Key References

- `NEXUS_Whitepaper.md` - System design, strategy philosophy, risk framework
- `NEXUS_Implementation_Spec.md` - Technical specifications, data models, API contracts
- `.claude/skills/*/SKILL.md` - Agent-specific implementation guidelines
