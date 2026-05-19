// Root layout — SERVER component (no "use client" directive per PATTERNS Pattern D
// exception). Mounts the global font stack, the sonner Toaster (UI-SPEC §10.5
// toasts are dispatched from anywhere in the client tree), and the Next 16
// metadata block. The chat surface itself is a client component mounted by
// app/page.tsx; this file deliberately stays minimal so React 19 server rendering
// owns the initial HTML.
import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Toaster } from "@/components/ui/sonner";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
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
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-white text-slate-900">
        {children}
        {/* sonner Toaster — UI-SPEC §10.5 toasts render here. */}
        <Toaster />
      </body>
    </html>
  );
}
