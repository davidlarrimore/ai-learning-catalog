/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          primary: "#0077ff",
          surface: "#111827"
        }
      },
      boxShadow: {
        soft: "0 20px 35px -15px rgba(15, 23, 42, 0.45)"
      }
    }
  },
  plugins: []
};
