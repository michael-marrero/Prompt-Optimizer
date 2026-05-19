// Vitest setup file — runs once before every test file.
// PATTERNS analog: apps/api/tests/conftest.py.
import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});
