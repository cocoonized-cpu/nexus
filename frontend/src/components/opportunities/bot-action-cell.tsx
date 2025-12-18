'use client';

import * as TooltipPrimitive from '@radix-ui/react-tooltip';
import { Badge } from '@/components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { CheckCircle2, XCircle, Clock, Ban, Info } from 'lucide-react';

export interface BotActionDetail {
  rule: string;
  passed: boolean;
  current: string | null;
  threshold: string | null;
  message: string;
}

export interface BotAction {
  status: 'auto_trade' | 'manual_only' | 'waiting' | 'blocked';
  reason: string;
  details: BotActionDetail[];
  user_action: string | null;
  can_execute: boolean;
}

interface BotActionCellProps {
  botAction: BotAction | null | undefined;
  className?: string;
}

const STATUS_CONFIG = {
  auto_trade: {
    label: 'Auto-trade',
    color: 'bg-green-500 hover:bg-green-600',
    textColor: 'text-green-500',
    icon: CheckCircle2,
    description: 'This opportunity will be automatically executed',
  },
  manual_only: {
    label: 'Manual only',
    color: 'bg-blue-500 hover:bg-blue-600',
    textColor: 'text-blue-500',
    icon: Info,
    description: 'Available for manual execution only',
  },
  waiting: {
    label: 'Waiting',
    color: 'bg-yellow-500 hover:bg-yellow-600',
    textColor: 'text-yellow-500',
    icon: Clock,
    description: 'Temporarily blocked, waiting for conditions to change',
  },
  blocked: {
    label: 'Blocked',
    color: 'bg-red-500 hover:bg-red-600',
    textColor: 'text-red-500',
    icon: Ban,
    description: 'Cannot be executed due to configuration or rules',
  },
};

/**
 * A table cell component that displays the bot action status for an opportunity.
 * Shows a badge with the status and a tooltip with detailed rule evaluations.
 */
export function BotActionCell({ botAction, className }: BotActionCellProps) {
  if (!botAction) {
    return (
      <span className="text-muted-foreground text-sm">--</span>
    );
  }

  const config = STATUS_CONFIG[botAction.status] || STATUS_CONFIG.blocked;
  const Icon = config.icon;

  // Separate passed and failed rules
  const failedRules = botAction.details.filter(d => !d.passed);
  const passedRules = botAction.details.filter(d => d.passed);

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge
          variant="outline"
          className={cn(
            'cursor-help text-white border-none',
            config.color,
            className
          )}
        >
          <Icon className="h-3 w-3 mr-1" />
          {config.label}
        </Badge>
      </TooltipTrigger>
      <TooltipPrimitive.Portal>
        <TooltipContent
          side="left"
          className="z-[100] max-w-md p-0 bg-popover border border-border shadow-xl"
          sideOffset={8}
        >
          <div className="p-4 space-y-3">
            {/* Header */}
            <div className="border-b border-border pb-3">
              <div className={cn('font-semibold flex items-center gap-2 text-base', config.textColor)}>
                <Icon className="h-5 w-5" />
                {config.label}
              </div>
              <p className="text-sm text-muted-foreground mt-1.5">
                {botAction.reason}
              </p>
            </div>

            {/* Failed Rules (if any) */}
            {failedRules.length > 0 && (
              <div className="space-y-2">
                <div className="text-xs font-semibold text-red-500 uppercase tracking-wide">
                  Blocking Rules
                </div>
                {failedRules.map((detail, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm bg-red-500/10 rounded-md p-2">
                    <XCircle className="h-4 w-4 text-red-500 mt-0.5 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <span className="text-foreground font-medium">{detail.message}</span>
                      {detail.current && detail.threshold && (
                        <div className="text-xs text-muted-foreground mt-1">
                          Current: <span className="text-red-400">{detail.current}</span> | Required: <span className="text-green-400">{detail.threshold}</span>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Passed Rules */}
            {passedRules.length > 0 && (
              <div className="space-y-2">
                <div className="text-xs font-semibold text-green-500 uppercase tracking-wide">
                  Passed Checks
                </div>
                <div className="space-y-1">
                  {passedRules.slice(0, 5).map((detail, i) => (
                    <div key={i} className="flex items-start gap-2 text-sm">
                      <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 shrink-0" />
                      <span className="text-muted-foreground">{detail.message}</span>
                    </div>
                  ))}
                  {passedRules.length > 5 && (
                    <div className="text-xs text-muted-foreground pl-6">
                      +{passedRules.length - 5} more checks passed
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* User Action */}
            {botAction.user_action && (
              <div className="border-t border-border pt-3">
                <div className="flex items-start gap-2 text-sm bg-blue-500/10 rounded-md p-2">
                  <span className="text-blue-400 font-bold">→</span>
                  <span className="text-blue-400 font-medium">{botAction.user_action}</span>
                </div>
              </div>
            )}

            {/* Can Execute Note */}
            {!botAction.can_execute && (
              <div className="text-xs text-red-400 border-t border-border pt-3 font-medium">
                Manual execution is not available for this opportunity
              </div>
            )}
          </div>
        </TooltipContent>
      </TooltipPrimitive.Portal>
    </Tooltip>
  );
}
