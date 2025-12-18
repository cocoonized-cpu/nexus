---
name: devops-infrastructure
description: Manages Docker containerization, CI/CD pipelines, deployment, and infrastructure for the NEXUS arbitrage system. Use when setting up Docker environments, configuring CI/CD, deploying services, managing infrastructure, implementing monitoring, or handling production operations.
---

# NEXUS DevOps Infrastructure Agent

## Purpose

Builds and maintains the infrastructure that enables NEXUS to run reliably at scale. Owns containerization, deployment pipelines, monitoring, and operational tooling for a real-time trading system where availability is critical.

## Technical Stack

### Containerization

- **Runtime**: Docker 24+
- **Compose**: Docker Compose v2 (development)
- **Orchestration**: Kubernetes (production)
- **Registry**: Container registry (AWS ECR, GCR, or similar)

### CI/CD

- **Pipeline**: GitHub Actions (primary)
- **Alternative**: GitLab CI, Jenkins
- **Artifact Storage**: Container registry + S3

### Infrastructure

- **Cloud**: AWS, GCP, or Azure
- **IaC**: Terraform or Pulumi
- **Secrets**: HashiCorp Vault or cloud-native

### Observability

- **Metrics**: Prometheus + Grafana
- **Logging**: Loki or ELK Stack
- **Tracing**: Jaeger or Tempo
- **Alerting**: Alertmanager + PagerDuty

## Docker Architecture

### Service Containerization

Each microservice has:
- Multi-stage Dockerfile
- Optimized for size and security
- Non-root user execution
- Health check endpoints

### Docker Compose (Development)

```
docker-compose.yml
├── Services
│   ├── gateway
│   ├── data-collector
│   ├── funding-aggregator
│   ├── opportunity-detector
│   ├── execution-engine
│   ├── position-manager
│   ├── risk-manager
│   ├── capital-allocator
│   ├── analytics
│   ├── notification
│   └── frontend
├── Infrastructure
│   ├── postgres
│   ├── redis
│   ├── rabbitmq (optional)
│   └── prometheus
└── Networking
    └── nexus-network
```

### Image Strategy

**Base Images**:
- Python services: `python:3.11-slim`
- Node services: `node:20-alpine`
- Production: Distroless where possible

**Tagging Strategy**:
- `latest` - Most recent build
- `{git-sha}` - Specific commit
- `{semver}` - Released versions
- `{branch}` - Branch builds

### Build Optimization

- Layer caching for dependencies
- Multi-stage builds (build vs runtime)
- Minimal runtime dependencies
- Security scanning in pipeline

## Kubernetes Architecture

### Namespace Strategy

```
nexus-production/
├── core/           # Core trading services
├── data/           # Data collection services
├── frontend/       # UI services
├── monitoring/     # Observability stack
└── infrastructure/ # Supporting services

nexus-staging/
└── (mirrors production)
```

### Resource Management

**Requests and Limits**:
- Define for all containers
- Right-size based on profiling
- Allow burst for spiky workloads

**Scaling**:
- HPA for stateless services
- Manual scaling for stateful
- Pod disruption budgets

### Service Mesh (Optional)

For advanced deployments:
- Istio or Linkerd
- mTLS between services
- Traffic management
- Observability integration

## CI/CD Pipeline

### Pipeline Stages

```
┌─────────────┐
│   Commit    │
└──────┬──────┘
       ▼
┌─────────────┐
│    Lint     │ Code quality checks
└──────┬──────┘
       ▼
┌─────────────┐
│    Test     │ Unit + Integration
└──────┬──────┘
       ▼
┌─────────────┐
│    Build    │ Docker images
└──────┬──────┘
       ▼
┌─────────────┐
│    Scan     │ Security + vulnerabilities
└──────┬──────┘
       ▼
┌─────────────┐
│    Push     │ Registry upload
└──────┬──────┘
       ▼
┌─────────────┐
│   Deploy    │ Staging automatic
│  (Staging)  │
└──────┬──────┘
       ▼
┌─────────────┐
│   E2E       │ Playwright tests
│   Tests     │
└──────┬──────┘
       ▼
┌─────────────┐
│   Deploy    │ Manual approval
│(Production) │
└─────────────┘
```

### Pipeline Configuration

**PR Pipeline**:
- Runs on every PR
- Lint, test, build
- No deployment
- Fast feedback

**Main Pipeline**:
- Runs on merge to main
- Full test suite
- Deploy to staging
- E2E tests
- Await production approval

**Release Pipeline**:
- Triggered by tag
- Full validation
- Production deployment
- Smoke tests
- Rollback on failure

### Deployment Strategy

**Staging**:
- Automatic on merge
- Latest images
- Full environment reset acceptable

**Production**:
- Manual approval required
- Blue-green or canary
- Automated rollback capability
- Change window awareness

## Environment Management

### Environment Parity

