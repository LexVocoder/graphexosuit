/**
 * graphexosuit.layer.backend.frontend.components.OutputTextBox
 *
 * Responsibilities:
 *  - Display monospace, word-wrapped output lines
 *  - Render scrollable text box with 95% width, 25 default rows
 *  - Provide drag-resizable handle at bottom to adjust height
 *  - Track scroll position: auto-scroll to bottom if already at bottom,
 *    preserve scroll position otherwise
 *  - Persist height to localStorage
 *  - Responsive on mobile (drag handle disabled on small screens)
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';

interface OutputTextBoxProps {
  lines: string[];
  height: number;
  onHeightChange: (height: number) => void;
  ariaLabel?: string;
}

const LINE_HEIGHT_PX = 18; // Approximate monospace line height
const MIN_HEIGHT_ROWS = 5;
const MAX_HEIGHT_ROWS = 100;
const STORAGE_KEY = 'output_box_height_rows';

/**
 * OutputTextBox component: Scrollable monospace output display with resize handle.
 *
 * Why: Display real-time execution output with user-adjustable height and smart scrolling.
 *
 * Args:
 *   lines: Array of output lines to display.
 *   height: Current height in rows.
 *   onHeightChange: Callback when user resizes (height in rows).
 *   ariaLabel: ARIA label for accessibility.
 */
function OutputTextBox({
  lines,
  height,
  onHeightChange,
  ariaLabel = 'Execution output',
}: OutputTextBoxProps) {
  const textBoxRef = useRef<HTMLDivElement>(null);
  const isResizingRef = useRef(false);
  const [isAtBottom, setIsAtBottom] = useState(true);

  /**
   * Restore height from localStorage on mount.
   */
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsedHeight = Math.max(
        MIN_HEIGHT_ROWS,
        Math.min(MAX_HEIGHT_ROWS, parseInt(stored, 10))
      );
      onHeightChange(parsedHeight);
    }
  }, [onHeightChange]);

  /**
   * Detect if scroll is at bottom (with 10px tolerance).
   */
  const checkIfAtBottom = useCallback(() => {
    if (!textBoxRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = textBoxRef.current;
    const atBottom = scrollHeight - scrollTop - clientHeight < 10;
    setIsAtBottom(atBottom);
  }, []);

  /**
   * Auto-scroll to bottom if already at bottom and new lines arrived.
   */
  useEffect(() => {
    checkIfAtBottom();

    if (isAtBottom && textBoxRef.current) {
      textBoxRef.current.scrollTop = textBoxRef.current.scrollHeight;
    }
  }, [lines, isAtBottom, checkIfAtBottom]);

  /**
   * Handle scroll event to track position.
   */
  const handleScroll = () => {
    checkIfAtBottom();
  };

  /**
   * Handle mouse down on resize handle: start drag operation.
   */
  const handleResizeMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    isResizingRef.current = true;
    const startY = e.clientY;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      if (!isResizingRef.current || !textBoxRef.current) return;

      const deltaY = moveEvent.clientY - startY;
      const newHeightPx = textBoxRef.current.clientHeight + deltaY;
      const newHeightRows = Math.round(newHeightPx / LINE_HEIGHT_PX);

      const clamped = Math.max(
        MIN_HEIGHT_ROWS,
        Math.min(MAX_HEIGHT_ROWS, newHeightRows)
      );

      onHeightChange(clamped);
      localStorage.setItem(STORAGE_KEY, clamped.toString());
    };

    const handleMouseUp = () => {
      isResizingRef.current = false;
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  };

  const heightPx = height * LINE_HEIGHT_PX;
  const content = lines.join('\n');

  return (
    <div className="space-y-2">
      {/* Output text box */}
      <div
        ref={textBoxRef}
        style={{ height: `${heightPx}px` }}
        className="output-box w-full"
        onScroll={handleScroll}
        role="region"
        aria-label={ariaLabel}
        aria-live="polite"
        aria-atomic="false"
      >
        {content}
      </div>

      {/* Resize handle - desktop only */}
      <div className="hidden sm:block">
        <div
          onMouseDown={handleResizeMouseDown}
          role="button"
          tabIndex={0}
          aria-label="Resize output box height (drag or press arrow keys)"
          className="h-1 bg-gray-300 hover:bg-blue-500 cursor-row-resize rounded-sm transition-colors"
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') {
              onHeightChange(Math.min(MAX_HEIGHT_ROWS, height + 1));
              localStorage.setItem(STORAGE_KEY, (height + 1).toString());
            } else if (e.key === 'ArrowUp') {
              onHeightChange(Math.max(MIN_HEIGHT_ROWS, height - 1));
              localStorage.setItem(STORAGE_KEY, (height - 1).toString());
            }
          }}
        />
      </div>

      {/* Scroll position indicator */}
      {!isAtBottom && (
        <div className="text-xs text-gray-500 text-center" aria-live="polite">
          ↓ New output below
        </div>
      )}
    </div>
  );
}

export default OutputTextBox;
