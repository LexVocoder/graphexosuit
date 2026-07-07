/**
 * graphexosuit.layer.backend.frontend.api.client
 *
 * Responsibilities:
 *  - Wrap axios HTTP client with base URL configuration
 *  - Provide functions: runGraph(), pollThread(), resumeThread(), retryThread()
 *  - Handle request/response serialization
 *  - Provide configurable API base URL via environment
 */

import axios, { AxiosInstance } from 'axios';
import {
  ExecutionData,
  RunResponse,
  ResumeResponse,
  RetryResponse,
} from '@/types/api';

/** Get the API base URL from environment or default. */
function getApiBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
}

/** Create and export singleton axios instance. */
const apiClient: AxiosInstance = axios.create({
  baseURL: getApiBaseUrl(),
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * Start a new graph execution.
 *
 * Why: Initiates async execution via POST /run endpoint.
 *
 * Args:
 *   initialState: Initial input state for the graph.
 *
 * Returns:
 *   Promise resolving to thread_id and poll_url.
 *
 * Throws:
 *   If HTTP request fails (e.g., 500, network error).
 */
export async function runGraph(initialState: unknown): Promise<RunResponse> {
  const response = await apiClient.post<RunResponse>('/run', {
    initial_state: initialState,
  });
  return response.data;
}

/**
 * Poll thread execution status and results.
 *
 * Why: Retrieve execution data (status, output, result, error) via polling.
 *
 * Args:
 *   threadId: The thread identifier.
 *
 * Returns:
 *   Promise resolving to execution data (status, output_lines, result, error, created_at).
 *
 * Throws:
 *   If HTTP request fails or thread not found (404).
 */
export async function pollThread(threadId: string): Promise<ExecutionData> {
  const response = await apiClient.get<ExecutionData>(`/thread/${threadId}`);
  return response.data;
}

/**
 * Resume paused execution with provided resume value.
 *
 * Why: Continue graph execution from interrupt checkpoint with user-provided payload.
 *
 * Args:
 *   threadId: The thread identifier.
 *   checkpointId: The checkpoint identifier.
 *   resumeValue: The JSON payload to send back to the graph.
 *
 * Returns:
 *   Promise resolving to thread_id and poll_url.
 *
 * Throws:
 *   If HTTP request fails or thread/checkpoint not found.
 */
export async function resumeThread(
  threadId: string,
  checkpointId: string,
  resumeValue: unknown
): Promise<ResumeResponse> {
  const response = await apiClient.post<ResumeResponse>(
    `/thread/${threadId}/checkpoint/${checkpointId}/resume`,
    resumeValue
  );
  return response.data;
}

/**
 * Retry failed execution from checkpoint.
 *
 * Why: Re-execute graph from last checkpoint after error.
 *
 * Args:
 *   threadId: The thread identifier.
 *   checkpointId: The checkpoint identifier.
 *
 * Returns:
 *   Promise resolving to thread_id and poll_url.
 *
 * Throws:
 *   If HTTP request fails or thread/checkpoint not found.
 */
export async function retryThread(
  threadId: string,
  checkpointId: string
): Promise<RetryResponse> {
  const response = await apiClient.post<RetryResponse>(
    `/thread/${threadId}/checkpoint/${checkpointId}/retry`
  );
  return response.data;
}
