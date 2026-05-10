'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ApiError, api, type MeResponse } from '@/lib/api';

export default function HomePage() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const data = await api.me();
        setMe(data);
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          // Anonymous — render the login CTA
          setMe(null);
        } else {
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return <p className="text-ink-muted">載入中…</p>;
  }

  if (error) {
    return (
      <p className="text-warn">
        無法連線後端（{error}）。請確認 backend 正在 :8000 執行。
      </p>
    );
  }

  if (me === null) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold">歡迎</h1>
        <p className="text-ink-muted">
          請使用 Google 帳號登入以開始使用。
        </p>
        <a
          href={api.loginUrl('/')}
          className="inline-block rounded-md bg-accent px-4 py-2 text-white shadow-sm hover:opacity-90"
        >
          使用 Google 登入
        </a>
      </div>
    );
  }

  const onboardingPending = !me.has_attested || !me.has_drive_root;

  return (
    <div className="space-y-6">
      <div className="rounded-md border border-stone-200 bg-white p-4">
        <h1 className="text-xl font-semibold">已登入：{me.email}</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Drive 根目錄：{me.has_drive_root ? '已設定' : '尚未設定'}　·
          家長同意聲明：{me.has_attested ? '已勾選' : '尚未勾選'}
        </p>
      </div>

      {onboardingPending && (
        <div className="rounded-md border border-accent/40 bg-accent/5 p-4">
          <p className="text-sm">尚有設定步驟未完成。</p>
          <Link
            href="/onboarding"
            className="mt-2 inline-block rounded-md bg-accent px-3 py-1.5 text-white text-sm"
          >
            前往設定 →
          </Link>
        </div>
      )}

      <section className="grid gap-4 md:grid-cols-2">
        <Card title="批次處理" body="將 Drive 中本學期檔案送 LLM 摘要。" href="/batch" />
        <Card
          title="評語產生"
          body="選擇學期與學生，撰寫評價種子，由 AI 生成初稿。"
          href="/evaluation/new"
        />
      </section>

      <section>
        <button
          type="button"
          onClick={async () => {
            await api.logout();
            window.location.href = '/';
          }}
          className="text-sm text-ink-muted underline hover:text-ink"
        >
          登出
        </button>
      </section>
    </div>
  );
}

function Card({ title, body, href }: { title: string; body: string; href: string }) {
  return (
    <Link
      href={href}
      className="block rounded-md border border-stone-200 bg-white p-4 hover:border-accent transition"
    >
      <h2 className="font-semibold text-accent">{title}</h2>
      <p className="mt-1 text-sm text-ink-muted">{body}</p>
    </Link>
  );
}
