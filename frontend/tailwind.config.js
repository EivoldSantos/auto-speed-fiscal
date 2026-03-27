/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./app/**/*.{js,ts,jsx,tsx}', './components/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        bg:      '#0f1117',
        bg2:     '#161922',
        bg3:     '#1e2330',
        border:  '#2a3040',
        border2: '#3a4560',
        green:   '#00d084',
        red:     '#ff4757',
        amber:   '#ffb347',
        blue:    '#4da6ff',
        purple:  '#b088ff',
      },
      fontFamily: {
        mono: ['"IBM Plex Mono"', 'monospace'],
        sans: ['"IBM Plex Sans"', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
