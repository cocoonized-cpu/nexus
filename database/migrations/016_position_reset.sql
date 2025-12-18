-- Migration 016: Position Reset Script
-- Purpose: Provide a safe script to reset orphan/stuck positions in the database
-- This migration marks all active positions as closed and logs the reset action
-- IMPORTANT: This is a data cleanup migration - run only when intentional reset is needed

-- Begin transaction for atomicity
BEGIN;

-- Count positions that will be affected (for audit log)
DO $$
DECLARE
    affected_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO affected_count
    FROM positions.active
    WHERE status IN ('active', 'opening', 'closing', 'exiting', 'pending');

    -- Log the count
    RAISE NOTICE 'Resetting % positions', affected_count;

    -- Only proceed if there are positions to reset
    IF affected_count > 0 THEN
        -- Update all non-closed positions to closed status
        UPDATE positions.active
        SET
            status = 'closed',
            exit_reason = 'manual_reset',
            closed_at = NOW(),
            updated_at = NOW(),
            current_activity = NULL,
            activity_description = 'Position closed via manual reset migration',
            blockers = '[]'::jsonb
        WHERE status IN ('active', 'opening', 'closing', 'exiting', 'pending');

        -- Log the reset in activity_events
        INSERT INTO audit.activity_events (
            service,
            category,
            event_type,
            severity,
            message,
            details,
            created_at
        ) VALUES (
            'migration',
            'system',
            'position_reset',
            'warning',
            format('All positions reset via migration script. %s positions affected.', affected_count),
            jsonb_build_object(
                'reset_at', NOW()::text,
                'affected_count', affected_count,
                'reset_reason', 'manual_reset',
                'migration', '016_position_reset'
            ),
            NOW()
        );

        -- Also log a position event for each affected position
        INSERT INTO positions.events (
            position_id,
            event_type,
            data,
            created_at
        )
        SELECT
            id,
            'position_reset',
            jsonb_build_object(
                'previous_status', status,
                'reset_reason', 'manual_reset',
                'reset_at', NOW()::text
            ),
            NOW()
        FROM positions.active
        WHERE status = 'closed' AND exit_reason = 'manual_reset';

        RAISE NOTICE 'Successfully reset % positions', affected_count;
    ELSE
        RAISE NOTICE 'No positions to reset';
    END IF;
END $$;

COMMIT;

-- Verify the reset
DO $$
DECLARE
    remaining_active INTEGER;
BEGIN
    SELECT COUNT(*) INTO remaining_active
    FROM positions.active
    WHERE status IN ('active', 'opening', 'closing', 'exiting', 'pending');

    IF remaining_active > 0 THEN
        RAISE WARNING 'There are still % active positions after reset', remaining_active;
    ELSE
        RAISE NOTICE 'Position reset complete. All positions are now closed.';
    END IF;
END $$;
