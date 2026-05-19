// Vitest config — jsdom environment, RTL setup, `@` path alias matching the
// Next.js tsconfig (so imports written for production code resolve identically
// in tests). PATTERNS Pattern A in 04-PATTERNS.md.
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    globals: true,
    // Only collect unit / component tests from tests/. Playwright owns
    // playwright/*.spec.ts and uses its own test runner.
    include: ["tests/**/*.{test,spec}.{ts,tsx}"],
    exclude: ["playwright/**", "node_modules/**", ".next/**"],
  },
  resolve: {
    alias: {
      "@": resolve(__dirname, "."),
    },
  },
});