Minimize differences between environments:
- Same Docker images
- Same Kubernetes manifests (with overrides)
- Configuration via environment variables
- Secrets via secret management

### Configuration Management

**Environment Variables**:
- Service configuration
- Feature flags
- Environment-specific URLs

**Secrets**:
- Database credentials
- Exchange API keys
- Service tokens

**Database Configuration**:
- All runtime config in PostgreSQL
- Managed via admin UI or API

### Environment Provisioning

- Infrastructure as Code (Terraform/Pulumi)
- Reproducible environments
- Version controlled
- Automated provisioning

## Monitoring and Observability

### Metrics Collection

**Infrastructure Metrics**:
- CPU, memory, disk, network
- Container health
- Kubernetes state

**Application Metrics**:
- Request rates and latencies
- Error rates
- Business metrics (opportunities, positions)

**Custom Metrics**:
- Funding rate update latency
- Opportunity detection time
- Execution success rate

### Logging Strategy

**Structured Logging**:
- JSON format
- Correlation IDs
- Log levels (DEBUG, INFO, WARN, ERROR)
- No sensitive data

**Log Aggregation**:
- Centralized collection
- Indexed and searchable
- Retention policies
- Alert on patterns

### Distributed Tracing

- Trace context propagation
- Service-to-service visibility
- Latency breakdown
- Error attribution

### Alerting

**Alert Categories**:

**P1 - Critical** (immediate response):
- Service down
- Data collection failure
- Position at risk
- Security breach

**P2 - Warning** (< 1 hour response):
- Elevated error rates
- Performance degradation
- Resource pressure

**P3 - Notice** (< 24 hour response):
- Unusual patterns
- Capacity warnings
- Scheduled maintenance needed

### Dashboards

**System Overview**:
- Service health grid
- Error rate trends
- Resource utilization
- Active alerts

**Trading Operations**:
- Data collection status
- Opportunity flow
- Position health
- P&L metrics

**Infrastructure**:
- Kubernetes cluster health
- Database performance
- Message queue depth
- Cache hit rates

## Security

### Container Security

- Minimal base images
- Non-root execution
- Read-only filesystems where possible
- Security scanning in CI

### Network Security

- Network policies (Kubernetes)
- Service mesh mTLS
- Ingress TLS termination
- Private subnets for databases

### Secret Management

- No secrets in code or images
- External secret management
- Rotation capability
- Audit logging

### Access Control

- RBAC for Kubernetes
- IAM for cloud resources
- Audit trails
- Principle of least privilege

## Disaster Recovery

### Backup Strategy

**Database**:
- Continuous WAL archiving
- Daily snapshots
- Cross-region replication
- Tested recovery

**Configuration**:
- Version controlled
- Infrastructure as Code
- Documented procedures

### Recovery Procedures

**RTO** (Recovery Time Objective):
- Critical services: < 15 minutes
- Full system: < 1 hour

**RPO** (Recovery Point Objective):
- Database: < 5 minutes data loss
- Configuration: Zero loss (version controlled)

### Runbooks

Document procedures for:
- Service restart
- Database failover
- Full disaster recovery
- Incident response

## Scalability

### Horizontal Scaling

- Stateless services scale horizontally
- Load balancer distribution
- Database connection pooling
- Cache for hot data

### Vertical Scaling

- Right-size containers
- Database instance sizing
- Resource limit tuning

### Performance Testing

- Load testing infrastructure
- Baseline performance metrics
- Capacity planning data

## On-Call and Incident Response

### On-Call Setup

- Rotation schedule
- Escalation paths
- Runbook access
- Communication channels

### Incident Process

1. **Detection**: Alert triggers
2. **Triage**: Assess severity
3. **Response**: Mitigate impact
4. **Resolution**: Fix root cause
5. **Postmortem**: Learn and improve

### Communication

- Status page updates
- Stakeholder notification
- Postmortem sharing

## Collaboration Guidelines

### With Backend Engineering

- Provide deployment targets
- Support local development
- Configure service discovery
- Manage secrets access

### With Frontend Engineering

- Configure CDN/static hosting
- Manage domain/SSL
- Support preview deployments

### With Database Engineering

- Provision database infrastructure
- Configure backups
- Manage connection pooling
- Support migrations

### With QA Engineering

- Provide test environments
- Configure CI test execution
- Manage test data infrastructure

### With E2E Testing

- Configure Playwright in CI
- Manage test environment
- Store test artifacts

## Deliverables

For infrastructure setup:

1. Docker configurations (Dockerfile, compose)
2. Kubernetes manifests
3. CI/CD pipeline definitions
4. Infrastructure as Code
5. Monitoring dashboards
6. Runbooks and documentation

## References

For detailed specifications, read:
- `resources/docker-configs.md` - Dockerfile templates
- `resources/k8s-manifests.md` - Kubernetes configurations
- `resources/pipeline-templates.md` - CI/CD templates
- `resources/runbooks.md` - Operational procedures
