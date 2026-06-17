import type { ValidationOut } from "@/lib/types";
import { Eyebrow } from "./primitives";

// The validation delta (§6.4): confirmed ownership + occupancy + contact route
// + a per-check provenance log. It must read as materially more than the free
// briefing — that delta is what the credit buys.

function Fact({ term, value }: { term: string; value: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[10rem_1fr] gap-x-4 py-2.5 border-t border-line first:border-t-0">
      <dt className="text-ink-3 text-sm pt-0.5">{term}</dt>
      <dd className="text-ink">{value}</dd>
    </div>
  );
}

function describe(obj: Record<string, unknown> | null | undefined): string {
  if (!obj) return "—";
  const parts = Object.entries(obj)
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([k, v]) => `${k.replace(/_/g, " ")}: ${String(v)}`);
  return parts.length ? parts.join(" · ") : "—";
}

export function ValidationResult({ result }: { result: ValidationOut }) {
  if (result.error) {
    return (
      <div className="mt-6 max-w-reading">
        <Eyebrow className="mb-2 text-seal">Validation incomplete</Eyebrow>
        <p className="text-ink leading-relaxed">{result.error}</p>
      </div>
    );
  }

  return (
    <div className="mt-8 pt-8 border-t border-line-2 max-w-reading">
      <Eyebrow className="mb-4">
        Validated · {result.credits_spent} credit
        {result.credits_spent === 1 ? "" : "s"} spent
      </Eyebrow>

      <dl className="m-0 mb-8">
        <Fact term="Confirmed owner" value={describe(result.confirmed_ownership)} />
        <Fact term="Occupancy" value={result.occupancy_status || "—"} />
        <Fact term="Contact route" value={describe(result.contact_route)} />
        {result.updated_conviction !== null &&
        result.updated_conviction !== undefined ? (
          <Fact
            term="Conviction now"
            value={
              <span className="text-ink">{result.updated_conviction}</span>
            }
          />
        ) : null}
      </dl>

      {result.provenance_log.length ? (
        <div>
          <Eyebrow className="mb-3">Provenance log</Eyebrow>
          <ul className="list-none p-0 m-0">
            {result.provenance_log.map((entry, i) => (
              <li
                key={`${entry.check}-${i}`}
                className="py-3 border-t border-line first:border-t-0"
              >
                <p className="text-ink">
                  {entry.check}
                  <span className="text-ink-3">
                    {" · "}
                    {entry.source}
                    {entry.cost_credits > 0
                      ? ` · ${entry.cost_credits} credit${entry.cost_credits === 1 ? "" : "s"}`
                      : " · no charge"}
                  </span>
                </p>
                <p className="text-ink-2 text-[0.95rem] mt-0.5">
                  {entry.result}
                </p>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
