import type { Config } from 'tailwindcss';

// Design tokens align with mockups/ — Phase 6 walking-skeleton uses minimal
// extension; UIUX-001 design system fully extracted in Phase 7+.
const config: Config = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          DEFAULT: '#1a1a1a',
          muted: '#5a5a5a',
        },
        accent: '#3a5a40',  // 墨痕 brand green
        warn: '#b03030',
        terminal: '#7a1f1f',
      },
      fontFamily: {
        // Notos Sans TC for Chinese; Inter as fallback Latin
        sans: ['Inter', '"Noto Sans TC"', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
};

export default config;
