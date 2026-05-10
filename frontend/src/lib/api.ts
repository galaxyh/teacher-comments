/**
 * API client — typed wrappers around backend FastAPI endpoints.
 *
 * For Phase 6 walking skeleton, types are hand-written. Phase 7+ will switch to
 * generated types via openapi-typescript per ARCH-001 §2.3.
 *
 * All fetches use `credentials: 'include'` so the session cookie travels with
 * cross-origin (in dev) and same-origin (in prod) requests.
 */

const baseFetch = (input: string, init?: RequestInit): Promise<Response> =>
  fetch(input, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  });

async function unwrap<T>(resp: Response): Promise<T> {
  if (resp.status === 401) {
    throw new ApiError('Unauthorized', 401, 'no_session');
  }
  if (!resp.ok) {
    let detail: { reason?: string; message?: string } = {};
    try {
      const body = await resp.json();
      detail = body?.detail ?? body;
    } catch {
      /* ignore — non-JSON error body */
    }
    throw new ApiError(
      detail.message ?? `HTTP ${resp.status}`,
      resp.status,
      detail.reason,
    );
  }
  return (await resp.json()) as T;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly reason?: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

// ── Types (mirrors backend Pydantic schemas) ────────────────────

export type EvaluationStyle = 'formal' | 'encouraging' | 'objective';

export interface MeResponse {
  teacher_id: string;
  email: string;
  has_drive_root: boolean;
  has_attested: boolean;
}

export interface EvaluationContextResponse {
  learning_summaries: string[];
  interaction_transcripts: string[];
  work_summaries: string[];
}

export interface EvaluationResponse {
  id: string;
  teacher_id: string;
  semester_label: string;
  student_pseudo_id: string;
  seed_text: string;
  style: EvaluationStyle;
  generated_text: string;
  edited_text: string | null;
  llm_model: string | null;
  llm_cost_usd: number | null;
  generated_at: string;
  edited_at: string | null;
}

// ── API surface ─────────────────────────────────────────────────

export const api = {
  async me(): Promise<MeResponse> {
    return unwrap<MeResponse>(await baseFetch('/me'));
  },

  loginUrl(returnTo: string = '/'): string {
    return `/auth/login?return_to=${encodeURIComponent(returnTo)}`;
  },

  async logout(): Promise<void> {
    await baseFetch('/auth/logout', { method: 'POST' });
  },

  async getEvaluationContext(
    semesterLabel: string,
    pseudoId: string,
  ): Promise<EvaluationContextResponse> {
    const url = `/eval/${encodeURIComponent(semesterLabel)}/${encodeURIComponent(pseudoId)}/context`;
    return unwrap<EvaluationContextResponse>(await baseFetch(url));
  },

  async generateEvaluation(input: {
    semester_label: string;
    student_pseudo_id: string;
    seed_text: string;
    style: EvaluationStyle;
  }): Promise<EvaluationResponse> {
    return unwrap<EvaluationResponse>(
      await baseFetch('/eval/generate', {
        method: 'POST',
        body: JSON.stringify(input),
      }),
    );
  },

  async editEvaluation(
    evaluationId: string,
    editedText: string,
  ): Promise<EvaluationResponse> {
    return unwrap<EvaluationResponse>(
      await baseFetch(`/eval/${encodeURIComponent(evaluationId)}`, {
        method: 'PUT',
        body: JSON.stringify({ edited_text: editedText }),
      }),
    );
  },
};
