import { describe, it, expect } from 'vitest';

// Test the message generation for the activity log
// This mirrors the generateMessage function in activity-log-enhanced.tsx

// Generate human-readable message (from activity-log-enhanced.tsx)
function generateMessage(eventType: string, resource: string, details?: Record<string, unknown>): string {
  const type = eventType.replace(/_/g, ' ');

  // Special cases for common events
  if (eventType === 'system_start') return 'System started';
  if (eventType === 'system_stop') return 'System stopped';
  if (eventType === 'mode_change') {
    const newMode = details?.new_mode || 'unknown';
    const prevMode = details?.previous_mode;
    return prevMode ? `Mode changed from ${prevMode} to ${newMode}` : `Mode changed to ${newMode}`;
  }
  if (eventType === 'opportunity_detected') {
    const score = details?.uos_score ? `(UOS: ${Number(details.uos_score).toFixed(1)})` : '';
    return `Opportunity detected: ${resource} ${score}`;
  }
  if (eventType.includes('alert')) {
    return details?.message ? String(details.message) : `${type} on ${resource}`;
  }

  // Position events
  if (eventType === 'position_opened') {
    const capital = details?.capital_deployed ? ` ($${Number(details.capital_deployed).toFixed(0)})` : '';
    return `Position opened: ${resource}${capital}`;
  }
  if (eventType === 'position_closed') {
    const pnl = details?.realized_pnl !== undefined
      ? ` PnL: $${Number(details.realized_pnl).toFixed(2)}`
      : '';
    const reason = details?.exit_reason ? ` (${details.exit_reason})` : '';
    return `Position closed: ${resource}${pnl}${reason}`;
  }
  if (eventType === 'funding_received') {
    const amount = details?.amount ? ` +$${Number(details.amount).toFixed(4)}` : '';
    return `Funding received: ${resource}${amount}`;
  }
  if (eventType === 'funding_paid') {
    const amount = details?.amount ? ` -$${Math.abs(Number(details.amount)).toFixed(4)}` : '';
    return `Funding paid: ${resource}${amount}`;
  }
  if (eventType === 'health_changed') {
    const oldHealth = details?.old_health || 'unknown';
    const newHealth = details?.new_health || 'unknown';
    return `Position health changed: ${resource} ${oldHealth} → ${newHealth}`;
  }
  if (eventType === 'rebalance_triggered') {
    return `Rebalance triggered: ${resource}`;
  }
  if (eventType === 'stop_loss_triggered') {
    const price = details?.trigger_price ? ` at $${Number(details.trigger_price).toFixed(2)}` : '';
    return `Stop loss triggered: ${resource}${price}`;
  }
  if (eventType === 'take_profit_triggered') {
    const pnl = details?.realized_pnl ? ` PnL: $${Number(details.realized_pnl).toFixed(2)}` : '';
    return `Take profit triggered: ${resource}${pnl}`;
  }

  return `${type}: ${resource}`;
}

describe('Activity Log Message Generation', () => {
  describe('System Events', () => {
    it('should generate system start message', () => {
      expect(generateMessage('system_start', '')).toBe('System started');
    });

    it('should generate system stop message', () => {
      expect(generateMessage('system_stop', '')).toBe('System stopped');
    });

    it('should generate mode change message with previous mode', () => {
      const details = { previous_mode: 'standard', new_mode: 'aggressive' };
      expect(generateMessage('mode_change', '', details)).toBe('Mode changed from standard to aggressive');
    });

    it('should generate mode change message without previous mode', () => {
      const details = { new_mode: 'standard' };
      expect(generateMessage('mode_change', '', details)).toBe('Mode changed to standard');
    });
  });

  describe('Opportunity Events', () => {
    it('should generate opportunity detected message with score', () => {
      const details = { uos_score: 85.5 };
      expect(generateMessage('opportunity_detected', 'BTC-PERP', details)).toBe('Opportunity detected: BTC-PERP (UOS: 85.5)');
    });

    it('should generate opportunity detected message without score', () => {
      expect(generateMessage('opportunity_detected', 'ETH-PERP', {})).toBe('Opportunity detected: ETH-PERP ');
    });
  });

  describe('Position Events', () => {
    it('should generate position opened message with capital', () => {
      const details = { capital_deployed: 1000 };
      expect(generateMessage('position_opened', 'BTC-PERP', details)).toBe('Position opened: BTC-PERP ($1000)');
    });

    it('should generate position opened message without capital', () => {
      expect(generateMessage('position_opened', 'BTC-PERP', {})).toBe('Position opened: BTC-PERP');
    });

    it('should generate position closed message with PnL and reason', () => {
      const details = { realized_pnl: 125.50, exit_reason: 'manual' };
      expect(generateMessage('position_closed', 'BTC-PERP', details)).toBe('Position closed: BTC-PERP PnL: $125.50 (manual)');
    });

    it('should generate position closed message with negative PnL', () => {
      const details = { realized_pnl: -50.25 };
      expect(generateMessage('position_closed', 'ETH-PERP', details)).toBe('Position closed: ETH-PERP PnL: $-50.25');
    });

    it('should generate position closed message without details', () => {
      expect(generateMessage('position_closed', 'SOL-PERP', {})).toBe('Position closed: SOL-PERP');
    });

    it('should generate funding received message with amount', () => {
      const details = { amount: 2.5678 };
      expect(generateMessage('funding_received', 'BTC-PERP', details)).toBe('Funding received: BTC-PERP +$2.5678');
    });

    it('should generate funding paid message with amount', () => {
      const details = { amount: -1.2345 };
      expect(generateMessage('funding_paid', 'ETH-PERP', details)).toBe('Funding paid: ETH-PERP -$1.2345');
    });

    it('should generate health changed message', () => {
      const details = { old_health: 'healthy', new_health: 'warning' };
      expect(generateMessage('health_changed', 'BTC-PERP', details)).toBe('Position health changed: BTC-PERP healthy → warning');
    });

    it('should generate rebalance triggered message', () => {
      expect(generateMessage('rebalance_triggered', 'ETH-PERP', {})).toBe('Rebalance triggered: ETH-PERP');
    });

    it('should generate stop loss triggered message with price', () => {
      const details = { trigger_price: 42000.50 };
      expect(generateMessage('stop_loss_triggered', 'BTC-PERP', details)).toBe('Stop loss triggered: BTC-PERP at $42000.50');
    });

    it('should generate take profit triggered message with PnL', () => {
      const details = { realized_pnl: 500.00 };
      expect(generateMessage('take_profit_triggered', 'BTC-PERP', details)).toBe('Take profit triggered: BTC-PERP PnL: $500.00');
    });
  });

  describe('Alert Events', () => {
    it('should use custom message from details', () => {
      const details = { message: 'Risk limit exceeded' };
      expect(generateMessage('risk_alert', 'system', details)).toBe('Risk limit exceeded');
    });

    it('should generate fallback alert message', () => {
      expect(generateMessage('margin_alert', 'binance', {})).toBe('margin alert on binance');
    });
  });

  describe('Generic Events', () => {
    it('should format unknown event types with underscores replaced', () => {
      expect(generateMessage('custom_event_type', 'resource_name', {})).toBe('custom event type: resource_name');
    });
  });
});
