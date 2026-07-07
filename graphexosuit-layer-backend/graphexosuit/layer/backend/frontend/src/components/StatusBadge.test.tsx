/**
 * Tests for graphexosuit.layer.backend.frontend.components.StatusBadge
 *
 * Responsibilities:
 *  - Test status badge rendering for each status
 *  - Test icon and label display
 *  - Test accessibility attributes
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import StatusBadge from '@/components/StatusBadge';
import { ExecutionStatus } from '@/types/api';

describe('StatusBadge', () => {
  it('should display running status', () => {
    render(<StatusBadge status="running" />);

    expect(screen.getByText('Running')).toBeInTheDocument();
    expect(screen.getByText('⟳')).toBeInTheDocument();
  });

  it('should display paused status', () => {
    render(<StatusBadge status="paused" />);

    expect(screen.getByText('Paused')).toBeInTheDocument();
    expect(screen.getByText('⏸')).toBeInTheDocument();
  });

  it('should display completed status', () => {
    render(<StatusBadge status="completed" />);

    expect(screen.getByText('Completed')).toBeInTheDocument();
    expect(screen.getByText('✓')).toBeInTheDocument();
  });

  it('should display error status', () => {
    render(<StatusBadge status="error" />);

    expect(screen.getByText('Error')).toBeInTheDocument();
    expect(screen.getByText('✕')).toBeInTheDocument();
  });

  it('should have correct CSS classes for each status', () => {
    const statuses: ExecutionStatus[] = [
      'running',
      'paused',
      'completed',
      'error',
    ];

    for (const status of statuses) {
      const { container } = render(<StatusBadge status={status} />);
      const badge = container.querySelector('[role="status"]');
      expect(badge).toHaveClass(`badge-${status}`);
    }
  });

  it('should have status role for screen readers', () => {
    render(<StatusBadge status="running" />);

    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('should hide icon from screen readers', () => {
    render(<StatusBadge status="running" />);

    expect(screen.getByText('⟳')).toHaveAttribute('aria-hidden', 'true');
  });
});
