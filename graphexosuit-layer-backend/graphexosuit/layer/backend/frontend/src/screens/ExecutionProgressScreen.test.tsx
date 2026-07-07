/**
 * Tests for graphexosuit.layer.backend.frontend.screens.ExecutionProgressScreen
 *
 * Responsibilities:
 *  - Test rendering of different execution statuses
 *  - Test interrupt handling UI
 *  - Test error/result display
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ExecutionProgressScreen from '@/screens/ExecutionProgressScreen';
import * as apiClient from '@/api/client';
import { AppProvider } from '@/context/AppContext';
import { ExecutionData } from '@/types/api';

vi.mock('@/api/client');
vi.mock('@monaco-editor/react', () => ({
  default: vi.fn(({ value, onChange }) => (
    <textarea
      data-testid="json-editor"
      value={value}
      onChange={(e) => onChange?.(e.target.value)}
    />
  )),
}));

describe('ExecutionProgressScreen', () => {
  const mockOnResetToPreRun = vi.fn();
  const threadId = 'test-thread-123';

  beforeEach(() => {
    mockOnResetToPreRun.mockClear();
    vi.clearAllMocks();
  });

  const renderScreen = () => {
    return render(
      <AppProvider>
        <ExecutionProgressScreen
          threadId={threadId}
          onResetToPreRun={mockOnResetToPreRun}
        />
      </AppProvider>
    );
  };

  it('should render header with thread ID', async () => {
    vi.mocked(apiClient.pollThread).mockResolvedValueOnce({
      status: 'running',
      output_lines: [],
      created_at: '2024-01-01T00:00:00Z',
    });

    renderScreen();

    await waitFor(() => {
      expect(screen.getByText('Execution Progress')).toBeInTheDocument();
      expect(screen.getByText(new RegExp(threadId))).toBeInTheDocument();
    });
  });

  it('should display running status badge', async () => {
    vi.mocked(apiClient.pollThread).mockResolvedValueOnce({
      status: 'running',
      output_lines: [],
      created_at: '2024-01-01T00:00:00Z',
    });

    renderScreen();

    await waitFor(() => {
      expect(screen.getByText('Running')).toBeInTheDocument();
    });
  });

  it('should display polling interval control', async () => {
    vi.mocked(apiClient.pollThread).mockResolvedValueOnce({
      status: 'running',
      output_lines: [],
      created_at: '2024-01-01T00:00:00Z',
    });

    renderScreen();

    await waitFor(() => {
      expect(screen.getByLabelText(/polling interval slider/i)).toBeInTheDocument();
    });
  });

  it('should display output lines', async () => {
    const outputLines = ['line 1', 'line 2', 'line 3'];
    vi.mocked(apiClient.pollThread).mockResolvedValueOnce({
      status: 'running',
      output_lines: outputLines,
      created_at: '2024-01-01T00:00:00Z',
    });

    renderScreen();

    await waitFor(() => {
      const outputBox = screen.getByRole('region', {
        name: /execution output/i,
      });
      expect(outputBox.textContent).toContain('line 1');
      expect(outputBox.textContent).toContain('line 2');
      expect(outputBox.textContent).toContain('line 3');
    });
  });

  it('should display paused status with interrupt prompt', async () => {
    const interruptData: ExecutionData = {
      status: 'paused',
      output_lines: [],
      created_at: '2024-01-01T00:00:00Z',
      result: {
        thread_id: threadId,
        checkpoint_id: 'ckpt123',
        interrupt_value: {
          message: 'Choose a flavor',
          options: [
            { label: 'Chocolate', payload: { flavor: 'chocolate' } },
            { label: 'Vanilla', payload: { flavor: 'vanilla' } },
          ],
        },
      },
    };

    vi.mocked(apiClient.pollThread).mockResolvedValueOnce(interruptData);

    renderScreen();

    await waitFor(() => {
      expect(screen.getByText('Graph Paused')).toBeInTheDocument();
      expect(screen.getByText('Choose a flavor')).toBeInTheDocument();
      expect(screen.getByLabelText('Chocolate')).toBeInTheDocument();
      expect(screen.getByLabelText('Vanilla')).toBeInTheDocument();
    });
  });

  it('should allow selecting interrupt option', async () => {
    const user = userEvent.setup();
    const interruptData: ExecutionData = {
      status: 'paused',
      output_lines: [],
      created_at: '2024-01-01T00:00:00Z',
      result: {
        thread_id: threadId,
        checkpoint_id: 'ckpt123',
        interrupt_value: {
          message: 'Choose flavor',
          options: [{ label: 'Chocolate', payload: { flavor: 'chocolate' } }],
        },
      },
    };

    vi.mocked(apiClient.pollThread).mockResolvedValueOnce(interruptData);

    renderScreen();

    await waitFor(() => {
      expect(screen.getByLabelText('Chocolate')).toBeInTheDocument();
    });

    await user.click(screen.getByLabelText('Chocolate'));

    await waitFor(() => {
      expect(screen.getByText('Edit Resume Payload')).toBeInTheDocument();
    });
  });

  it('should call resumeThread on Resume button click', async () => {
    const user = userEvent.setup();
    const interruptData: ExecutionData = {
      status: 'paused',
      output_lines: [],
      created_at: '2024-01-01T00:00:00Z',
      result: {
        thread_id: threadId,
        checkpoint_id: 'ckpt123',
        interrupt_value: {
          message: 'Choose',
          options: [{ label: 'Option', payload: { key: 'value' } }],
        },
      },
    };

    vi.mocked(apiClient.pollThread).mockResolvedValueOnce(interruptData);
    vi.mocked(apiClient.resumeThread).mockResolvedValueOnce({
      thread_id: threadId,
      poll_url: `/thread/${threadId}`,
    });

    renderScreen();

    await waitFor(() => {
      expect(screen.getByLabelText('Option')).toBeInTheDocument();
    });

    await user.click(screen.getByLabelText('Option'));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /resume/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /resume/i }));

    await waitFor(() => {
      expect(apiClient.resumeThread).toHaveBeenCalledWith(
        threadId,
        'ckpt123',
        { key: 'value' }
      );
    });
  });

  it('should display error status with error message', async () => {
    const errorData: ExecutionData = {
      status: 'error',
      output_lines: [],
      created_at: '2024-01-01T00:00:00Z',
      error: {
        message: 'Node execution failed',
        checkpoint_id: 'ckpt123',
        thread_id: threadId,
      },
    };

    vi.mocked(apiClient.pollThread).mockResolvedValueOnce(errorData);

    renderScreen();

    await waitFor(() => {
      expect(screen.getByText('Node execution failed')).toBeInTheDocument();
    });
  });

  it('should display completed status with result', async () => {
    const completedData: ExecutionData = {
      status: 'completed',
      output_lines: [],
      created_at: '2024-01-01T00:00:00Z',
      result: {
        thread_id: threadId,
        final_result: { outcome: 'success', data: [1, 2, 3] },
      },
    };

    vi.mocked(apiClient.pollThread).mockResolvedValueOnce(completedData);

    renderScreen();

    await waitFor(() => {
      expect(screen.getByText('Execution Completed')).toBeInTheDocument();
      expect(screen.getByText(/success/)).toBeInTheDocument();
    });
  });

  it('should display Run Again button on completion', async () => {
    const completedData: ExecutionData = {
      status: 'completed',
      output_lines: [],
      created_at: '2024-01-01T00:00:00Z',
      result: {
        thread_id: threadId,
        final_result: { result: 'done' },
      },
    };

    vi.mocked(apiClient.pollThread).mockResolvedValueOnce(completedData);

    renderScreen();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /return to pre-run screen/i })).toBeInTheDocument();
    });
  });

  it('should call onResetToPreRun on Start Over button', async () => {
    const user = userEvent.setup();
    const completedData: ExecutionData = {
      status: 'completed',
      output_lines: [],
      created_at: '2024-01-01T00:00:00Z',
      result: {
        thread_id: threadId,
        final_result: { result: 'done' },
      },
    };

    vi.mocked(apiClient.pollThread).mockResolvedValueOnce(completedData);

    renderScreen();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /return to pre-run screen/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /return to pre-run screen/i }));

    expect(mockOnResetToPreRun).toHaveBeenCalled();
  });
});