/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'SF Pro Display', 'system-ui', 'sans-serif'],
        mono: ['SF Mono', 'JetBrains Mono', 'Menlo', 'Consolas', 'monospace'],
      },
      fontSize: {
        '2xs': ['11px', '14px'],
        xs: ['12px', '16px'],
        sm: ['13px', '18px'],
        base: ['14px', '20px'],
        md: ['16px', '22px'],
        lg: ['18px', '24px'],
        xl: ['22px', '28px'],
      },
      colors: {
        ink: {
          50: '#F7F7F8',
          100: '#EEEEF0',
          200: '#D9D9DE',
          300: '#A3A3AC',
          400: '#6E6E78',
          500: '#4A4A52',
          600: '#2E2E33',
          700: '#1F1F23',
          800: '#17171A',
          850: '#121214',
          900: '#0C0C0E',
          950: '#08080A',
        },
        accent: {
          DEFAULT: '#7C5CFF',
          hover: '#8E72FF',
          soft: 'rgba(124, 92, 255, 0.14)',
          ring: 'rgba(124, 92, 255, 0.35)',
        },
      },
      borderRadius: {
        DEFAULT: '7px',
      },
      boxShadow: {
        soft: '0 1px 2px rgba(0,0,0,0.3), 0 0 0 1px rgba(255,255,255,0.04)',
        pop: '0 8px 24px rgba(0,0,0,0.45), 0 0 0 1px rgba(255,255,255,0.06)',
      },
      transitionTimingFunction: {
        'out-soft': 'cubic-bezier(0.22, 1, 0.36, 1)',
      },
      keyframes: {
        pulseSoft: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.55' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        pulseSoft: 'pulseSoft 1.6s ease-in-out infinite',
        shimmer: 'shimmer 2.4s linear infinite',
        fadeIn: 'fadeIn 160ms cubic-bezier(0.22, 1, 0.36, 1)',
      },
    },
  },
  plugins: [],
};
