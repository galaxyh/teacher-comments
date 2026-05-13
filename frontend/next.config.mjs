/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  // Backend (FastAPI) on :8000 in dev. In prod, served on the same host
  // (per OAQ-3 in DESIGN-001 §2.3 — Caddy routes /api → :8000, * → :3000).
  async rewrites() {
    return [
      // Forward auth, drive, file, eval, me, healthz, readyz to backend.
      // /api/* convention reserves Next.js API routes for frontend-only concerns.
      { source: '/auth/:path*', destination: 'http://localhost:8000/auth/:path*' },
      { source: '/drive/:path*', destination: 'http://localhost:8000/drive/:path*' },
      { source: '/onboarding/:path*', destination: 'http://localhost:8000/onboarding/:path*' },
      { source: '/file/:path*', destination: 'http://localhost:8000/file/:path*' },
      { source: '/eval/:path*', destination: 'http://localhost:8000/eval/:path*' },
      { source: '/batch/:path*', destination: 'http://localhost:8000/batch/:path*' },
      { source: '/pii/:path*', destination: 'http://localhost:8000/pii/:path*' },
      // Backend bare /settings was renamed to /settings/me so it doesn't collide
      // with the frontend /settings page; :path* below covers /me, /llm-tier, etc.
      { source: '/settings/:path*', destination: 'http://localhost:8000/settings/:path*' },
      { source: '/me', destination: 'http://localhost:8000/me' },
      { source: '/healthz', destination: 'http://localhost:8000/healthz' },
      { source: '/readyz', destination: 'http://localhost:8000/readyz' },
    ];
  },
};

export default nextConfig;
