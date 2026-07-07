/**
 * graphexosuit.layer.backend.frontend.components.StatusBadge
 *
 * Responsibilities:
 *  - Display execution status with visual indicator
 *  - Color-coded badge for running, paused, completed, error states
 *  - Accessible aria-live region for screen readers
 */

import React from 'react';
import { ExecutionStatus } from '@/types/api';

interface StatusBadgeProps {
  status: ExecutionStatus;
}

/**
 * Get display text and CSS class for status.
 */
function getStatusDisplay(status: ExecutionStatus): {
  label: string;
  className: string;
  icon: string;
} {
  switch (status) {
    case 'running':
      return {
        label: 'Running',
        className: 'badge-running',
        icon: '▶',
      };
    case 'paused':
      return {
        label: 'Paused',
        className: 'badge-paused',
        icon: '⏸',
      };
    case 'completed':
      return {
        label: 'Completed',
        className: 'badge-completed',
        icon: '✓',
      };
    case 'error':
      return {
        label: 'Error',
        className: 'badge-error',
        icon: '✕',
      };
    default:
      return {
        label: 'Unknown',
        className: 'badge-status bg-gray-100 text-gray-800',
        icon: '?',
      };
  }
}

/**
 * StatusBadge component: Visual indicator of execution status.
 *
 * Why: Give user at-a-glance view of current execution state.
 *
 * Args:
 *   status: Current execution status.
 */
function StatusBadge({ status }: StatusBadgeProps) {
  const { label, className, icon } = getStatusDisplay(status);

  return (
    <div
      className={`${className} flex items-center gap-2`}
      role="status"
      aria-live="polite"
    >
      <span aria-hidden="true">{icon}</span>
      <span>{label}</span>
    </div>
  );
}

export default StatusBadge;
