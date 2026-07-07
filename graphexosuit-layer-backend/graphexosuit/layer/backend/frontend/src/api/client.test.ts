/**
 * Tests for graphexosuit.layer.backend.frontend.api.client
 *
 * Responsibilities:
 *  - Test all API endpoint functions
 *  - Verify request/response handling
 *  - Test error scenarios
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import axios from 'axios';
import {
  runGraph,
  pollThread,
  resumeThread,
  retryThread,
} from '@/api/client';

vi.mock('axios');
const mockedAxios = axios as unknown as {
  create: ReturnType<typeof vi.fn>;
};

describe('API Client', () => {
  let mockPostFn: ReturnType<typeof vi.fn>;
  let mockGetFn: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockPostFn = vi.fn();
    mockGetFn = vi.fn();

    mockedAxios.create.mockReturnValue({
      post: mockPostFn,
      get: mockGetFn,
    });

    // Re-import to get fresh instance with mocked axios
    vi.resetModules();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('runGraph', () => {
    it('should make POST request to /run with initial_state', async () => {
      const initialState = { key: 'value' };
      const response = { thread_id: 'abc123', poll_url: '/thread/abc123' };

      mockPostFn.mockResolvedValueOnce({ data: response });

      // Import fresh to use mocked axios
      const { runGraph: testRunGraph } = await import('@/api/client');
      const result = await testRunGraph(initialState);

      expect(mockPostFn).toHaveBeenCalledWith('/run', {
        initial_state: initialState,
      });
      expect(result).toEqual(response);
    });

    it('should propagate network errors', async () => {
      const error = new Error('Network error');
      mockPostFn.mockRejectedValueOnce(error);

      const { runGraph: testRunGraph } = await import('@/api/client');
      await expect(testRunGraph({})).rejects.toThrow('Network error');
    });
  });

  describe('pollThread', () => {
    it('should make GET request to /thread/{threadId}', async () => {
      const threadId = 'abc123';
      const response = {
        status: 'running',
        output_lines: [],
        created_at: '2024-01-01T00:00:00Z',
      };

      mockGetFn.mockResolvedValueOnce({ data: response });

      const { pollThread: testPollThread } = await import('@/api/client');
      const result = await testPollThread(threadId);

      expect(mockGetFn).toHaveBeenCalledWith(`/thread/${threadId}`);
      expect(result).toEqual(response);
    });

    it('should handle 404 errors', async () => {
      const error = new Error('Thread not found');
      mockGetFn.mockRejectedValueOnce(error);

      const { pollThread: testPollThread } = await import('@/api/client');
      await expect(testPollThread('nonexistent')).rejects.toThrow(
        'Thread not found'
      );
    });
  });

  describe('resumeThread', () => {
    it('should make POST request with resume value', async () => {
      const threadId = 'abc123';
      const checkpointId = 'ckpt123';
      const resumeValue = { choice: 'option1' };
      const response = { thread_id: 'abc123', poll_url: '/thread/abc123' };

      mockPostFn.mockResolvedValueOnce({ data: response });

      const { resumeThread: testResumeThread } = await import('@/api/client');
      const result = await testResumeThread(threadId, checkpointId, resumeValue);

      expect(mockPostFn).toHaveBeenCalledWith(
        `/thread/${threadId}/checkpoint/${checkpointId}/resume`,
        resumeValue
      );
      expect(result).toEqual(response);
    });

    it('should handle API errors', async () => {
      const error = new Error('Bad request');
      mockPostFn.mockRejectedValueOnce(error);

      const { resumeThread: testResumeThread } = await import('@/api/client');
      await expect(
        testResumeThread('abc123', 'ckpt123', {})
      ).rejects.toThrow('Bad request');
    });
  });

  describe('retryThread', () => {
    it('should make POST request to retry endpoint', async () => {
      const threadId = 'abc123';
      const checkpointId = 'ckpt123';
      const response = { thread_id: 'abc123', poll_url: '/thread/abc123' };

      mockPostFn.mockResolvedValueOnce({ data: response });

      const { retryThread: testRetryThread } = await import('@/api/client');
      const result = await testRetryThread(threadId, checkpointId);

      expect(mockPostFn).toHaveBeenCalledWith(
        `/thread/${threadId}/checkpoint/${checkpointId}/retry`
      );
      expect(result).toEqual(response);
    });

    it('should handle retry errors', async () => {
      const error = new Error('Retry failed');
      mockPostFn.mockRejectedValueOnce(error);

      const { retryThread: testRetryThread } = await import('@/api/client');
      await expect(testRetryThread('abc123', 'ckpt123')).rejects.toThrow(
        'Retry failed'
      );
    });
  });
});
