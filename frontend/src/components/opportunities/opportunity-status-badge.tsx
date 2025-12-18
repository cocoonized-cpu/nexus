'use client';

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import {
  CheckCircle2,
  Clock,
  AlertCircle,
  XCircle,
  Loader2,
  Zap,
} from 'lucide-react';

type OpportunityStatus =
  | 'detected'
  | 'validated'
  | 'scored'
  | 'allocated'
  | 'executing'
  | 'executed'
  | 'expired'
  | 'rejected';

interface OpportunityStatusBadgeProps {
  status: string;
  className?: string;
  showIcon?: boolean;
}

const STATUS_CONFIG: Record<OpportunityStatus, {
  label: string;
  variant: 'default' | 'secondary' | 'outline' | 'destructive';
  className: string;
  Icon: typeof CheckCircle2;
}> = {
  detected: {
    label: 'Detected',
    variant: 'outline',
    className: 'border-blue-500 text-blue-500',
    Icon: Zap,
  },
  validated: {
    label: 'Validated',
    variant: 'outline',
    className: 'border-cyan-500 text-cyan-500',
    Icon: CheckCircle2,
  },
  scored: {
    label: 'Scored',
    variant: 'outline',
    className: 'border-purple-500 text-purple-500',
    Icon: CheckCircle2,
  },
  allocated: {
    label: 'Allocated',
    variant: 'outline',
    className: 'border-yellow-500 text-yellow-500',
    Icon: Clock,
  },
  executing: {
    label: 'Executing',
    variant: 'outline',
    className: 'border-orange-500 text-orange-500',
    Icon: Loader2,
  },
  executed: {
    label: 'Executed',
    variant: 'outline',
    className: 'border-green-500 text-green-500',
    Icon: CheckCircle2,
  },
  expired: {
    label: 'Expired',
    variant: 'outline',
    className: 'border-muted-foreground text-muted-foreground',
    Icon: Clock,
  },
  rejected: {
    label: 'Rejected',
    variant: 'outline',
    className: 'border-red-500 text-red-500',
    Icon: XCircle,
  },
};

export function OpportunityStatusBadge({
  status,
  className,
  showIcon = false,
}: OpportunityStatusBadgeProps) {
  const config = STATUS_CONFIG[status as OpportunityStatus] || STATUS_CONFIG.detected;
  const { label, variant, className: statusClassName, Icon } = config;

  return (
    <Badge
      variant={variant}
      className={cn(statusClassName, 'gap-1', className)}
    >
      {showIcon && (
        <Icon
          className={cn(
            'h-3 w-3',
            status === 'executing' && 'animate-spin'
          )}
        />
      )}
      {label}
    </Badge>
  );
}

/**
 * Determines the general category of an opportunity status
 */
export function getStatusCategory(status: string): 'open' | 'closed' | 'pending' {
  switch (status) {
    case 'detected':
    case 'validated':
    case 'scored':
      return 'open';
    case 'allocated':
    case 'executing':
      return 'pending';
    case 'executed':
    case 'expired':
    case 'rejected':
      return 'closed';
    default:
      return 'open';
  }
}
