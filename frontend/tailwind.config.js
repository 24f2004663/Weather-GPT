/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Theme-aware ink and glass tint. Both resolve to CSS variables set from
        // <html data-surface>, so every existing alpha variant (text-ink/70,
        // border-ink/20, bg-ink/10 ...) follows the backdrop automatically.
        ink: 'rgb(var(--ink-rgb) / <alpha-value>)',
        glass: 'rgb(var(--glass-rgb) / <alpha-value>)',
        // `white` is remapped onto the same ink token on purpose. The UI expresses its
        // foreground, borders and tile tints as text-white/border-white/bg-white at
        // various alphas in ~270 places; rebinding the palette entry themes all of them
        // at once instead of rewriting every call site. Anything that must stay literally
        // white — text on a saturated brand button — uses text-[#fff] explicitly.
        white: 'rgb(var(--ink-rgb) / <alpha-value>)',
        brand: {
          50: '#f0f9ff',
          100: '#e0f2fe',
          500: '#0ea5e9',
          600: '#0284c7',
          700: '#0369a1',
          900: '#0c4a6e',
        },
        surface: {
          dark: '#0f172a',
          card: '#1e293b',
          border: '#334155',
        }
      },
      keyframes: {
        slideDown: {
          '0%': { backgroundPosition: '0 0' },
          '100%': { backgroundPosition: '0 400px' },
        },
        lightning: {
          '0%, 95%, 98%': { opacity: '0' },
          '96%, 99%': { opacity: '0.4' },
          '100%': { opacity: '0' },
        }
      },
      animation: {
        slideDown: 'slideDown linear infinite',
        lightning: 'lightning 7s infinite',
      }
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
}
