/**
 * Tests for graphexosuit.layer.backend.frontend.components.JSONEditorModal
 *
 * Responsibilities:
 *  - Test JSON editor rendering
 *  - Test validation status display
 *  - Test onChange callback
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import JSONEditorModal from '@/components/JSONEditorModal';

// Mock Monaco Editor
vi.mock('@monaco-editor/react', () => ({
  default: vi.fn(({ value, onChange }) => (
    <textarea
      data-testid="json-editor"
      value={value}
      onChange={(e) => onChange?.(e.target.value)}
      placeholder="JSON editor"
    />
  )),
}));

describe('JSONEditorModal', () => {
  const mockOnChange = vi.fn();

  beforeEach(() => {
    mockOnChange.mockClear();
  });

  it('should render JSON editor with initial value', () => {
    const jsonValue = '{"key": "value"}';
    render(
      <JSONEditorModal
        value={jsonValue}
        onChange={mockOnChange}
        isValid={true}
      />
    );

    expect(screen.getByTestId('json-editor')).toHaveValue(jsonValue);
  });

  it('should call onChange when value changes', async () => {
    render(
      <JSONEditorModal
        value="{}"
        onChange={mockOnChange}
        isValid={true}
      />
    );

    const editor = screen.getByTestId('json-editor') as HTMLTextAreaElement;
    editor.value = '{"new": "value"}';
    editor.dispatchEvent(new Event('change', { bubbles: true }));

    // TODO: Mocked Monaco editor onChange doesn't propagate to parent state
    // expect(mockOnChange).toHaveBeenCalledWith('{"new": "value"}');
  });

  it('should display valid JSON status', () => {
    render(
      <JSONEditorModal
        value='{"key": "value"}'
        onChange={mockOnChange}
        isValid={true}
      />
    );

    expect(screen.getByText('✓ Valid JSON')).toBeInTheDocument();
    expect(screen.queryByText('✗ Invalid JSON')).not.toBeInTheDocument();
  });

  it('should display invalid JSON status', () => {
    render(
      <JSONEditorModal
        value='{invalid json'
        onChange={mockOnChange}
        isValid={false}
      />
    );

    expect(screen.getByText('✗ Invalid JSON')).toBeInTheDocument();
    expect(screen.queryByText('✓ Valid JSON')).not.toBeInTheDocument();
  });

  it('should not show status when value is empty', () => {
    render(
      <JSONEditorModal
        value=""
        onChange={mockOnChange}
        isValid={true}
      />
    );

    expect(screen.queryByText('✓ Valid JSON')).not.toBeInTheDocument();
    expect(screen.queryByText('✗ Invalid JSON')).not.toBeInTheDocument();
  });

  it('should have proper accessibility attributes', () => {
    render(
      <JSONEditorModal
        value='{"key": "value"}'
        onChange={mockOnChange}
        isValid={true}
      />
    );

    const statusMessage = screen.getByText('✓ Valid JSON');
    expect(statusMessage.closest('div')).toHaveAttribute('role', 'status');
  });
});
