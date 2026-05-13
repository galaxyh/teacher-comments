'use client';

import { useEffect, useState } from 'react';
import { ApiError, api, type DriveTreeNode, type ScanResult } from '@/lib/api';

type Step = 'attest' | 'pick-root' | 'mapping' | 'done';

const ATTESTATION_VERSION = 'v1';
const ATTESTATION_TEXT = `本人聲明：
- 我已就處理之學生個人資料（含作品、課堂紀錄、影音）取得家長/監護人書面同意。
- 我了解系統會將去識別化（PII 匿名化）後的內容傳送至外部 LLM 服務以協助生成評語草稿。
- 我同意承擔本系統使用之教學責任；若家長同意撤回，我將立即停止處理該學生資料。`;

const CATEGORY_OPTIONS: { value: string; label: string }[] = [
  { value: 'learning', label: '學習紀錄' },
  { value: 'interaction', label: '教師與學生互動紀錄' },
  { value: 'work', label: '作品成果' },
  { value: '__skip__', label: '不歸類（略過）' },
];

export default function OnboardingPage() {
  const [step, setStep] = useState<Step>('attest');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Step 2 — Drive root picker (tree, lazy-loaded)
  const [candidates, setCandidates] = useState<DriveTreeNode[]>([]);
  const [pickedRootId, setPickedRootId] = useState<string | null>(null);
  const [childrenByFolder, setChildrenByFolder] = useState<Record<string, DriveTreeNode[]>>({});
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set());
  const [loadingFolders, setLoadingFolders] = useState<Set<string>>(new Set());

  async function toggleExpand(folderId: string) {
    setError(null);
    const isExpanded = expandedFolders.has(folderId);
    if (isExpanded) {
      setExpandedFolders((prev) => {
        const next = new Set(prev);
        next.delete(folderId);
        return next;
      });
      return;
    }
    setExpandedFolders((prev) => new Set(prev).add(folderId));
    if (childrenByFolder[folderId]) return; // cached
    setLoadingFolders((prev) => new Set(prev).add(folderId));
    try {
      const items = await api.listDriveChildren(folderId);
      setChildrenByFolder((prev) => ({ ...prev, [folderId]: items }));
    } catch (err) {
      setError(formatError(err));
      setExpandedFolders((prev) => {
        const next = new Set(prev);
        next.delete(folderId);
        return next;
      });
    } finally {
      setLoadingFolders((prev) => {
        const next = new Set(prev);
        next.delete(folderId);
        return next;
      });
    }
  }

  // Step 3 — folder mapping
  const [scanResult, setScanResult] = useState<ScanResult | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});

  // Bootstrap: skip steps the teacher has already completed
  useEffect(() => {
    (async () => {
      try {
        const me = await api.me();
        if (!me.has_attested) {
          setStep('attest');
          return;
        }
        if (!me.has_drive_root) {
          await loadCandidates();
          setStep('pick-root');
          return;
        }
        // Already attested + has drive root — try a scan to see if mapping is needed
        const r = await api.scan();
        setScanResult(r);
        if (r.needs_folder_mapping) {
          setStep('mapping');
        } else {
          setStep('done');
        }
      } catch (err) {
        setError(formatError(err));
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadCandidates() {
    setBusy(true);
    setError(null);
    try {
      const items = await api.listDriveRootCandidates();
      setCandidates(items);
    } catch (err) {
      setError(formatError(err));
    } finally {
      setBusy(false);
    }
  }

  async function submitAttest() {
    setBusy(true);
    setError(null);
    try {
      await api.attest(ATTESTATION_VERSION);
      await loadCandidates();
      setStep('pick-root');
    } catch (err) {
      setError(formatError(err));
    } finally {
      setBusy(false);
    }
  }

  async function submitDriveRoot() {
    if (!pickedRootId) return;
    setBusy(true);
    setError(null);
    try {
      await api.setDriveRoot(pickedRootId);
      const r = await api.scan();
      setScanResult(r);
      setStep(r.needs_folder_mapping ? 'mapping' : 'done');
    } catch (err) {
      setError(formatError(err));
    } finally {
      setBusy(false);
    }
  }

  async function submitMapping() {
    setBusy(true);
    setError(null);
    try {
      await api.setFolderMapping(mapping);
      const r = await api.scan();
      setScanResult(r);
      if (r.needs_folder_mapping) {
        setError('仍有未對應的資料夾。請完成所有對應後再送出。');
        return;
      }
      setStep('done');
    } catch (err) {
      setError(formatError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">初次設定</h1>
      <Steps current={step} />
      {error && (
        <div className="rounded border border-warn/40 bg-warn/5 px-3 py-2 text-warn text-sm">
          {error}
        </div>
      )}

      {step === 'attest' && <AttestStep onSubmit={submitAttest} busy={busy} />}

      {step === 'pick-root' && (
        <PickRootStep
          candidates={candidates}
          picked={pickedRootId}
          setPicked={setPickedRootId}
          busy={busy}
          onSubmit={submitDriveRoot}
          childrenByFolder={childrenByFolder}
          expandedFolders={expandedFolders}
          loadingFolders={loadingFolders}
          onToggleExpand={toggleExpand}
        />
      )}

      {step === 'mapping' && scanResult && (
        <MappingStep
          unmapped={scanResult.unmapped_category_names}
          mapping={mapping}
          setMapping={setMapping}
          busy={busy}
          onSubmit={submitMapping}
        />
      )}

      {step === 'done' && scanResult && <DoneStep scanResult={scanResult} />}
    </div>
  );
}

function Steps({ current }: { current: Step }) {
  const labels: Record<Step, string> = {
    attest: '1. 同意聲明',
    'pick-root': '2. 選擇 Drive 根目錄',
    mapping: '3. 對應資料夾名稱',
    done: '完成',
  };
  const order: Step[] = ['attest', 'pick-root', 'mapping', 'done'];
  return (
    <ol className="flex flex-wrap gap-2 text-xs text-ink-muted">
      {order.map((s) => (
        <li
          key={s}
          className={
            s === current
              ? 'rounded-full bg-accent px-3 py-1 text-white'
              : 'rounded-full border border-stone-300 px-3 py-1'
          }
        >
          {labels[s]}
        </li>
      ))}
    </ol>
  );
}

function AttestStep({ onSubmit, busy }: { onSubmit: () => void; busy: boolean }) {
  const [agreed, setAgreed] = useState(false);
  return (
    <section className="space-y-3 rounded-md border border-stone-200 bg-white p-4">
      <h2 className="font-semibold">家長/監護人同意聲明</h2>
      <pre className="whitespace-pre-wrap rounded bg-stone-50 p-3 text-sm text-ink-muted">
        {ATTESTATION_TEXT}
      </pre>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
        我已閱讀並同意上述聲明
      </label>
      <button
        type="button"
        disabled={!agreed || busy}
        onClick={onSubmit}
        className="rounded-md bg-accent text-white px-4 py-1.5 disabled:opacity-50"
      >
        {busy ? '送出中…' : '同意並繼續'}
      </button>
    </section>
  );
}

function PickRootStep({
  candidates,
  picked,
  setPicked,
  busy,
  onSubmit,
  childrenByFolder,
  expandedFolders,
  loadingFolders,
  onToggleExpand,
}: {
  candidates: DriveTreeNode[];
  picked: string | null;
  setPicked: (id: string) => void;
  busy: boolean;
  onSubmit: () => void;
  childrenByFolder: Record<string, DriveTreeNode[]>;
  expandedFolders: Set<string>;
  loadingFolders: Set<string>;
  onToggleExpand: (folderId: string) => void;
}) {
  return (
    <section className="space-y-3 rounded-md border border-stone-200 bg-white p-4">
      <h2 className="font-semibold">選擇教學資料根目錄</h2>
      <p className="text-sm text-ink-muted">
        系統會掃描此資料夾下的「學期 / 學生 / 類別」3 層結構。可展開子資料夾並選擇任一層作為根目錄。
      </p>
      <ul className="divide-y divide-stone-100">
        {candidates.map((c) => (
          <TreeRow
            key={c.drive_file_id}
            node={c}
            depth={0}
            picked={picked}
            setPicked={setPicked}
            childrenByFolder={childrenByFolder}
            expandedFolders={expandedFolders}
            loadingFolders={loadingFolders}
            onToggleExpand={onToggleExpand}
          />
        ))}
        {candidates.length === 0 && (
          <li className="py-2 text-sm text-ink-muted">（尚未載入或 Drive 無頂層資料夾）</li>
        )}
      </ul>
      <button
        type="button"
        disabled={!picked || busy}
        onClick={onSubmit}
        className="rounded-md bg-accent text-white px-4 py-1.5 disabled:opacity-50"
      >
        {busy ? '掃描中…' : '繼續'}
      </button>
    </section>
  );
}

function TreeRow({
  node,
  depth,
  picked,
  setPicked,
  childrenByFolder,
  expandedFolders,
  loadingFolders,
  onToggleExpand,
}: {
  node: DriveTreeNode;
  depth: number;
  picked: string | null;
  setPicked: (id: string) => void;
  childrenByFolder: Record<string, DriveTreeNode[]>;
  expandedFolders: Set<string>;
  loadingFolders: Set<string>;
  onToggleExpand: (folderId: string) => void;
}) {
  const expanded = expandedFolders.has(node.drive_file_id);
  const loading = loadingFolders.has(node.drive_file_id);
  const children = childrenByFolder[node.drive_file_id];
  return (
    <>
      <li
        className="flex items-center gap-2 py-2 text-sm"
        style={{ paddingLeft: `${depth * 1.25}rem` }}
      >
        {node.is_folder ? (
          <button
            type="button"
            onClick={() => onToggleExpand(node.drive_file_id)}
            className="w-5 select-none text-ink-muted hover:text-ink"
            aria-label={expanded ? '收合' : '展開'}
          >
            {loading ? '…' : expanded ? '▼' : '▶'}
          </button>
        ) : (
          <span className="w-5" />
        )}
        <input
          type="radio"
          name="root"
          checked={picked === node.drive_file_id}
          onChange={() => setPicked(node.drive_file_id)}
        />
        <label
          className="cursor-pointer"
          onClick={() => setPicked(node.drive_file_id)}
        >
          {node.name}
        </label>
      </li>
      {expanded && children && children.length === 0 && (
        <li
          className="py-1 text-xs text-ink-muted"
          style={{ paddingLeft: `${(depth + 1) * 1.25 + 1.5}rem` }}
        >
          （此資料夾沒有子資料夾）
        </li>
      )}
      {expanded &&
        children?.map((child) => (
          <TreeRow
            key={child.drive_file_id}
            node={child}
            depth={depth + 1}
            picked={picked}
            setPicked={setPicked}
            childrenByFolder={childrenByFolder}
            expandedFolders={expandedFolders}
            loadingFolders={loadingFolders}
            onToggleExpand={onToggleExpand}
          />
        ))}
    </>
  );
}

function MappingStep({
  unmapped,
  mapping,
  setMapping,
  busy,
  onSubmit,
}: {
  unmapped: string[];
  mapping: Record<string, string>;
  setMapping: (m: Record<string, string>) => void;
  busy: boolean;
  onSubmit: () => void;
}) {
  const allMapped = unmapped.every((name) => mapping[name]);
  return (
    <section className="space-y-3 rounded-md border border-stone-200 bg-white p-4">
      <h2 className="font-semibold">對應資料夾名稱</h2>
      <p className="text-sm text-ink-muted">
        以下資料夾名稱不在標準三類別內，請選擇對應的類別或「不歸類」。
      </p>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-ink-muted">
            <th className="py-1">資料夾名稱</th>
            <th className="py-1">對應類別</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-stone-100">
          {unmapped.map((name) => (
            <tr key={name}>
              <td className="py-2">{name}</td>
              <td className="py-2">
                <select
                  className="rounded border border-stone-300 px-2 py-1"
                  value={mapping[name] ?? ''}
                  onChange={(e) => setMapping({ ...mapping, [name]: e.target.value })}
                >
                  <option value="" disabled>
                    請選擇…
                  </option>
                  {CATEGORY_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button
        type="button"
        disabled={!allMapped || busy}
        onClick={onSubmit}
        className="rounded-md bg-accent text-white px-4 py-1.5 disabled:opacity-50"
      >
        {busy ? '儲存中…' : '完成設定'}
      </button>
    </section>
  );
}

function DoneStep({ scanResult }: { scanResult: ScanResult }) {
  return (
    <section className="space-y-3 rounded-md border border-stone-200 bg-white p-4">
      <h2 className="font-semibold text-accent">設定完成</h2>
      <p className="text-sm text-ink-muted">
        共偵測到 {scanResult.semesters_found} 個學期、{scanResult.students_found} 位學生、
        新增/更新 {scanResult.files_indexed} 個檔案
        （{scanResult.files_unchanged} 個未變更）。
      </p>
      <a
        href="/batch"
        className="inline-block rounded-md bg-accent text-white px-4 py-1.5"
      >
        前往批次處理 →
      </a>
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
