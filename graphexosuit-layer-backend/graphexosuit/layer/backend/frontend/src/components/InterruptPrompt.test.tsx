/**
 * Tests for graphexosuit.layer.backend.frontend.components.InterruptPrompt
 *
 * Responsibilities:
 *  - Test interrupt message display
 *  - Test option rendering
 *  - Test option selection
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import InterruptPrompt from '@/components/InterruptPrompt';
import { StandardizedInterrupt, InterruptOption } from '@/types/api';

describe('InterruptPrompt', () => {
  const mockOnSelectOption = vi.fn();

  const interrupt: StandardizedInterrupt = {
    message: 'Choose an option',
    options: [
      { label: 'Option 1', payload: { value: 1 } },
      { label: 'Option 2', payload: { value: 2 } },
    ],
  };

  it('should display interrupt message', () => {
    render(
      <InterruptPrompt
        interrupt={interrupt}
        selectedOption={null}
        onSelectOption={mockOnSelectOption}
      />
    );

    expect(screen.getByText('Graph Paused')).toBeInTheDocument();
    expect(screen.getByText('Choose an option')).toBeInTheDocument();
  });

  it('should render all interrupt options', () => {
    render(
      <InterruptPrompt
        interrupt={interrupt}
        selectedOption={null}
        onSelectOption={mockOnSelectOption}
      />
    );

    expect(screen.getByLabelText('Option 1')).toBeInTheDocument();
    expect(screen.getByLabelText('Option 2')).toBeInTheDocument();
  });

  it('should call onSelectOption when option clicked', async () => {
    const user = userEvent.setup();
    render(
      <InterruptPrompt
        interrupt={interrupt}
        selectedOption={null}
        onSelectOption={mockOnSelectOption}
      />
    );

    await user.click(screen.getByLabelText('Option 1'));
    expect(mockOnSelectOption).toHaveBeenCalledWith(interrupt.options[0]);
  });

  it('should show selected option as checked', () => {
    const selectedOption: InterruptOption = interrupt.options[0];
    render(
      <InterruptPrompt
        interrupt={interrupt}
        selectedOption={selectedOption}
        onSelectOption={mockOnSelectOption}
      />
    );

    const radio1 = screen.getByLabelText('Option 1') as HTMLInputElement;
    const radio2 = screen.getByLabelText('Option 2') as HTMLInputElement;

    expect(radio1.checked).toBe(true);
    expect(radio2.checked).toBe(false);
  });

  it('should handle multiple option selections', async () => {
    const user = userEvent.setup();
    render(
      <InterruptPrompt
        interrupt={interrupt}
        selectedOption={null}
        onSelectOption={mockOnSelectOption}
      />
    );

    await user.click(screen.getByLabelText('Option 1'));
    expect(mockOnSelectOption).toHaveBeenCalledWith(interrupt.options[0]);

    await user.click(screen.getByLabelText('Option 2'));
    expect(mockOnSelectOption).toHaveBeenCalledWith(interrupt.options[1]);

    expect(mockOnSelectOption).toHaveBeenCalledTimes(2);
  });

  it('should be keyboard accessible', async () => {
    const user = userEvent.setup();
    render(
      <InterruptPrompt
        interrupt={interrupt}
        selectedOption={null}
        onSelectOption={mockOnSelectOption}
      />
    );

    await user.tab();
    await user.keyboard(' '); // Space to select

    expect(mockOnSelectOption).toHaveBeenCalled();
  });
});
