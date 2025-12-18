'use client';

import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  CheckCircle2,
  Circle,
  Loader2,
  XCircle,
  TrendingUp,
  TrendingDown,
  ArrowRight,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatPercent, formatCurrency } from '@/lib/utils';

interface ExecutionStep {
  id: string;
  label: string;
  description: string;
  status: 'pending' | 'in_progress' | 'completed' | 'error';
  errorMessage?: string;
}

interface OpportunityData {
  id: string;
  symbol: string;
  primary_exchange: string;
  hedge_exchange: string;
  primary_side: string;
  hedge_side: string;
  net_apr?: number;
  uos_score: number;
  recommended_size_usd?: number;
}

interface ExecutionResult {
  success: boolean;
  message?: string;
  data?: {
    position_id: string;
    primary: {
      exchange: string;
      side: string;
      order_id?: string;
    };
    hedge: {
      exchange: string;
      side: string;
      order_id?: string;
    };
  };
  error?: string;
}

interface ExecutionProgressModalProps {
  open: boolean;
  onClose: () => void;
  opportunity: OpportunityData | null;
  onExecute: (id: string) => Promise<ExecutionResult>;
}

const INITIAL_STEPS: ExecutionStep[] = [
  {
    id: 'validate',
    label: 'Validating Opportunity',
    description: 'Checking opportunity status and expiration',
    status: 'pending',
  },
  {
    id: 'connect_primary',
    label: 'Connecting to Primary Exchange',
    description: 'Establishing connection',
    status: 'pending',
  },
  {
    id: 'connect_hedge',
    label: 'Connecting to Hedge Exchange',
    description: 'Establishing connection',
    status: 'pending',
  },
  {
    id: 'place_primary',
    label: 'Placing Primary Order',
    description: 'Opening long/short position',
    status: 'pending',
  },
  {
    id: 'place_hedge',
    label: 'Placing Hedge Order',
    description: 'Opening opposite position',
    status: 'pending',
  },
  {
    id: 'create_position',
    label: 'Creating Position Record',
    description: 'Recording position in database',
    status: 'pending',
  },
];

