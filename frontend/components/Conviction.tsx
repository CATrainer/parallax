import { bandWord, isSignal, humanise } from "@/lib/format";

// The ONE --seal moment of a briefing (§9.3): the conviction word + number +
// a decomposition sentence. The seal carries weight precisely because colour
// appears once per view.

export function Conviction({
  band,
  conviction,
  signalCount,
  headlineOpportunity,
}: {
  band: string;
  conviction: number;
  signalCount: number;
  headlineOpportunity?: string | null;
}) {
  const word = bandWord(band);
  const sealed = isSignal(band);
  const opportunity = headlineOpportunity
    ? humanise(headlineOpportunity).toLowerCase()
    : null;

  // The decomposition sentence — names how the conviction was reached.
  const sources =
    signalCount === 1
      ? "a single signal — treat as a candidate, not a lead"
      : `${signalCount} corroborating signals`;

  return (
    <div className="font-serif">
      <p className="text-lg leading-relaxed text-ink-2">
        <span
          className={
            sealed
              ? "text-seal font-medium tracking-wide"
              : "text-ink font-medium tracking-wide"
          }
        >
          {word}
        </span>
        <span className="text-ink-2"> · conviction </span>
        <span className="text-ink">{conviction}</span>
        <span className="text-ink-2">
          {opportunity ? `, reading as ${opportunity}, ` : ", "}
          drawn from {sources}.
        </span>
      </p>
    </div>
  );
}
