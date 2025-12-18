'use client';

import { Clock, AlertTriangle } from 'lucide-react';
import { useCountdownDetailed } from '@/hooks/use-countdown';
import { cn } from '@/lib/utils';

interface CountdownCellProps {
  expiresAt: string | Date | null | undefined;
  showIcon?: boolean;
  className?: string;
}

/**
 * A table cell component that displays a real-time countdown to expiration.
 * Updates every second and shows visual indicators for expired/urgent states.
 */
export function CountdownCell({ expiresAt, showIcon = true, className }: CountdownCellProps) {
  const { display, isExpired, isUrgent } = useCountdownDetailed(expiresAt);

  return (
    <div
      className={cn(
        'flex items-center gap-1 text-sm',
        isExpired && 'text-muted-foreground',
        isUrgent && !isExpired && 'text-orange-500',
        className
      )}
    >
      {showIcon && (
        isUrgent && !isExpired ? (
          <AlertTriangle className="h-3 w-3" />
        ) : (
          <Clock className="h-3 w-3" />
        )
      )}
      <span className={cn(isUrgent && !isExpired && 'font-medium')}>
        {display}
      </span>
    </div>
  );
}
