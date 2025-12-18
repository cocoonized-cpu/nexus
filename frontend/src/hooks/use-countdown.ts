'use client';

import { useState, useEffect } from 'react';

/**
 * Hook that calculates and updates time remaining until a target date.
 * Updates every second to provide real-time countdown.
 *
 * @param targetDate - ISO string or Date representing the expiration time
 * @returns Formatted time remaining string (e.g., "2h 30m", "45m", "Expired")
 */
export function useCountdown(targetDate: string | Date | null | undefined): string {
  const [timeRemaining, setTimeRemaining] = useState<string>('');

  useEffect(() => {
    if (!targetDate) {
      setTimeRemaining('N/A');
      return;
    }

    const calculate = (): string => {
      // Parse date - if no timezone specified, treat as UTC
      let target: Date;
      if (typeof targetDate === 'string') {
        // If no timezone suffix, append Z to treat as UTC
        const dateStr = targetDate.endsWith('Z') || targetDate.includes('+') || targetDate.includes('-', 10)
          ? targetDate
          : targetDate + 'Z';
        target = new Date(dateStr);
      } else {
        target = targetDate;
      }
      const now = Date.now();
      const diff = target.getTime() - now;

      if (diff <= 0) return 'Expired';

      const totalSeconds = Math.floor(diff / 1000);
      const totalMinutes = Math.floor(totalSeconds / 60);
      const hours = Math.floor(totalMinutes / 60);
      const minutes = totalMinutes % 60;
      const seconds = totalSeconds % 60;

      if (hours > 0) {
        return `${hours}h ${minutes}m`;
      }
      if (minutes > 0) {
        return `${minutes}m ${seconds}s`;
      }
      return `${seconds}s`;
    };

    // Set initial value
    setTimeRemaining(calculate());

    // Update every second
    const interval = setInterval(() => {
      setTimeRemaining(calculate());
    }, 1000);

    return () => clearInterval(interval);
  }, [targetDate]);

  return timeRemaining;
}

/**
 * Hook variant that returns more detailed countdown information
 */
export function useCountdownDetailed(targetDate: string | Date | null | undefined): {
  display: string;
  isExpired: boolean;
  isUrgent: boolean;
  totalSeconds: number;
} {
  const [state, setState] = useState({
    display: '',
    isExpired: false,
    isUrgent: false,
    totalSeconds: 0,
  });

  useEffect(() => {
    if (!targetDate) {
      setState({
        display: 'N/A',
        isExpired: false,
        isUrgent: false,
        totalSeconds: 0,
      });
      return;
    }

    const calculate = () => {
      // Parse date - if no timezone specified, treat as UTC
      let target: Date;
      if (typeof targetDate === 'string') {
        // If no timezone suffix, append Z to treat as UTC
        const dateStr = targetDate.endsWith('Z') || targetDate.includes('+') || targetDate.includes('-', 10)
          ? targetDate
          : targetDate + 'Z';
        target = new Date(dateStr);
      } else {
        target = targetDate;
      }
      const now = Date.now();
      const diff = target.getTime() - now;

      if (diff <= 0) {
        return {
          display: 'Expired',
          isExpired: true,
          isUrgent: false,
          totalSeconds: 0,
        };
      }

      const totalSeconds = Math.floor(diff / 1000);
      const totalMinutes = Math.floor(totalSeconds / 60);
      const hours = Math.floor(totalMinutes / 60);
      const minutes = totalMinutes % 60;
      const seconds = totalSeconds % 60;

      // Urgent if less than 5 minutes remaining
      const isUrgent = totalMinutes < 5;

      let display: string;
      if (hours > 0) {
        display = `${hours}h ${minutes}m`;
      } else if (minutes > 0) {
        display = `${minutes}m ${seconds}s`;
      } else {
        display = `${seconds}s`;
      }

      return {
        display,
        isExpired: false,
        isUrgent,
        totalSeconds,
      };
    };

    setState(calculate());

    const interval = setInterval(() => {
      setState(calculate());
    }, 1000);

    return () => clearInterval(interval);
  }, [targetDate]);

  return state;
}
