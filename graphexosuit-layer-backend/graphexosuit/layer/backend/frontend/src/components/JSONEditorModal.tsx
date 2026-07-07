/**
 * graphexosuit.layer.backend.frontend.components.JSONEditorModal
 *
 * Responsibilities:
 *  - Display Monaco JSON editor for editing interrupt payload
 *  - Validate JSON in real-time
 *  - Show validation errors
 *  - Update parent component with edited JSON
 */

import React from 'react';
import Editor from '@monaco-editor/react';

interface JSONEditorModalProps {
  value: string;
  onChange: (value: string) => void;
  isValid: boolean;
}

/**
 * JSONEditorModal component: Edit JSON payload with validation.
 *
 * Why: Allow user to modify resume payload before sending to backend.
 *
 * Args:
 *   value: Current JSON string.
 *   onChange: Callback when user edits JSON.
 *   isValid: Whether current JSON is valid.
 */
function JSONEditorModal({ value, onChange, isValid }: JSONEditorModalProps) {
  return (
    <div className="space-y-3">
      {/* JSON Editor */}
      <div className="border border-gray-300 rounded-md overflow-hidden">
        <Editor
          height="300px"
          defaultLanguage="json"
          value={value}
          onChange={(val) => onChange(val || '')}
          options={{
            minimap: { enabled: false },
            wordWrap: 'on',
            fontFamily: 'Menlo, Monaco, "Courier New", monospace',
            fontSize: 13,
            lineNumbers: 'on',
            scrollBeyondLastLine: false,
            folding: true,
          }}
          theme="light"
        />
      </div>

      {/* Validation status */}
      {!isValid && (
        <div
          className="error-message text-xs"
          role="alert"
        >
          ✗ Invalid JSON
        </div>
      )}
      {isValid && value && (
        <div
          className="success-message text-xs"
          role="status"
        >
          ✓ Valid JSON
        </div>
      )}
    </div>
  );
}

export default JSONEditorModal;
