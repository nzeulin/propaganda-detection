import { defineConfig } from "vite";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [tailwindcss()],
  server: {
    proxy: Object.fromEntries(
      ["/analyze", "/examples", "/health", "/api"].map((path) => [
        path,
        "http://127.0.0.1:8000",
      ]),
    ),
  },
});
