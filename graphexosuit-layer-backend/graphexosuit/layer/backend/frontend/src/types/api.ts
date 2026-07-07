/**
 * GraphExosuit Frontend API Types
 *
 * Responsibilities:
 *  - Define TypeScript interfaces for all backend API response shapes
 *  - Define status enum for execution states
 *  - Provide types for interrupt options and final results
 */

/** Execution status states. */
export type ExecutionStatus = 'running' | 'paused' | 'completed' | 'error';

/** An interrupt option available when execution pauses. */
export interface InterruptOption {
  label: string;
  payload: unknown;
}

/** Standardized interrupt structure returned by backend. */
export interface StandardizedInterrupt {
  message: string;
  options: InterruptOption[];
}

/** Result of a successful graph execution. */
export interface RunResult {
  thread_id: string;
  checkpoint_id?: string;
  interrupt_value?: StandardizedInterrupt;
  final_result?: unknown;
}

/** Error information from backend. */
export interface ExecutionError {
  message: string;
  checkpoint_id?: string;
  thread_id?: string;
}

/** Polling response from GET /thread/{thread_id}. */
export interface ExecutionData {
  created_at: string;
  status: ExecutionStatus;
  error?: ExecutionError | null;
  result?: RunResult | null;
  output_lines: string[];
}

/** Response from POST /run. */
export interface RunResponse {
  thread_id: string;
  poll_url: string;
}

/** Response from POST /thread/{thread_id}/checkpoint/{checkpoint_id}/resume. */
export interface ResumeResponse {
  thread_id: string;
  poll_url: string;
}

/** Response from POST /thread/{thread_id}/checkpoint/{checkpoint_id}/retry. */
export interface RetryResponse {
  thread_id: string;
  poll_url: string;
}
