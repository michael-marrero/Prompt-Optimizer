// shadcn convention helper: compose conditional class names with clsx then
// resolve Tailwind v4 conflicts with tailwind-merge. Used by every component
// that builds a dynamic className. Plan 04-01 PATTERNS Pattern E.
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
