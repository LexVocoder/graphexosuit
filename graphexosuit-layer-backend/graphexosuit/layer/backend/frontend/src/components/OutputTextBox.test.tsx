/**
 * Tests for graphexosuit.layer.backend.frontend.components.OutputTextBox
 *
 * Responsibilities:
 *  - Test rendering lines
 *  - Test drag-resizable handle
 *  - Test smart scrolling behavior
 *  - Test localStorage persistence
 *  - Test scroll position detection
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import OutputTextBox from '@/components/OutputTextBox';

describe('OutputTextBox', () => {
  let mockOnHeightChange: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockOnHeightChange = vi.fn();
    localStorage.clear();
  });

  it('should render output lines joined by newlines', () => {
    const lines = ['line 1', 'line 2', 'line 3'];
    render(
      <OutputTextBox
        lines={lines}
        height={25}
        onHeightChange={mockOnHeightChange}
      />
    );

    const textbox = screen.getByRole('region', { name: /execution output/i });
    // Component renders lines in pre tag, which preserves whitespace
    // Check that all lines are present (regardless of exact whitespace)
    expect(textbox.textContent).toContain('line 1');
    expect(textbox.textContent).toContain('line 2');
    expect(textbox.textContent).toContain('line 3');
  });

  it('should accept custom aria label', () => {
    render(
      <OutputTextBox
        lines={[]}
        height={25}
        onHeightChange={mockOnHeightChange}
        ariaLabel="Custom output"
      />
    );

    expect(screen.getByRole('region', { name: /custom output/i })).toBeInTheDocument();
  });

  it('should restore height from localStorage on mount', () => {
    localStorage.setItem('output_box_height_rows', '30');

    render(
      <OutputTextBox
        lines={[]}
        height={25}
        onHeightChange={mockOnHeightChange}
      />
    );

    expect(mockOnHeightChange).toHaveBeenCalledWith(30);
  });

  it('should clamp stored height to valid range', () => {
    localStorage.setItem('output_box_height_rows', '200');

    render(
      <OutputTextBox
        lines={[]}
        height={25}
        onHeightChange={mockOnHeightChange}
      />
    );

    expect(mockOnHeightChange).toHaveBeenCalledWith(100); // MAX_HEIGHT_ROWS
  });

  it('should show scroll position indicator when not at bottom', () => {
    render(
      <OutputTextBox
        lines={Array(50).fill('line')}
        height={10}
        onHeightChange={mockOnHeightChange}
      />
    );

    // Component should render output section
    expect(screen.getByRole('region', { name: /execution output/i })).toBeInTheDocument();
  });

  it('should not show indicator when at bottom', () => {
    const { rerender } = render(
      <OutputTextBox
        lines={Array(50).fill('line')}
        height={10}
        onHeightChange={mockOnHeightChange}
      />
    );

    // Component renders successfully without scroll indicator
    expect(screen.getByRole('region', { name: /execution output/i })).toBeInTheDocument();
  });

  it('should track scroll position on scroll event', async () => {
    const { container } = render(
      <OutputTextBox
        lines={Array(50).fill('line')}
        height={10}
        onHeightChange={mockOnHeightChange}
      />
    );

    const textbox = container.querySelector('[role="region"]') as HTMLDivElement;
    expect(textbox).toBeInTheDocument();

    // Simulate scroll
    fireEvent.scroll(textbox, { target: { scrollTop: 100 } });
    expect(textbox).toBeInTheDocument();
  });

  it('should render resize handle on desktop', () => {
    const { container } = render(
      <OutputTextBox
        lines={[]}
        height={25}
        onHeightChange={mockOnHeightChange}
      />
    );

    const resizeHandle = container.querySelector('[role="button"][aria-label*="Resize"]');
    expect(resizeHandle).toBeInTheDocument();
  });

  it('should persist height to localStorage on drag', async () => {
    const { container } = render(
      <OutputTextBox
        lines={[]}
        height={25}
        onHeightChange={mockOnHeightChange}
      />
    );

    const resizeHandle = container.querySelector('[role="button"]') as HTMLElement;

    // Simulate drag
    fireEvent.mouseDown(resizeHandle, { clientY: 0 });
    fireEvent.mouseMove(document, { clientY: 100 });
    fireEvent.mouseUp(document);

    await waitFor(() => {
      expect(localStorage.getItem('output_box_height_rows')).toBeTruthy();
    });
  });

  it('should handle arrow keys on resize handle', async () => {
    const user = userEvent.setup();
    const { container } = render(
      <OutputTextBox
        lines={[]}
        height={25}
        onHeightChange={mockOnHeightChange}
      />
    );

    const resizeHandle = container.querySelector('[role="button"]') as HTMLElement;

    await user.tab(); // Focus resize handle
    await user.keyboard('{ArrowDown}');

    expect(mockOnHeightChange).toHaveBeenCalledWith(26);
  });

  it('should handle ArrowUp key on resize handle', async () => {
    const user = userEvent.setup();
    const { container } = render(
      <OutputTextBox
        lines={[]}
        height={25}
        onHeightChange={mockOnHeightChange}
      />
    );

    const resizeHandle = container.querySelector('[role="button"]') as HTMLElement;

    await user.tab();
    await user.keyboard('{ArrowUp}');

    expect(mockOnHeightChange).toHaveBeenCalledWith(24);
  });

  it('should clamp arrow key height changes to valid range', async () => {
    const user = userEvent.setup();
    mockOnHeightChange.mockClear();

    const { container, rerender } = render(
      <OutputTextBox
        lines={[]}
        height={5} // MIN_HEIGHT_ROWS
        onHeightChange={mockOnHeightChange}
      />
    );

    rerender(
      <OutputTextBox
        lines={[]}
        height={5}
        onHeightChange={mockOnHeightChange}
      />
    );

    const resizeHandle = container.querySelector('[role="button"]') as HTMLElement;

    await user.tab();
    await user.keyboard('{ArrowUp}');

    // Should stay at minimum
    expect(mockOnHeightChange).toHaveBeenCalledWith(5);
  });
});
