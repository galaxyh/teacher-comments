'use client';

import { useEffect, useRef, useState } from 'react';
import { ApiError, api, type BatchEvent, type BatchStatusResponse } from '@/lib/api';

type Phase = 'idle' | 'starting' | 'running' | 'finished';

export default function BatchPage() {
  const [semester, setSemester] = useState('113-1');
  const [phase, setPhase] = useState<Phase>('idle');
  const [batchId, setBatchId] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<BatchStatusResponse | null>(null);
  const [lastEvent, setLastEvent] = useState<BatchEvent['last_event']>(null);
  const [error, setError] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Cleanup on unmount — close any open SSE connection
  useEffect(() => {
    return () => {
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
    };
  }, []);

  async function startBatch() {
    setError(null);
    setPhase('starting');
    setLastEvent(null);
    setSnapshot(null);
    try {
      const { batch_job_id, total, status } = await api.startBatch(semester);
      setBatchId(batch_job_id);
      setPhase(status === 'completed' ? 'finished' : 'running');
      setSnapshot({
        batch_job_id,
        status: status as BatchStatusResponse['status'],
        total,
        completed: 0,
        failed: 0,
        total_cost_usd: null,
        started_at: new Date().toISOString(),
        finished_at: null,
      });
      if (total > 0 && status !== 'completed') {
        attachEventStream(batch_job_id);
      }
    } catch (err) {
      setError(formatError(err));
      setPhase('idle');
    }
  }

  function attachEventStream(id: string) {
    eventSourceRef.current?.close();
    const es = api.openBatchEventStream(id);
    eventSourceRef.current = es;
    es.onmessage = (msg) => {
      try {
        const ev = JSON.parse(msg.data) as BatchEvent;
        setSnapshot((prev) => ({
          ...(prev ?? {
            batch_job_id: id,
            status: 'running',
            total: ev.total,
            completed: 0,
            failed: 0,
            total_cost_usd: null,
            started_at: new Date().toISOString(),
            finished_at: null,
          }),
          status: ev.state,
          total: ev.total,
          completed: ev.completed,
          failed: ev.failed,
        }));
        setLastEvent(ev.last_event);
        if (ev.state !== 'running') {
          setPhase('finished');
          es.close();
          eventSourceRef.current = null;
        }
      } catch (e) {
        console.error('SSE parse failed', e);
      }
    };
    es.onerror = async () => {
      // EventSource auto-reconnects, but if backend has terminated the stream
      // we fall back to one polling read so the UI shows final state.
      console.warn('SSE error — falling back to /status poll');
      try {
        const snap = await api.getBatchStatus(id);
        setSnapshot(snap);
        if (snap.status !== 'running') {
          setPhase('finished');
          es.close();
          eventSourceRef.current = null;
        }
      } catch {
        // ignored — keep showing whatever we have
      }
    };
  }

  async function cancel() {
    if (!batchId) return;
    try {
      await api.cancelBatch(batchId);
    } catch (err) {
      setError(formatError(err));
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">批次處理</h1>
      <p className="text-sm text-ink-muted">
        將 Drive 中本學期所有「待處理」檔案一次送出 LLM 摘要。
      </p>

      {error && (
        <div className="rounded border border-warn/40 bg-warn/5 px-3 py-2 text-warn text-sm">
          {error}
        </div>
      )}

      <section className="space-y-3 rounded-md border border-stone-200 bg-white p-4">
        <label className="flex items-end gap-3">
          <span className="flex flex-col text-sm">
            學期
            <input
              className="mt-1 rounded border border-stone-300 px-2 py-1"
              value={semester}
              onChange={(e) => setSemester(e.target.value)}
              disabled={phase === 'starting' || phase === 'running'}
            />
          </span>
          <button
            type="button"
            onClick={startBatch}
            disabled={phase === 'starting' || phase === 'running'}
            className="rounded-md bg-accent text-white px-4 py-1.5 disabled:opacity-50"
          >
            {phase === 'starting' ? '啟動中…' : phase === 'running' ? '處理中…' : '開始批次'}
          </button>
          {phase === 'running' && batchId && (
            <button
              type="button"
              onClick={cancel}
              className="rounded-md border border-warn text-warn px-3 py-1.5 hover:bg-warn/5"
            >
              取消
            </button>
          )}
        </label>
      </section>

      {snapshot && <ProgressPanel snapshot={snapshot} lastEvent={lastEvent} />}
    </div>
  );
}

function ProgressPanel({
  snapshot,
  lastEvent,
}: {
  snapshot: BatchStatusResponse;
  lastEvent: BatchEvent['last_event'];
}) {
  const pct =
    snapshot.total > 0
      ? Math.round(((snapshot.completed + snapshot.failed) / snapshot.total) * 100)
      : 0;
  return (
    <section className="space-y-3 rounded-md border border-stone-200 bg-white p-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-ink-muted">進度</h2>
        <span className="text-xs text-ink-muted">
          狀態：{snapshot.status}　·　成本：US$
          {snapshot.total_cost_usd != null ? snapshot.total_cost_usd.toFixed(5) : '—'}
        </span>
      </div>

      <div className="h-3 w-full overflow-hidden rounded bg-stone-200">
        <div
          className="h-full bg-accent transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="flex justify-between text-sm">
        <span>
          {snapshot.completed + snapshot.failed} / {snapshot.total} 檔案
        </span>
        <span className="text-ink-muted">
          完成 {snapshot.completed}　·　失敗 {snapshot.failed}
        </span>
      </div>

      {lastEvent && (
        <div className="text-xs text-ink-muted border-t border-stone-100 pt-2">
          最近事件：drive_file <code className="text-ink">{lastEvent.drive_file_id}</code>{' '}
          {lastEvent.ok ? '✓ 完成' : `✗ ${lastEvent.reason ?? 'unknown'}`}
        </div>
      )}
    </section>
  );
}

function formatError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 401) return '工作階段已逾時，請重新登入。';
    return `${err.message}（${err.status}${err.reason ? ` ${err.reason}` : ''}）`;
  }
  return err instanceof Error ? err.message : String(err);
}
