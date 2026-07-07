/**
 * Tests for graphexosuit.layer.backend.frontend.context.AppContext
 *
 * Responsibilities:
 *  - Test AppProvider wraps children
 *  - Test polling interval state management
 *  - Test updatePollingInterval clamping
 *  - Test error on hook usage outside provider
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AppProvider, useAppContext } from '@/context/AppContext';

function TestComponent() {
  const { pollingInterval, updatePollingInterval } = useAppContext();
  return (
    <div>
      <span data-testid="polling-interval">{pollingInterval}</span>
      <button
        onClick={() => updatePollingInterval(500)}
        data-testid="set-interval-500"
      >
        Set 500
      </button>
      <button
        onClick={() => updatePollingInterval(2000)}
        data-testid="set-interval-2000"
      >
        Set 2000
      </button>
      <button
        onClick={() => updatePollingInterval(100)}
        data-testid="set-interval-100"
      >
        Set 100
      </button>
      <button
        onClick={() => updatePollingInterval(15000)}
        data-testid="set-interval-15000"
      >
        Set 15000
      </button>
    </div>
  );
}

describe('AppContext', () => {
  it('should provide initial polling interval of 1000ms', () => {
    render(
      <AppProvider>
        <TestComponent />
      </AppProvider>
    );

    expect(screen.getByTestId('polling-interval')).toHaveTextContent('1000');
  });

  it('should allow updating polling interval', async () => {
    const user = userEvent.setup();
    render(
      <AppProvider>
        <TestComponent />
      </AppProvider>
    );

    await user.click(screen.getByTestId('set-interval-500'));
    expect(screen.getByTestId('polling-interval')).toHaveTextContent('500');

    await user.click(screen.getByTestId('set-interval-2000'));
    expect(screen.getByTestId('polling-interval')).toHaveTextContent('2000');
  });

  it('should clamp interval to min 250ms', async () => {
    const user = userEvent.setup();
    render(
      <AppProvider>
        <TestComponent />
      </AppProvider>
    );

    await user.click(screen.getByTestId('set-interval-100'));
    expect(screen.getByTestId('polling-interval')).toHaveTextContent('250');
  });

  it('should clamp interval to max 10000ms', async () => {
    const user = userEvent.setup();
    render(
      <AppProvider>
        <TestComponent />
      </AppProvider>
    );

    await user.click(screen.getByTestId('set-interval-15000'));
    expect(screen.getByTestId('polling-interval')).toHaveTextContent('10000');
  });

  it('should throw error when hook used outside provider', () => {
    // Suppress console.error for this test
    const originalError = console.error;
    console.error = () => {};

    expect(() => {
      render(<TestComponent />);
    }).toThrow('useAppContext must be used within AppProvider');

    console.error = originalError;
  });
});
