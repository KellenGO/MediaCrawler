import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: ['class'],
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // Round 14: 现代浅蓝品牌体系（效果稿 social-search-redesign）
        brand: {
          DEFAULT: 'rgb(var(--brand) / <alpha-value>)',
          strong: 'rgb(var(--brand-2) / <alpha-value>)',
          soft: 'rgb(var(--brand-soft) / <alpha-value>)',
          ink: 'rgb(var(--brand-ink) / <alpha-value>)',
        },
        ok: {
          DEFAULT: 'rgb(var(--ok) / <alpha-value>)',
          soft: 'rgb(var(--ok-soft) / <alpha-value>)',
        },
        warn: {
          DEFAULT: 'rgb(var(--warn) / <alpha-value>)',
          soft: 'rgb(var(--warn-soft) / <alpha-value>)',
        },
        danger: {
          DEFAULT: 'rgb(var(--danger) / <alpha-value>)',
          soft: 'rgb(var(--danger-soft) / <alpha-value>)',
        },
        // Legacy cyber namespace (values now point at the new palette)
        cyber: {
          // Background colors
          bg: {
            primary: 'rgb(var(--cyber-bg-primary) / <alpha-value>)',
            secondary: 'rgb(var(--cyber-bg-secondary) / <alpha-value>)',
            tertiary: 'rgb(var(--cyber-bg-tertiary) / <alpha-value>)',
            panel: 'rgb(var(--cyber-bg-panel) / <alpha-value>)',
            elevated: 'rgb(var(--cyber-bg-elevated) / <alpha-value>)',
            glass: 'rgb(var(--glass-bg))',
            glassDark: 'rgb(var(--glass-dark-bg))',
          },
          // Neon colors
          neon: {
            cyan: 'rgb(var(--cyber-neon-cyan) / <alpha-value>)',
            cyanDim: 'rgb(var(--cyber-neon-cyan-dim) / <alpha-value>)',
            pink: 'rgb(var(--cyber-neon-pink) / <alpha-value>)',
            pinkDim: 'rgb(var(--cyber-neon-pink-dim) / <alpha-value>)',
            green: 'rgb(var(--cyber-neon-green) / <alpha-value>)',
            greenDim: 'rgb(var(--cyber-neon-green-dim) / <alpha-value>)',
            orange: 'rgb(var(--cyber-neon-orange) / <alpha-value>)',
            yellow: 'rgb(var(--cyber-neon-yellow) / <alpha-value>)',
            purple: 'rgb(var(--cyber-neon-purple) / <alpha-value>)',
          },
          // Text colors
          text: {
            primary: 'rgb(var(--cyber-text-primary) / <alpha-value>)',
            secondary: 'rgb(var(--cyber-text-secondary) / <alpha-value>)',
            muted: 'rgb(var(--cyber-text-muted) / <alpha-value>)',
          },
          // Border colors
          border: {
            DEFAULT: 'rgb(var(--cyber-border-default) / <alpha-value>)',
            glow: 'rgb(var(--cyber-border-glow) / <alpha-value>)',
            subtle: 'rgb(var(--cyber-border-subtle) / <alpha-value>)',
          },
        },
        // Keep semantic colors for compatibility
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))',
        },
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
      boxShadow: {
        // Round 14: 柔和阴影（不再有霓虹多层发光）
        'glow-cyan': '0 10px 30px rgba(50,105,145,0.1)',
        'glow-cyan-sm': '0 4px 14px rgba(50,105,145,0.12)',
        'glow-pink': '0 10px 30px rgba(50,105,145,0.1)',
        'glow-pink-sm': '0 4px 14px rgba(50,105,145,0.12)',
        'glow-green': '0 10px 30px rgba(50,105,145,0.1)',
        'glow-green-sm': '0 4px 14px rgba(50,105,145,0.12)',
        'glow-orange': '0 10px 30px rgba(50,105,145,0.1)',
        'cyber-card': '0 10px 30px rgba(50,105,145,0.1)',
        'cyber-inset': 'inset 0 0 20px rgba(0,0,0,0.06)',
        'cyber-soft': '0 4px 18px rgba(50,105,145,0.08)',
        'cyber-float': '0 24px 70px rgba(50,105,145,0.1)',
        'cyber-elevated': '0 24px 70px rgba(50,105,145,0.12)',
      },
      animation: {
        'slide-up': 'slideUp 0.3s ease-out forwards',
        'pulse-fast': 'pulse 1.5s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'pulse-glow': 'pulseGlow 2s ease-in-out infinite',
        'scanline': 'scanline 8s linear infinite',
        'cursor-blink': 'cursorBlink 1s step-end infinite',
        'border-glow': 'borderGlow 3s linear infinite',
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
      },
      keyframes: {
        slideUp: {
          from: { opacity: '0', transform: 'translateY(10px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        pulseGlow: {
          '0%, 100%': {
            boxShadow: '0 0 5px rgb(var(--cyber-neon-cyan) / 0.5), 0 0 10px rgb(var(--cyber-neon-cyan) / 0.3)'
          },
          '50%': {
            boxShadow: '0 0 15px rgb(var(--cyber-neon-cyan) / 0.8), 0 0 25px rgb(var(--cyber-neon-cyan) / 0.5), 0 0 35px rgb(var(--cyber-neon-cyan) / 0.3)'
          },
        },
        scanline: {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100vh)' },
        },
        cursorBlink: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0' },
        },
        borderGlow: {
          '0%, 100%': { borderColor: 'rgb(var(--cyber-neon-cyan) / 0.3)' },
          '50%': { borderColor: 'rgb(var(--cyber-neon-cyan) / 0.6)' },
        },
        'accordion-down': {
          from: { height: '0' },
          to: { height: 'var(--radix-accordion-content-height)' },
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height)' },
          to: { height: '0' },
        },
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
}

export default config
