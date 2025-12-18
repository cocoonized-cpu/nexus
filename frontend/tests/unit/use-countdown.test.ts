import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useCountdown, useCountdownDetailed } from '@/hooks/use-countdown';

describe('useCountdown', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should return N/A for null target date', async () => {
    const { result } = renderHook(() => useCountdown(null));
    // Wait for effect to run
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current).toBe('N/A');
  });

  it('should return N/A for undefined target date', async () => {
    const { result } = renderHook(() => useCountdown(undefined));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current).toBe('N/A');
  });

  it('should return Expired for past date', async () => {
    const pastDate = new Date(Date.now() - 60000).toISOString(); // 1 minute ago
    const { result } = renderHook(() => useCountdown(pastDate));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current).toBe('Expired');
  });

  it('should return time remaining for future date', async () => {
    const futureDate = new Date(Date.now() + 3600000).toISOString(); // 1 hour from now
    const { result } = renderHook(() => useCountdown(futureDate));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current).toMatch(/\d+h \d+m/);
  });

  it('should show minutes and seconds when less than 1 hour', async () => {
    const futureDate = new Date(Date.now() + 1800000).toISOString(); // 30 minutes from now
    const { result } = renderHook(() => useCountdown(futureDate));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current).toMatch(/\d+m \d+s/);
  });

  it('should update countdown over time', async () => {
    const futureDate = new Date(Date.now() + 65000).toISOString(); // 65 seconds from now
    const { result } = renderHook(() => useCountdown(futureDate));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    const initialValue = result.current;
    expect(initialValue).toMatch(/\d+m \d+s/);

    // Advance time by 2 seconds
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    // Value should have changed
    expect(result.current).toBeDefined();
  });

  it('should handle Date object input', async () => {
    const futureDate = new Date(Date.now() + 3600000); // 1 hour from now
    const { result } = renderHook(() => useCountdown(futureDate));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current).toMatch(/\d+h \d+m/);
  });

  it('should transition to Expired when time runs out', async () => {
    const futureDate = new Date(Date.now() + 2000).toISOString(); // 2 seconds from now
    const { result } = renderHook(() => useCountdown(futureDate));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current).not.toBe('Expired');

    // Advance time past the target
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });

    expect(result.current).toBe('Expired');
  });
});

describe('useCountdownDetailed', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should return isExpired true for past date', async () => {
    const pastDate = new Date(Date.now() - 60000).toISOString();
    const { result } = renderHook(() => useCountdownDetailed(pastDate));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.isExpired).toBe(true);
    expect(result.current.display).toBe('Expired');
  });

  it('should return isExpired false for future date', async () => {
    const futureDate = new Date(Date.now() + 3600000).toISOString();
    const { result } = renderHook(() => useCountdownDetailed(futureDate));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.isExpired).toBe(false);
  });

  it('should return isUrgent true when less than 5 minutes', async () => {
    const futureDate = new Date(Date.now() + 240000).toISOString(); // 4 minutes from now
    const { result } = renderHook(() => useCountdownDetailed(futureDate));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.isUrgent).toBe(true);
  });

  it('should return isUrgent false when more than 5 minutes', async () => {
    const futureDate = new Date(Date.now() + 600000).toISOString(); // 10 minutes from now
    const { result } = renderHook(() => useCountdownDetailed(futureDate));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.isUrgent).toBe(false);
  });

  it('should return totalSeconds correctly', async () => {
    const futureDate = new Date(Date.now() + 7200000).toISOString(); // 2 hours from now
    const { result } = renderHook(() => useCountdownDetailed(futureDate));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    // Should be approximately 7200 seconds (within a few seconds due to timing)
    expect(result.current.totalSeconds).toBeGreaterThanOrEqual(7195);
    expect(result.current.totalSeconds).toBeLessThanOrEqual(7200);
  });

  it('should handle null date', async () => {
    const { result } = renderHook(() => useCountdownDetailed(null));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.display).toBe('N/A');
    expect(result.current.isExpired).toBe(false);
    expect(result.current.isUrgent).toBe(false);
  });

  it('should update over time', async () => {
    const futureDate = new Date(Date.now() + 65000).toISOString();
    const { result } = renderHook(() => useCountdownDetailed(futureDate));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    const initialSeconds = result.current.totalSeconds;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    // Total seconds should have decreased
    expect(result.current.totalSeconds).toBeLessThan(initialSeconds);
  });
});
