// Root layout — SERVER component (no "use client" directive per PATTERNS Pattern D
// exception). Mounts the global Plasma font stack (Phase 7 Plan 07-02), the
// next-themes ThemeProvider that drives the dormant .theme-* class on <html>
// (O-7/D-07 — default Plasma, alternates dormant), the sonner Toaster (UI-SPEC
// §10.5 toasts are dispatched from anywhere in the client tree), and the Next 16
// metadata block. The chat surface itself is a client component mounted by
// app/page.tsx; this file deliberately stays minimal so React 19 server rendering
// owns the initial HTML.
import type { Metadata } from "next";
import { Instrument_Sans, Inter_Tight, JetBrains_Mono } from "next/font/google";
import { ThemeProvider } from "next-themes";
import { Toaster } from "@/components/ui/sonner";
import "./globals.css";

// Phase 7 §Typography (LOCKED) — display = Instrument Sans, body = Inter Tight,
// mono = JetBrains Mono. next/font/google self-hosts these at build time (no
// per-request Google fetch — threat T-07-03). CSS vars are consumed by
// globals.css (--display / body / --mono).
const display = Instrument_Sans({
  variable: "--font-display",
  subsets: ["latin"],
});

const body = Inter_Tight({
  variable: "--font-body",
  subsets: ["latin"],
});

const mono = JetBrains_Mono({
  variable: "--font-mono-plasma",
  subsets: ["latin"],
});

// UI-SPEC §16 — browser tab is "Prompt-Optimizer"; description matches
// PROJECT.md core value. No mid-stream title mutation (kept stable).
export const metadata: Metadata = {
  title: "Prompt-Optimizer",
  description:
    "Quality-first prompt router that picks the right LLM for every question.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    // suppressHydrationWarning — next-themes writes the theme class on <html>
    // before React hydrates, so the server/client class mismatch is expected.
    <html
      lang="en"
      className={`${display.variable} ${body.variable} ${mono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      {/* Token-driven bg/color comes from globals.css (body rule). The old
          Phase-4 slate/white utility classes are gone — they would fight the
          Carbon dark theme. */}
      <body className="min-h-full flex flex-col">
        {/* O-7/D-07 — attribute="class" + the value map write the active theme
            as a .theme-* class on <html> to match the globals.css selectors
            (RESEARCH §5). Plasma maps to .theme-plasma (a harmless no-op class;
            :root supplies the Plasma defaults). Default Plasma, the four
            alternates ship dormant. enableSystem is false (Plasma is the fixed
            default, not OS-driven). */}
        <ThemeProvider
          attribute="class"
          themes={["plasma", "citrus", "tide", "bauhaus", "carbon"]}
          value={{
            plasma: "theme-plasma",
            citrus: "theme-citrus",
            tide: "theme-tide",
            bauhaus: "theme-bauhaus",
            carbon: "theme-carbon",
          }}
          defaultTheme="plasma"
          enableSystem={false}
        >
          {children}
          {/* sonner Toaster — UI-SPEC §10.5 toasts render here. */}
          <Toaster />
        </ThemeProvider>
      </body>
    </html>
  );
}
