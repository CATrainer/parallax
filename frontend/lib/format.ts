// Display helpers. The wordmark lives here once (BRAND token, §6 brief).

export const BRAND = "Parallax";

/** Bands (§6.4): LOW 0–30 · MONITOR 31–55 · LIKELY 56–80 · STRONG 81–100. */
export type Band = "LOW" | "MONITOR" | "LIKELY" | "STRONG";

export function bandWord(band: string | null | undefined): string {
  if (!band) return "—";
  return band.toUpperCase();
}

/** A band/conviction is a "conviction moment" worthy of the seal when strong. */
export function isSignal(band: string | null | undefined): boolean {
  const b = (band || "").toUpperCase();
  return b === "STRONG" || b === "LIKELY";
}

/** Turn a snake/lower opportunity_type into sentence-case prose. */
export function humanise(value: string | null | undefined): string {
  if (!value) return "";
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^./, (c) => c.toUpperCase());
}

/** Relative freshness, e.g. "updated 3 days ago". Falls back to a date. */
export function freshness(iso: string | null | undefined): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diff = Date.now() - then;
  const day = 86_400_000;
  if (diff < 0) return "just now";
  if (diff < 3_600_000) return "within the hour";
  if (diff < day) return "today";
  const days = Math.round(diff / day);
  if (days === 1) return "yesterday";
  if (days < 30) return `${days} days ago`;
  const months = Math.round(days / 30);
  if (months < 12) return `${months} month${months === 1 ? "" : "s"} ago`;
  const years = Math.round(months / 12);
  return `${years} year${years === 1 ? "" : "s"} ago`;
}

export function confidenceLabel(value: number | null | undefined): string {
  if (value === null || value === undefined) return "";
  return `confidence ${value.toFixed(2)}`;
}
