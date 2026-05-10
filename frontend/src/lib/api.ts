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

export interface DriveTreeNode {
  drive_file_id: string;
  name: string;
  is_folder: boolean;
}

export interface ScanResult {
  semesters_found: number;
  students_found: number;
  files_indexed: number;
  files_unchanged: number;
  needs_folder_mapping: boolean;
  unmapped_category_names: string[];
}

export interface BatchStatusResponse {
  batch_job_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  total: number;
  completed: number;
  failed: number;
  total_cost_usd: number | null;
  started_at: string;
  finished_at: string | null;
}

export interface BatchEvent {
  batch_job_id: string;
  state: 'running' | 'completed' | 'failed' | 'cancelled';
  total: number;
  completed: number;
  failed: number;
  last_event: { drive_file_id: string; ok: boolean; reason: string | null } | null;
}

export type PIIType =
  | 'student_name'
  | 'student_id'
  | 'parent_name'
  | 'phone'
  | 'email'
  | 'address'
  | 'other_name'
  | 'other';

export interface PIIMappingRow {
  id: string;
  pseudonym: string;
  pii_type: string;
  display_name: string | null;
  original_value: string | null;
  source: string;
  created_at: string | null;
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

  async startBatch(semesterLabel: string): Promise<{
    batch_job_id: string;
    total: number;
    status: string;
  }> {
    return unwrap(
      await baseFetch('/batch/start', {
        method: 'POST',
        body: JSON.stringify({ semester_label: semesterLabel }),
      }),
    );
  },

  async cancelBatch(batchJobId: string): Promise<void> {
    await baseFetch(`/batch/${encodeURIComponent(batchJobId)}/cancel`, {
      method: 'POST',
    });
  },

  async getBatchStatus(batchJobId: string): Promise<BatchStatusResponse> {
    return unwrap<BatchStatusResponse>(
      await baseFetch(`/batch/${encodeURIComponent(batchJobId)}/status`),
    );
  },

  /**
   * Open an EventSource for batch progress. Returns the EventSource handle so
   * the caller can `.close()` on unmount. The browser auto-reconnects on
   * transient drops; the server emits a terminal event on completion which we
   * use to close cleanly.
   */
  openBatchEventStream(batchJobId: string): EventSource {
    return new EventSource(`/batch/${encodeURIComponent(batchJobId)}/events`, {
      withCredentials: true,
    });
  },

  // ── Onboarding ────────────────────────────────────────────────

  async attest(version: string = 'v1'): Promise<{ version: string }> {
    return unwrap(
      await baseFetch('/onboarding/attest', {
        method: 'POST',
        body: JSON.stringify({ version }),
      }),
    );
  },

  async listDriveRootCandidates(): Promise<DriveTreeNode[]> {
    const body = await unwrap<{ items: DriveTreeNode[] }>(await baseFetch('/drive/list'));
    return body.items;
  },

  async setDriveRoot(folderId: string): Promise<void> {
    await baseFetch('/onboarding/drive-root', {
      method: 'POST',
      body: JSON.stringify({ folder_id: folderId }),
    });
  },

  async scan(): Promise<ScanResult> {
    return unwrap<ScanResult>(
      await baseFetch('/drive/scan', { method: 'POST' }),
    );
  },

  async setFolderMapping(mapping: Record<string, string>): Promise<void> {
    await baseFetch('/onboarding/folder-mapping', {
      method: 'POST',
      body: JSON.stringify({ mapping }),
    });
  },

  // ── PII Min UI (D13) ──────────────────────────────────────────

  async listPIIMappings(): Promise<PIIMappingRow[]> {
    return unwrap<PIIMappingRow[]>(await baseFetch('/pii/mappings'));
  },

  async updatePIIDisplayName(pseudonym: string, displayName: string | null): Promise<void> {
    await baseFetch(`/pii/mappings/${encodeURIComponent(pseudonym)}/display-name`, {
      method: 'PUT',
      body: JSON.stringify({ display_name: displayName ?? '' }),
    });
  },

  async addManualPIIMapping(input: {
    pseudonym: string;
    original_value: string;
    pii_type: PIIType;
  }): Promise<PIIMappingRow> {
    return unwrap<PIIMappingRow>(
      await baseFetch('/pii/mappings', {
        method: 'POST',
        body: JSON.stringify(input),
      }),
    );
  },

  // ── Settings ───────────────────────────────────────────────────

  async getSettings(): Promise<SettingsResponse> {
    return unwrap<SettingsResponse>(await baseFetch('/settings'));
  },

  async updateTierConfig(overrides: Record<string, string>): Promise<void> {
    await baseFetch('/settings/llm-tier', {
      method: 'PUT',
      body: JSON.stringify({ overrides }),
    });
  },
};

export interface SettingsResponse {
  llm_tier_config: Record<string, string>;
  monthly_cost_usd: number;
  monthly_budget_usd: number;
}
