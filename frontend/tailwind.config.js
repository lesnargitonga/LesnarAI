/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'navy-black': '#05070A',
        'cyber-gray': '#12161F',
        'lesnar-accent': '#00FDFF', // Brighter Cyan
        'lesnar-danger': '#FF1F6D', // Brighter Pink/Red
        'lesnar-warning': '#FFCE00', // Brighter Yellow
        'lesnar-success': '#00FF9D', // Brighter Green
        'lesnar': {
          'primary': '#00F5FF',
          'secondary': '#764ba2',
          'accent': '#f093fb',
        }
      },
      boxShadow: {
        'neo-glow': '0 0 15px rgba(0, 245, 255, 0.3)',
        'glass': '0 8px 32px 0 rgba(0, 0, 0, 0.37)',
        'drone-flying': '0 0 10px rgba(34, 197, 94, 0.5)',
      },
      animation: {
        'glow': 'glow 2s ease-in-out infinite alternate',
        'pulse-slow': 'pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'scan': 'scan 3s linear infinite',
      },
      keyframes: {
        glow: {
          '0%': { boxShadow: '0 0 5px rgba(0, 245, 255, 0.2), 0 0 10px rgba(0, 245, 255, 0.1)' },
          '100%': { boxShadow: '0 0 20px rgba(0, 245, 255, 0.6), 0 0 30px rgba(0, 245, 255, 0.4)' },
        },
        scan: {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100%)' },
        }
      }
    },
  },
  plugins: [],
}
