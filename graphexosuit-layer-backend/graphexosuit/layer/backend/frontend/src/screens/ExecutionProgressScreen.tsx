/**
 * graphexosuit.layer.backend.frontend.screens.ExecutionProgressScreen
 *
 * Responsibilities:
 *  - Display real-time output from execution (95% width, 25 default rows, scrollable, drag-resizable)
 *  - Poll thread status at configurable interval (250-10000ms, default 1000ms)
 *  - Update output_lines incrementally with smart scrolling
 *  - Handle status changes: running → paused (interrupt) | completed (result) | error
 *  - On paused: show interrupt prompt, allow JSON editing, Resume button
 *  - On error: show error message, Retry button
 *  - On completed: show final result, Run Again button
 *  - Polling interval control slider
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { pollThread, resumeThread, retryThread } from '@/api/client';
import {
  ExecutionData,
  ExecutionStatus,
  StandardizedInterrupt,
  InterruptOption,
} from '@/types/api';
import { useAppContext } from '@/context/AppContext';
import OutputTextBox from '@/components/OutputTextBox';
import InterruptPrompt from '@/components/InterruptPrompt';
import JSONEditorModal from '@/components/JSONEditorModal';
import StatusBadge from '@/components/StatusBadge';

interface ExecutionProgressScreenProps {
  threadId: string;
  onResetToPreRun: () => void;
}

/**
 * ExecutionProgressScreen component: Real-time execution monitoring and control.
 *
 * Why: Display execution progress, allow user interaction (resume/retry/start over),
 * and manage polling lifecycle.
 *
 * Args:
 *   threadId: The execution thread identifier.
 *   onResetToPreRun: Callback to return to pre-run screen.
 */
