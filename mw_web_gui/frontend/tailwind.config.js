/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts}'],
  theme: {
    extend: {
      colors: {
        panel: '#1a1f2e',
        accent: '#3b82f6',
      },
    },
  },
  plugins: [],
};
