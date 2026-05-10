/**
 * API wrapper unit tests — covers `unwrap` error mapping + `loginUrl` builder.
 *
 * Network calls are stubbed via vi.stubGlobal('fetch', ...). We don't run
 * full integration tests here — that's the Playwright suite's job. These
 * tests guard the error-shape contract the UI relies on.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, api } from './api';

function mockFetch(status: number, body: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      json: async () => body,
    }),
  );
}

describe('api', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  describe('loginUrl', () => {
    it('encodes return_to', () => {
      expect(api.loginUrl('/eval/new')).toBe('/auth/login?return_to=%2Feval%2Fnew');
    });

    it('defaults to root', () => {
      expect(api.loginUrl()).toBe('/auth/login?return_to=%2F');
    });
  });

  describe('me', () => {
    it('returns parsed body on 200', async () => {
      mockFetch(200, {
        teacher_id: 't1',
        email: 'a@b.com',
        has_drive_root: true,
        has_attested: true,
      });
      const me = await api.me();
      expect(me.email).toBe('a@b.com');
    });

    it('throws ApiError with no_session reason on 401', async () => {
      mockFetch(401, { detail: { reason: 'no_session' } });
      await expect(api.me()).rejects.toMatchObject({
        status: 401,
        reason: 'no_session',
      });
    });

    it('parses backend reason field on non-401 errors', async () => {
      mockFetch(412, { detail: { reason: 'no_artifacts', message: 'process first' } });
      try {
        await api.me();
        throw new Error('should have thrown');
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError);
        expect((err as ApiError).status).toBe(412);
        expect((err as ApiError).reason).toBe('no_artifacts');
        expect((err as ApiError).message).toBe('process first');
      }
    });
  });
});
