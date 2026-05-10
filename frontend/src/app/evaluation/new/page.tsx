'use client';

import { Suspense, useEffect, useState } from 'react';
import {
  ApiError,
  api,
  type EvaluationContextResponse,
  type EvaluationResponse,
  type EvaluationStyle,
} from '@/lib/api';

const STYLE_LABELS: Record<EvaluationStyle, string> = {
  formal: '正式',
  encouraging: '鼓勵',
  objective: '客觀',
};

export default function NewEvaluationPage() {
  return (
    <Suspense fallback={<p className="text-ink-muted">載入中…</p>}>
      <NewEvaluationForm />
    </Suspense>
  );
}

function NewEvaluationForm() {
  const [semester, setSemester] = useState('113-1');
  const [pseudoId, setPseudoId] = useState('');
  const [seed, setSeed] = useState('');
  const [style, setStyle] = useState<EvaluationStyle>('formal');

  const [context, setContext] = useState<EvaluationContextResponse | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluationResponse | null>(null);
  const [editedText, setEditedText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Manual fetch — context only loads when the teacher confirms semester+student
  async function fetchContext() {
    setError(null);
    setContext(null);
    if (!pseudoId.trim()) return;
    setLoading(true);
    try {
      const ctx = await api.getEvaluationContext(semester, pseudoId);
      setContext(ctx);
    } catch (err) {
      setError(formatError(err));
    } finally {
      setLoading(false);
    }
  }

  async function generate() {
    if (!seed.trim()) {
      setError('評價種子不可空白');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const e = await api.generateEvaluation({
        semester_label: semester,
        student_pseudo_id: pseudoId,
        seed_text: seed,
        style,
      });
      setEvaluation(e);
      setEditedText(e.edited_text ?? e.generated_text);
    } catch (err) {
      setError(formatError(err));
    } finally {
      setLoading(false);
    }
  }

  async function save() {
    if (!evaluation) return;
    setLoading(true);
    setError(null);
    try {
      const updated = await api.editEvaluation(evaluation.id, editedText);
      setEvaluation(updated);
    } catch (err) {
      setError(formatError(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">撰寫評語</h1>

      {error && (
        <div className="rounded border border-warn/40 bg-warn/5 px-3 py-2 text-warn text-sm">
          {error}
        </div>
      )}

      <section className="space-y-3 rounded-md border border-stone-200 bg-white p-4">
        <h2 className="text-sm font-semibold text-ink-muted">1. 選擇學期與學生</h2>
        <div className="flex flex-wrap gap-3">
          <label className="flex flex-col text-sm">
            學期
            <input
              className="mt-1 rounded border border-stone-300 px-2 py-1"
              value={semester}
              onChange={(e) => setSemester(e.target.value)}
            />
          </label>
          <label className="flex flex-col text-sm">
            學生（暫以資料夾名稱填入）
            <input
              className="mt-1 rounded border border-stone-300 px-2 py-1"
              value={pseudoId}
              placeholder="例：王小明"
              onChange={(e) => setPseudoId(e.target.value)}
            />
          </label>
          <button
            type="button"
            onClick={fetchContext}
            disabled={loading || !pseudoId.trim()}
            className="self-end rounded-md border border-accent px-3 py-1.5 text-accent disabled:opacity-50"
          >
            載入素材
          </button>
        </div>

        {context && (
          <div className="text-xs text-ink-muted">
            找到素材：學習 {context.learning_summaries.length} 篇 · 互動{' '}
            {context.interaction_transcripts.length} 篇 · 作品 {context.work_summaries.length} 篇
          </div>
        )}
      </section>

      <section className="space-y-3 rounded-md border border-stone-200 bg-white p-4">
        <h2 className="text-sm font-semibold text-ink-muted">2. 評價種子 + 風格</h2>
        <textarea
          className="w-full min-h-[6rem] rounded border border-stone-300 px-2 py-1 text-sm"
          placeholder="輸入您對該生這學期的核心觀察（30-100 字建議）"
          value={seed}
          onChange={(e) => setSeed(e.target.value)}
        />
        <div className="flex items-center gap-3">
          {(Object.keys(STYLE_LABELS) as EvaluationStyle[]).map((s) => (
            <label key={s} className="flex items-center gap-1.5 text-sm">
              <input
                type="radio"
                name="style"
                checked={style === s}
                onChange={() => setStyle(s)}
              />
              {STYLE_LABELS[s]}
            </label>
          ))}
          <button
            type="button"
            onClick={generate}
            disabled={loading || !context || !seed.trim()}
            className="ml-auto rounded-md bg-accent text-white px-4 py-1.5 disabled:opacity-50"
          >
            {loading ? '生成中…' : '生成評語'}
          </button>
        </div>
      </section>

      {evaluation && (
        <section className="space-y-3 rounded-md border border-stone-200 bg-white p-4">
          <div className="flex items-baseline justify-between">
            <h2 className="text-sm font-semibold text-ink-muted">3. 編輯與儲存</h2>
            <span className="text-xs text-ink-muted">
              字數：{editedText.length}　·　成本：US$
              {evaluation.llm_cost_usd?.toFixed(5) ?? '?'}
            </span>
          </div>
          <textarea
            className="w-full min-h-[16rem] rounded border border-stone-300 px-3 py-2 text-sm leading-relaxed"
            value={editedText}
            onChange={(e) => setEditedText(e.target.value)}
          />
          <div className="flex justify-end gap-3">
            <button
              type="button"
              onClick={() => setEditedText(evaluation.generated_text)}
              className="rounded-md border border-stone-300 px-3 py-1.5 text-sm text-ink-muted hover:text-ink"
            >
              還原 AI 初稿
            </button>
            <button
              type="button"
              onClick={save}
              disabled={loading}
              className="rounded-md bg-accent text-white px-4 py-1.5 disabled:opacity-50"
            >
              {loading ? '儲存中…' : '儲存'}
            </button>
          </div>
        </section>
      )}
    </div>
  );
}

function formatError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.reason === 'no_artifacts') {
      return '尚未處理該學生的檔案。請先到「檔案處理」執行批次。';
    }
    if (err.status === 401) {
      return '工作階段已逾時，請重新登入。';
    }
    return `${err.message}（${err.status}${err.reason ? ` ${err.reason}` : ''}）`;
  }
  return err instanceof Error ? err.message : String(err);
}
