import type { BriefingParagraph, SignalOut } from "@/lib/types";
import { humanise } from "@/lib/format";

// THE FINDING (§9.3): a serif lede, prose paragraphs each carrying inline
// source refs derived from cited_signal_ids, and the pulled-out "Why it's
// actionable" takeaway. Every claim is sourced; inference reads as inference.

function refLabel(index: number): string {
  // Compact, stable reference token shown inline and footnoted below.
  return `S${index + 1}`;
}

export function BriefingProse({
  lede,
  paragraphs,
  takeaway,
  signals,
}: {
  lede: string;
  paragraphs: BriefingParagraph[];
  takeaway: string;
  signals: SignalOut[];
}) {
  // Map signal id → its index so inline refs are stable and footnotable.
  const indexById = new Map<string, number>();
  signals.forEach((s, i) => indexById.set(s.id, i));

  // Collect the signals actually cited anywhere, in first-appearance order.
  const citedOrder: string[] = [];
  for (const p of paragraphs) {
    for (const id of p.cited_signal_ids) {
      if (!citedOrder.includes(id)) citedOrder.push(id);
    }
  }

  return (
    <div className="max-w-reading">
      {/* Serif lede — the one-sentence conclusion */}
      <p className="font-serif text-2xl leading-snug text-ink mb-6">{lede}</p>

      {paragraphs.map((p, pi) => (
        <p key={pi} className="text-ink leading-relaxed mb-4">
          {p.text}
          {p.cited_signal_ids.map((id) => {
            const idx = indexById.get(id);
            const sig = idx !== undefined ? signals[idx] : undefined;
            return (
              <a
                key={id}
                href={`#signal-${id}`}
                className="source-ref"
                title={
                  sig
                    ? `${humanise(sig.signal_type)} — ${sig.source}`
                    : "source"
                }
              >
                {refLabel(idx ?? 0)}
              </a>
            );
          })}
        </p>
      ))}

      {/* Pulled-out "Why it's actionable" */}
      {takeaway ? (
        <div className="mt-7 pl-5 border-l-2 border-line-2">
          <p className="eyebrow mb-1.5">Why it’s actionable</p>
          <p className="font-serif text-lg leading-relaxed text-ink">
            {takeaway}
          </p>
        </div>
      ) : null}

      {citedOrder.length ? (
        <p className="text-ink-3 text-sm mt-6">
          References above point to the signals listed below.
        </p>
      ) : null}
    </div>
  );
}