function ExecutionProgressScreen({
  threadId,
  onResetToPreRun,
}: ExecutionProgressScreenProps): JSX.Element {
  const { pollingInterval, updatePollingInterval } = useAppContext();

  // Execution state
  const [status, setStatus] = useState<ExecutionStatus>('running');
  const [outputLines, setOutputLines] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [finalResult, setFinalResult] = useState<unknown>(null);
  const [interrupt, setInterrupt] = useState<StandardizedInterrupt | null>(
    null
  );
  const [checkpointId, setCheckpointId] = useState<string | null>(null);

  // UI state
  const [selectedInterruptOption, setSelectedInterruptOption] =
    useState<InterruptOption | null>(null);
  const [resumeJsonContent, setResumeJsonContent] = useState<string>('');
  const [isResumeJsonValid, setIsResumeJsonValid] = useState(true);
  const [isResuming, setIsResuming] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);
  const [pollingError, setPollingError] = useState<string | null>(null);
  const [outputBoxHeight, setOutputBoxHeight] = useState(25);

  // Refs for polling control
  const pollAbortControllerRef = useRef<AbortController | null>(null);
  const lastOutputCountRef = useRef(0);

  /**
   * Validate JSON in resume editor.
   */
  useEffect(() => {
    if (!resumeJsonContent) {
      setIsResumeJsonValid(true);
      return;
    }
    try {
      JSON.parse(resumeJsonContent);
      setIsResumeJsonValid(true);
    } catch {
      setIsResumeJsonValid(false);
    }
  }, [resumeJsonContent]);

  /**
   * When interrupt option is selected, preload its payload into JSON editor.
   */
  useEffect(() => {
    if (selectedInterruptOption) {
      setResumeJsonContent(
        JSON.stringify(selectedInterruptOption.payload, null, 2)
      );
    }
  }, [selectedInterruptOption]);

  /**
   * Main polling loop: Fetch execution data, update state, stop on completion/error.
   */
  const poll = useCallback(async () => {
    try {
      setPollingError(null);
      const data: ExecutionData = await pollThread(threadId);

      // Update status
      setStatus(data.status);

      // Append new output lines (avoid duplicates)
      // TODO: replace contents with all of data.output_lines in case the execution data store is reset (e.g., the {thread}.output_lines key hits its TTL) while the frontend is still open
      if (data.output_lines && data.output_lines.length > lastOutputCountRef.current) {
        const newLines = data.output_lines.slice(lastOutputCountRef.current);
        setOutputLines((prev) => [...prev, ...newLines]);
        lastOutputCountRef.current = data.output_lines.length;
      }

      // Handle status-specific updates
      if (data.status === 'paused' && data.result?.interrupt_value) {
        const interruptValue = data.result.interrupt_value;
        setInterrupt(interruptValue);
        setCheckpointId(data.result.checkpoint_id || null);
        setSelectedInterruptOption(null); // Reset selection
      } else if (data.status === 'completed' && data.result?.final_result) {
        setFinalResult(data.result.final_result);
      } else if (data.status === 'error' && data.error) {
        setError(data.error.message);
        setCheckpointId(data.error.checkpoint_id || null);
      }
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : 'Polling failed';
      setPollingError(`Polling error: ${errorMessage}`);
    }
  }, [threadId]);

  /**
   * Setup polling interval.
   */
  useEffect(() => {
    // Don't poll if execution is complete or in error
    if (status === 'completed' || status === 'error') {
      return;
    }

    // Create abort controller for this polling cycle
    pollAbortControllerRef.current = new AbortController();

    // Initial poll immediately
    poll().catch(() => {
      // Error already handled in poll()
    });

    // Set up interval for subsequent polls
    const intervalId = setInterval(() => {
      poll().catch(() => {
        // Error already handled in poll()
      });
    }, pollingInterval);

    // Cleanup on unmount or when status/interval changes
    return () => {
      clearInterval(intervalId);
      pollAbortControllerRef.current?.abort();
    };
  }, [poll, pollingInterval, status]);

  /**
   * Handle Resume button click: send edited JSON payload and resume execution.
   */
  const handleResume = async () => {
    if (!checkpointId || !isResumeJsonValid) {
      return;
    }

    setPollingError(null);
    setIsResuming(true);

    try {
      const payload = JSON.parse(resumeJsonContent);
      await resumeThread(threadId, checkpointId, payload);
      // Clear interrupt state and continue polling
      setInterrupt(null);
      setSelectedInterruptOption(null);
      setResumeJsonContent('');
      setStatus('running');
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : 'Resume failed';
      setPollingError(`Failed to resume: ${errorMessage}`);
    } finally {
      setIsResuming(false);
    }
  };

  /**
   * Handle Retry button click: retry from checkpoint.
   */
  const handleRetry = async () => {
    if (!checkpointId) {
      return;
    }

    setPollingError(null);
    setIsRetrying(true);

    try {
      await retryThread(threadId, checkpointId);
      // Clear error state and continue polling
      setError(null);
      setStatus('running');
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : 'Retry failed';
      setPollingError(`Failed to retry: ${errorMessage}`);
    } finally {
      setIsRetrying(false);
    }
  };

  return (
    <div className="py-8">
      <div className="flex-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900 mb-2">
            Execution Progress
          </h2>
          <p className="text-gray-600 text-sm">
            Thread ID: <code className="font-mono">{threadId}</code>
          </p>
        </div>
        <StatusBadge status={status} />
      </div>

      <div className="mb-6 p-4 bg-gray-50 border border-gray-200 rounded-md">
        <label
          htmlFor="polling-interval-input"
          className="block text-sm font-medium text-gray-700 mb-2"
        >
          Polling Interval (ms)
        </label>
        <div className="flex items-center gap-4">
          <input
            id="polling-interval-input"
            type="range"
            min="250"
            max="10000"
            step="100"
            value={pollingInterval}
            onChange={(e) => updatePollingInterval(Number(e.target.value))}
            className="flex-1"
            aria-label="Polling interval slider"
          />
          <span
            className="text-sm font-mono text-gray-700 w-16 text-right"
            aria-live="polite"
          >
            {pollingInterval} ms
          </span>
        </div>
      </div>

      {pollingError && (
        <div
          className="error-message mb-6"
          role="alert"
          aria-live="assertive"
        >
          {pollingError}
        </div>
      )}

      <div className="mb-6">
        <OutputTextBox
          lines={outputLines}
          height={outputBoxHeight}
          onHeightChange={setOutputBoxHeight}
          ariaLabel="Graph execution output"
        />
      </div>

      {status === 'paused' && interrupt ? (
        <div className="mb-6 p-4 bg-blue-50 border border-blue-300 rounded-md">
          <InterruptPrompt
            interrupt={interrupt}
            selectedOption={selectedInterruptOption}
            onSelectOption={setSelectedInterruptOption}
          />

          {selectedInterruptOption && (
            <div className="mt-6">
              <h4 className="text-sm font-semibold text-gray-900 mb-3">
                Edit Resume Payload
              </h4>
              <JSONEditorModal
                value={resumeJsonContent}
                onChange={setResumeJsonContent}
                isValid={isResumeJsonValid}
              />

              {!isResumeJsonValid && (
                <div className="error-message mt-3">Invalid JSON</div>
              )}

              <div className="flex gap-3 justify-end mt-4">
                <button
                  onClick={onResetToPreRun}
                  className="btn-secondary"
                  aria-label="Return to pre-run screen"
                >
                  Start Over
                </button>
                <button
                  onClick={handleResume}
                  disabled={!isResumeJsonValid || isResuming}
                  className="btn-primary"
                  aria-label={
                    isResuming ? 'Resuming execution...' : 'Resume execution'
                  }
                  aria-busy={isResuming}
                >
                  {isResuming && (
                    <span className="spinner mr-2" aria-hidden="true"></span>
                  )}
                  {isResuming ? 'Resuming...' : 'Resume'}
                </button>
              </div>
            </div>
          )}
        </div>
      ) : null}

      {status === 'error' && error ? (
        <div className="mb-6 p-4 bg-red-50 border border-red-300 rounded-md">
          <h4 className="text-sm font-semibold text-red-900 mb-2">Error</h4>
          <p className="text-red-800 text-sm mb-4">{error}</p>
          <div className="flex gap-3 justify-end">
            <button
              onClick={onResetToPreRun}
              className="btn-secondary"
              aria-label="Return to pre-run screen"
            >
              Start Over
            </button>
            <button
              onClick={handleRetry}
              disabled={isRetrying}
              className="btn-danger"
              aria-label={isRetrying ? 'Retrying...' : 'Retry execution'}
              aria-busy={isRetrying}
            >
              {isRetrying && (
                <span className="spinner mr-2" aria-hidden="true"></span>
              )}
              {isRetrying ? 'Retrying...' : 'Retry'}
            </button>
          </div>
        </div>
      ) : null}

      {status === 'completed' && finalResult ? (
        <div className="mb-6 p-4 bg-green-50 border border-green-300 rounded-md">
          <h4 className="text-sm font-semibold text-green-900 mb-3">
            Execution Completed
          </h4>
          <div className="bg-white border border-green-200 rounded-md p-3 mb-4 overflow-auto max-h-64">
            <pre className="font-mono text-sm text-gray-900">
              {JSON.stringify(finalResult, null, 2)}
            </pre>
          </div>
          <div className="flex justify-end">
            <button
              onClick={onResetToPreRun}
              className="btn-primary"
              aria-label="Return to pre-run screen"
            >
              Run Again
            </button>
          </div>
        </div>
      ) : null}
    </div>
  ) as JSX.Element;
}

export default ExecutionProgressScreen;
