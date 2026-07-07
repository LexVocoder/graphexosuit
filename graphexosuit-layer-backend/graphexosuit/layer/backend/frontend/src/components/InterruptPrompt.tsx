/**
 * graphexosuit.layer.backend.frontend.components.InterruptPrompt
 *
 * Responsibilities:
 *  - Display interrupt message
 *  - Render radio buttons for each interrupt option
 *  - Allow user to select an option
 *  - Invoke callback with selected option
 */

import React from 'react';
import { StandardizedInterrupt, InterruptOption } from '@/types/api';

interface InterruptPromptProps {
  interrupt: StandardizedInterrupt;
  selectedOption: InterruptOption | null;
  onSelectOption: (option: InterruptOption) => void;
}

/**
 * InterruptPrompt component: Display interrupt options and allow selection.
 *
 * Why: Present user with available interrupt choices and capture selection.
 *
 * Args:
 *   interrupt: Interrupt data with message and options.
 *   selectedOption: Currently selected option (if any).
 *   onSelectOption: Callback when user selects an option.
 */
function InterruptPrompt({
  interrupt,
  selectedOption,
  onSelectOption,
}: InterruptPromptProps) {
  return (
    <div className="space-y-4">
      {/* Interrupt message */}
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-2">
          Graph Paused
        </h3>
        <p className="text-gray-700">{interrupt.message}</p>
      </div>

      {/* Options */}
      <fieldset className="space-y-3">
        <legend className="text-sm font-semibold text-gray-900">
          Choose an option:
        </legend>

        {interrupt.options.map((option, index) => (
          <label
            key={index}
            className="flex items-center gap-3 p-3 border border-gray-200 rounded-md hover:bg-gray-50 cursor-pointer transition-colors"
          >
            <input
              type="radio"
              name="interrupt-option"
              checked={selectedOption === option}
              onChange={() => onSelectOption(option)}
              className="h-4 w-4 text-blue-600 focus:ring-blue-500"
              aria-label={option.label}
            />
            <span className="text-gray-900">{option.label}</span>
          </label>
        ))}
      </fieldset>
    </div>
  );
}

export default InterruptPrompt;
