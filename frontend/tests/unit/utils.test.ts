import { describe, it, expect } from 'vitest';
import { cn, formatCurrency, formatPercent, formatNumber, getScoreColor } from '@/lib/utils';

describe('cn (classNames utility)', () => {
  it('should merge class names', () => {
    expect(cn('foo', 'bar')).toBe('foo bar');
  });

  it('should handle conditional classes', () => {
    expect(cn('foo', false && 'bar', 'baz')).toBe('foo baz');
  });

  it('should merge tailwind classes correctly', () => {
    expect(cn('px-2 py-1', 'px-4')).toBe('py-1 px-4');
  });
});

describe('formatCurrency', () => {
  it('should format positive numbers', () => {
    expect(formatCurrency(1234.56)).toBe('$1,234.56');
  });

  it('should format negative numbers', () => {
    expect(formatCurrency(-1234.56)).toBe('-$1,234.56');
  });

  it('should format zero', () => {
    expect(formatCurrency(0)).toBe('$0.00');
  });

  it('should respect decimal places', () => {
    expect(formatCurrency(1234.5678, 4)).toBe('$1,234.5678');
  });
});

describe('formatPercent', () => {
  it('should format positive percentages with plus sign', () => {
    expect(formatPercent(12.34)).toBe('+12.34%');
  });

  it('should format negative percentages', () => {
    expect(formatPercent(-12.34)).toBe('-12.34%');
  });

  it('should format zero', () => {
    expect(formatPercent(0)).toBe('+0.00%');
  });
});

describe('formatNumber', () => {
  it('should format numbers with thousands separator', () => {
    expect(formatNumber(1234567.89)).toBe('1,234,567.89');
  });
});

describe('getScoreColor', () => {
  it('should return green for scores >= 80', () => {
    expect(getScoreColor(80)).toBe('text-green-500');
    expect(getScoreColor(100)).toBe('text-green-500');
  });

  it('should return yellow for scores >= 60', () => {
    expect(getScoreColor(60)).toBe('text-yellow-500');
    expect(getScoreColor(79)).toBe('text-yellow-500');
  });

  it('should return orange for scores >= 40', () => {
    expect(getScoreColor(40)).toBe('text-orange-500');
    expect(getScoreColor(59)).toBe('text-orange-500');
  });

  it('should return red for scores < 40', () => {
    expect(getScoreColor(39)).toBe('text-red-500');
    expect(getScoreColor(0)).toBe('text-red-500');
  });
});
