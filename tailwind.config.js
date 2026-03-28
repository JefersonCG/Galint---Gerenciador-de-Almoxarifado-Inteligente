/** @type {import('tailwindcss').Config} */
module.exports = {
    content: [
        './galint_flask/templates/**/*.html',
        './galint_flask/templates_mako/**/*.mako',
        './galint_flask/static/js/**/*.js',
    ],
    theme: {
        extend: {
            colors: {
                galint: {
                    ink: '#08111f',
                    slate: '#0f172a',
                    steel: '#334155',
                    mist: '#e2e8f0',
                    frost: '#f8fafc',
                    panel: '#111827',
                    panelSoft: '#182235',
                    line: 'rgba(148, 163, 184, 0.22)',
                    primary: '#2563eb',
                    primarySoft: '#38bdf8',
                    success: '#15803d',
                    warning: '#d97706',
                    danger: '#dc2626',
                },
            },
            boxShadow: {
                shell: '0 18px 50px rgba(8, 17, 31, 0.18)',
                panel: '0 14px 38px rgba(15, 23, 42, 0.10)',
                insetline: 'inset 0 1px 0 rgba(255, 255, 255, 0.04)',
            },
            borderRadius: {
                shell: '1.25rem',
            },
            fontFamily: {
                sans: ['IBM Plex Sans', 'Segoe UI', 'sans-serif'],
                mono: ['IBM Plex Mono', 'Consolas', 'monospace'],
            },
            backgroundImage: {
                'galint-grid': 'linear-gradient(rgba(148, 163, 184, 0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(148, 163, 184, 0.08) 1px, transparent 1px)',
                'galint-glow': 'radial-gradient(circle at top, rgba(56, 189, 248, 0.18), transparent 48%)',
            },
        },
    },
    plugins: [],
};