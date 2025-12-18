---
name: frontend-engineering
description: Builds the user interface and real-time dashboard for the NEXUS arbitrage system using React, TypeScript, and shadcn/ui. Use when creating UI components, implementing real-time displays, building trading dashboards, designing user interactions, or integrating WebSocket data streams.
---

# NEXUS Frontend Engineering Agent

## Purpose

Creates a modern, real-time trading dashboard for NEXUS that displays opportunities, positions, risk metrics, and system health. Delivers a professional-grade UI optimized for traders who need instant visibility and quick actions.

## Technical Stack

### Core Technologies

- **Framework**: Next.js 14+ (App Router)
- **Language**: TypeScript (strict mode)
- **UI Library**: shadcn/ui components
- **Styling**: Tailwind CSS
- **State Management**: Zustand for global state, React Query for server state
- **Real-Time**: WebSocket with reconnection handling
- **Charts**: Recharts or TradingView lightweight charts
- **Forms**: React Hook Form with Zod validation

### Development Tools

- **Package Manager**: pnpm
- **Linting**: ESLint with strict config
- **Formatting**: Prettier
- **Testing**: Vitest + React Testing Library + Playwright

## Application Architecture

### Directory Structure

```
frontend/
├── app/                      # Next.js App Router
│   ├── (dashboard)/         # Dashboard layout group
│   │   ├── opportunities/   # Opportunity views
│   │   ├── positions/       # Position management
│   │   ├── risk/           # Risk dashboard
│   │   ├── analytics/      # Performance analytics
│   │   └── settings/       # Configuration
│   ├── api/                # API routes (if needed)
│   ├── layout.tsx          # Root layout
│   └── page.tsx            # Landing/overview
├── components/
│   ├── ui/                 # shadcn/ui components
│   ├── dashboard/          # Dashboard-specific components
│   ├── trading/            # Trading components
│   ├── charts/             # Chart components
│   └── common/             # Shared components
├── hooks/                  # Custom React hooks
├── lib/                    # Utilities and helpers
├── stores/                 # Zustand stores
├── services/               # API and WebSocket clients
├── types/                  # TypeScript type definitions
└── styles/                 # Global styles
```

## Component Guidelines

### shadcn/ui Usage

Use shadcn/ui as the foundation for all UI components:

- Install components as needed: `npx shadcn-ui@latest add [component]`
- Customize via CSS variables in `globals.css`
- Extend components in `components/ui/` when needed
- Maintain consistent styling patterns

### Component Categories

**Primitive Components** (from shadcn/ui):
- Button, Input, Select, Checkbox
- Dialog, Sheet, Popover
- Table, Card, Badge
- Tabs, Accordion
- Toast, Alert

**Domain Components** (custom):
- OpportunityCard
- PositionRow
- RiskGauge
- FundingRateDisplay
- ExecutionStatus
- PnLDisplay

### Component Structure

```typescript
// components/trading/OpportunityCard.tsx

interface OpportunityCardProps {
  opportunity: Opportunity;
  onSelect?: (id: string) => void;
  isSelected?: boolean;
}

export function OpportunityCard({ 
  opportunity, 
  onSelect,
  isSelected 
}: OpportunityCardProps) {
  // Component implementation
}
```

## Real-Time Data Handling

### WebSocket Architecture

```typescript
// services/websocket.ts

// Connection management with auto-reconnect
// Channel subscription system
// Message parsing and routing
// Heartbeat/ping-pong handling
```

### Data Flow

```
WebSocket Server
       │
       ▼
WebSocket Client (singleton)
       │
       ▼
Event Dispatcher
       │
       ├──► Zustand Store (global state)
       │
       └──► React Query Cache (invalidation)
              │
              ▼
         UI Components (reactive updates)
```

### Subscription Patterns

```typescript
// hooks/useRealTimeData.ts

// Subscribe to specific channels
// Handle connection state
// Manage subscription lifecycle
// Provide loading and error states
```

## State Management

### Zustand Stores

**Connection Store**:
- WebSocket connection status
- Reconnection state
- Error tracking

**Trading Store**:
- Selected opportunity
- Active filters
- View preferences

**Notification Store**:
- Toast queue
- Alert management

### React Query

Use for all server state:
- API data fetching
- Caching and invalidation
- Optimistic updates
- Background refetching

## Page Specifications

### Dashboard Overview

**Purpose**: At-a-glance system status and top opportunities

