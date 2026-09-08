/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Semantic tokens — values defined in globals.css for light + dark.
        app: {
          bg: 'rgb(var(--app-bg) / <alpha-value>)',
          surface: 'rgb(var(--app-surface) / <alpha-value>)',
          'surface-2': 'rgb(var(--app-surface-2) / <alpha-value>)',
          hover: 'rgb(var(--app-hover) / <alpha-value>)',
          input: 'rgb(var(--app-input) / <alpha-value>)',
          border: 'rgb(var(--app-border) / <alpha-value>)',
          'border-strong': 'rgb(var(--app-border-strong) / <alpha-value>)',
          text: 'rgb(var(--app-text) / <alpha-value>)',
          soft: 'rgb(var(--app-text-soft) / <alpha-value>)',
          subtle: 'rgb(var(--app-text-subtle) / <alpha-value>)',
          muted: 'rgb(var(--app-text-muted) / <alpha-value>)',
          faint: 'rgb(var(--app-text-faint) / <alpha-value>)',
          accent: 'rgb(var(--app-accent) / <alpha-value>)',
          'accent-strong': 'rgb(var(--app-accent-strong) / <alpha-value>)',
          'brand-2': 'rgb(var(--app-brand-2) / <alpha-value>)',
          'brand-3': 'rgb(var(--app-brand-3) / <alpha-value>)',
          success: 'rgb(var(--app-success) / <alpha-value>)',
        },
      },
      fontFamily: {
        sans: [
          'Inter',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'Roboto',
          'Helvetica Neue',
          'Arial',
          'sans-serif',
        ],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'Liberation Mono', 'monospace'],
      },
      boxShadow: {
        card: '0 10px 40px -12px rgba(2, 6, 23, 0.12)',
        lifted: '0 18px 48px -12px rgba(2, 6, 23, 0.18), 0 2px 8px -2px rgba(2, 6, 23, 0.08)',
        'glow-accent': '0 12px 40px -8px rgba(99, 102, 241, 0.35), 0 0 0 1px rgba(99, 102, 241, 0.12)',
        'glow-field': '0 0 0 3px rgba(99, 102, 241, 0.18), 0 8px 24px -8px rgba(99, 102, 241, 0.25)',
      },
    },
  },
  plugins: [],
}