export function ExecutionProgressModal({
  open,
  onClose,
  opportunity,
  onExecute,
}: ExecutionProgressModalProps) {
  const [steps, setSteps] = useState<ExecutionStep[]>(INITIAL_STEPS);
  const [isExecuting, setIsExecuting] = useState(false);
  const [executionResult, setExecutionResult] = useState<ExecutionResult | null>(null);
  const [currentStepIndex, setCurrentStepIndex] = useState(-1);

  // Reset state when modal opens with new opportunity
  useEffect(() => {
    if (open && opportunity) {
      setSteps(
        INITIAL_STEPS.map((step) => ({
          ...step,
          description: getStepDescription(step.id, opportunity),
          status: 'pending',
        }))
      );
      setIsExecuting(false);
      setExecutionResult(null);
      setCurrentStepIndex(-1);
    }
  }, [open, opportunity]);

  const getStepDescription = (stepId: string, opp: OpportunityData): string => {
    switch (stepId) {
      case 'validate':
        return `Checking ${opp.symbol} opportunity status`;
      case 'connect_primary':
        return `Connecting to ${opp.primary_exchange}`;
      case 'connect_hedge':
        return `Connecting to ${opp.hedge_exchange}`;
      case 'place_primary':
        return `Opening ${opp.primary_side} on ${opp.primary_exchange}`;
      case 'place_hedge':
        return `Opening ${opp.hedge_side} on ${opp.hedge_exchange}`;
      case 'create_position':
        return 'Recording position in database';
      default:
        return '';
    }
  };

  const updateStep = (index: number, status: ExecutionStep['status'], errorMessage?: string) => {
    setSteps((prev) =>
      prev.map((step, i) =>
        i === index ? { ...step, status, errorMessage } : step
      )
    );
  };

  const simulateProgress = async () => {
    // Simulate step-by-step progress while waiting for API
    const stepDurations = [300, 500, 500, 800, 800, 400];

    for (let i = 0; i < steps.length; i++) {
      setCurrentStepIndex(i);
      updateStep(i, 'in_progress');
      await new Promise((resolve) => setTimeout(resolve, stepDurations[i]));
    }
  };

  const handleExecute = async () => {
    if (!opportunity) return;

    setIsExecuting(true);
    setExecutionResult(null);

    // Start first step immediately
    setCurrentStepIndex(0);
    updateStep(0, 'in_progress');

    // Track which step we're on for error handling
    let completedSteps = 0;

    // Start progress simulation (non-blocking)
    const progressPromise = (async () => {
      const stepDurations = [300, 500, 500, 800, 800, 400];
      for (let i = 0; i < steps.length; i++) {
        setCurrentStepIndex(i);
        updateStep(i, 'in_progress');
        completedSteps = i;
        await new Promise((resolve) => setTimeout(resolve, stepDurations[i]));
      }
    })();

    try {
      // Execute the actual API call
      const result = await onExecute(opportunity.id);

      // Wait for progress animation to catch up
      await progressPromise;

      if (result.success) {
        // Mark all steps as completed
        setSteps((prev) =>
          prev.map((step) => ({ ...step, status: 'completed' }))
        );
        setExecutionResult(result);
      } else {
        // Find where it failed and mark steps accordingly
        const errorStep = steps.length - 1;
        setSteps((prev) =>
          prev.map((step, i) => ({
            ...step,
            status: i < errorStep ? 'completed' : i === errorStep ? 'error' : 'pending',
            errorMessage: i === errorStep ? result.error || 'Unknown error' : undefined,
          }))
        );
        setExecutionResult(result);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Execution failed';

      // Determine which step to mark as failed (use tracked step or default to first)
      const failedStep = Math.max(0, completedSteps);

      // Mark steps with proper error state
      setSteps((prev) =>
        prev.map((step, i) => ({
          ...step,
          status: i < failedStep ? 'completed' : i === failedStep ? 'error' : 'pending',
          errorMessage: i === failedStep ? errorMessage : undefined,
        }))
      );
      setExecutionResult({
        success: false,
        error: errorMessage,
      });
    } finally {
      setIsExecuting(false);
    }
  };

  const getStepIcon = (status: ExecutionStep['status']) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="h-5 w-5 text-green-500" />;
      case 'in_progress':
        return <Loader2 className="h-5 w-5 text-blue-500 animate-spin" />;
      case 'error':
        return <XCircle className="h-5 w-5 text-red-500" />;
      default:
        return <Circle className="h-5 w-5 text-muted-foreground" />;
    }
  };

  const isComplete = executionResult?.success;
  const hasError = executionResult && !executionResult.success;

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isExecuting && !isOpen && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {isComplete
              ? 'Execution Complete'
              : hasError
              ? 'Execution Failed'
              : 'Execute Opportunity'}
          </DialogTitle>
          <DialogDescription>
            {opportunity?.symbol} - Funding Rate Arbitrage
          </DialogDescription>
        </DialogHeader>

        {opportunity && (
          <div className="space-y-6 py-4">
            {/* Trade Summary */}
            <div className="rounded-lg border bg-muted/30 p-4">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="bg-green-500/10 text-green-500 border-green-500/20">
                    <TrendingUp className="h-3 w-3 mr-1" />
                    {opportunity.primary_side.toUpperCase()}
                  </Badge>
                  <span className="text-sm">{opportunity.primary_exchange}</span>
                </div>
                <ArrowRight className="h-4 w-4 text-muted-foreground" />
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="bg-red-500/10 text-red-500 border-red-500/20">
                    <TrendingDown className="h-3 w-3 mr-1" />
                    {opportunity.hedge_side.toUpperCase()}
                  </Badge>
                  <span className="text-sm">{opportunity.hedge_exchange}</span>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-4 text-sm">
                <div>
                  <div className="text-muted-foreground">Est. APR</div>
                  <div className="font-medium text-green-500">
                    {formatPercent(opportunity.net_apr || 0, 1)}
                  </div>
                </div>
                <div>
                  <div className="text-muted-foreground">UOS Score</div>
                  <div className="font-medium">{opportunity.uos_score}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Size</div>
                  <div className="font-medium">
                    {formatCurrency(opportunity.recommended_size_usd || 100)}
                    {!opportunity.recommended_size_usd && (
                      <span className="text-xs text-muted-foreground ml-1">(default)</span>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Execution Steps */}
            <div className="space-y-3">
              <div className="text-sm font-medium">Execution Progress</div>
              {steps.map((step, index) => (
                <div
                  key={step.id}
                  className={cn(
                    'flex items-start gap-3 p-3 rounded-lg transition-colors',
                    step.status === 'in_progress' && 'bg-blue-500/5 border border-blue-500/20',
                    step.status === 'completed' && 'bg-green-500/5',
                    step.status === 'error' && 'bg-red-500/5 border border-red-500/20'
                  )}
                >
                  {getStepIcon(step.status)}
                  <div className="flex-1 min-w-0">
                    <div
                      className={cn(
                        'font-medium text-sm',
                        step.status === 'pending' && 'text-muted-foreground'
                      )}
                    >
                      {step.label}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {step.errorMessage || step.description}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Success Result */}
            {isComplete && executionResult.data && (
              <div className="rounded-lg border border-green-500/20 bg-green-500/5 p-4">
                <div className="flex items-center gap-2 text-green-500 mb-2">
                  <CheckCircle2 className="h-5 w-5" />
                  <span className="font-medium">Position Opened Successfully</span>
                </div>
                <div className="text-sm text-muted-foreground space-y-1">
                  <div>Position ID: {executionResult.data.position_id.slice(0, 8)}...</div>
                  {executionResult.data.primary.order_id && (
                    <div>Primary Order: {executionResult.data.primary.order_id}</div>
                  )}
                  {executionResult.data.hedge.order_id && (
                    <div>Hedge Order: {executionResult.data.hedge.order_id}</div>
                  )}
                </div>
              </div>
            )}

            {/* Error Result */}
            {hasError && (
              <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-4">
                <div className="flex items-center gap-2 text-red-500 mb-2">
                  <XCircle className="h-5 w-5" />
                  <span className="font-medium">Execution Failed</span>
                </div>
                <div className="text-sm text-muted-foreground space-y-2">
                  {executionResult.error ? (
                    <>
                      {/* Split error message by | to show main error and status separately */}
                      {executionResult.error.split(' | ').map((part, index) => (
                        <div key={index} className={index === 0 ? 'font-medium text-red-400' : 'text-xs opacity-80'}>
                          {part}
                        </div>
                      ))}
                    </>
                  ) : (
                    'An unexpected error occurred'
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-end gap-2">
          {!isExecuting && !isComplete && !hasError && (
            <>
              <Button variant="outline" onClick={onClose}>
                Cancel
              </Button>
              <Button onClick={handleExecute}>
                Start Execution
              </Button>
            </>
          )}
          {isExecuting && (
            <Button disabled>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              Executing...
            </Button>
          )}
          {(isComplete || hasError) && (
            <Button onClick={onClose}>
              {isComplete ? 'Done' : 'Close'}
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