**Components**:
- System health indicators
- Top 5 opportunities by UOS score
- Active positions summary
- P&L summary
- Recent alerts

**Real-Time Updates**:
- Funding rates refresh every 5s
- Position P&L updates continuously
- Alerts stream in real-time

### Opportunities Page

**Purpose**: Full opportunity scanner and analysis

**Components**:
- Filter panel (exchange, asset, min spread)
- Sortable opportunity table
- Opportunity detail drawer
- Comparison tool
- Historical analysis charts

**Interactions**:
- Click row to select and show details
- Double-click or button to initiate position
- Bulk actions for watchlist

### Positions Page

**Purpose**: Active position monitoring and management

**Components**:
- Position cards or table view
- Health status indicators
- P&L breakdown (funding, price, fees)
- Exit controls
- Position timeline

**Interactions**:
- Adjust exit triggers
- Add margin
- Force close
- View execution history

### Risk Dashboard

**Purpose**: Real-time risk monitoring

**Components**:
- Portfolio risk summary
- Limit utilization gauges
- Concentration charts (venue, asset)
- Drawdown chart
- Alert history

**Interactions**:
- Adjust limits (with confirmation)
- Acknowledge alerts
- Trigger emergency protocols

### Settings Page

**Purpose**: System configuration

**Components**:
- Exchange credential management
- Strategy parameters
- Risk limit configuration
- Alert preferences
- User preferences

**Interactions**:
- Edit configurations (stored in DB)
- Test exchange connections
- Export/import settings

## UI/UX Standards

### Visual Design

- Dark theme optimized for trading (reduce eye strain)
- High contrast for critical data
- Color coding: Green (positive), Red (negative), Yellow (warning)
- Consistent spacing using Tailwind scale
- Clear visual hierarchy

### Data Display

- Numbers right-aligned, formatted consistently
- Percentages with appropriate precision (2-4 decimals)
- Timestamps in user's timezone with relative time option
- Currency values with proper formatting
- Status badges for categorical data

### Loading States

- Skeleton loaders for initial load
- Subtle indicators for background updates
- Disable interactions during mutations
- Clear error states with retry options

### Responsive Design

- Primary: Desktop (1920x1080 and up)
- Secondary: Laptop (1366x768)
- Tertiary: Tablet landscape
- Mobile: Status monitoring only (not full functionality)

## Performance Optimization

### Rendering

- Virtualize long lists (opportunities, trades)
- Memoize expensive computations
- Lazy load non-critical components
- Avoid unnecessary re-renders

### Data

- Debounce filter inputs
- Throttle real-time updates for UI (max 10 fps)
- Cache static data aggressively
- Paginate large datasets

### Bundle

- Code split by route
- Tree shake unused code
- Optimize images
- Analyze bundle regularly

## Accessibility

### Requirements

- WCAG 2.1 AA compliance
- Keyboard navigation for all interactions
- Screen reader compatibility
- Focus management
- Color not sole indicator

### Implementation

- Use semantic HTML
- ARIA labels where needed
- Focus trapping in modals
- Skip navigation link
- Reduced motion support

## Testing Strategy

### Unit Tests (Vitest)

- Test component rendering
- Test hooks in isolation
- Test utility functions
- Mock external dependencies

### Integration Tests (React Testing Library)

- Test component interactions
- Test form submissions
- Test state updates
- Test error handling

### E2E Tests (Playwright)

- Delegate to e2e-testing agent
- Provide testable data attributes
- Support test environment

### Test Data Attributes

Add `data-testid` attributes for E2E:

```tsx
<Button data-testid="execute-trade-btn">Execute</Button>
<Table data-testid="opportunities-table">...</Table>
```

## Collaboration Guidelines

### With Backend Engineering

- Consume OpenAPI specs for type generation
- Coordinate WebSocket event schemas
- Report API issues promptly
- Request new endpoints as needed

### With Product Management

- Implement to acceptance criteria
- Raise UX concerns early
- Participate in design reviews
- Demo features regularly

### With QA Engineering

- Provide testable interfaces
- Document component behaviors
- Support test data setup
- Fix UI bugs promptly

### With E2E Testing

- Add consistent test IDs
- Document page object patterns
- Maintain testable state
- Avoid breaking test selectors

## References

For detailed specifications, read:
- `resources/component-library.md` - Component catalog
- `resources/design-system.md` - Colors, typography, spacing
- `resources/websocket-events.md` - Real-time event schemas
