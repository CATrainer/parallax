import Link from "next/link";
import type { BriefingCard as BriefingCardData } from "@/lib/types";
import { bandWord, isSignal, humanise, freshness } from "@/lib/format";

// Compact card for feeds (patch + search). Reads as an entry in a briefing
// digest, not a dashboard tile — hairline-separated, content-first.

export function BriefingCard({ card }: { card: BriefingCardData }) {
  const sealed = isSignal(card.band);
  return (
    <Link
      href={`/sites/${encodeURIComponent(card.site_uprn)}`}
      className="block group py-7 border-t border-line first:border-t-0 no-underline"
    >
      <div className="flex items-baseline justify-between gap-4">
        <h3 className="font-serif text-xl text-ink group-hover:underline decoration-line-2 underline-offset-4">
          {card.address}
        </h3>
        <span
          className={
            sealed
              ? "eyebrow text-seal shrink-0"
              : "eyebrow text-ink-3 shrink-0"
          }
        >
          {bandWord(card.band)} · {card.conviction}
        </span>
      </div>
      <p className="text-ink-2 leading-relaxed mt-2 max-w-reading">
        {card.lede}
      </p>
      <p className="text-ink-3 text-sm mt-2.5">
        {card.headline_opportunity
          ? humanise(card.headline_opportunity)
          : "Opportunity"}
        {` · ${card.signal_count} signal${card.signal_count === 1 ? "" : "s"}`}
        {card.postcode ? ` · ${card.postcode}` : ""}
        {card.updated_at ? ` · updated ${freshness(card.updated_at)}` : ""}
      </p>
    </Link>
  );
}
