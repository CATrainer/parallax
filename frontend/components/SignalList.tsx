import type { SignalOut } from "@/lib/types";
import { humanise, freshness } from "@/lib/format";

// Typeset list, hairline-separated (§9.3). Firing signals carry a --seal pip;
// checked-but-not-firing signals are dimmed but SHOWN — the engine shows its
// working, including what it looked for and didn't find.

function SignalRow({ signal }: { signal: SignalOut }) {
  const firing = signal.fired;
  return (
    <li
      id={`signal-${signal.id}`}
      className="py-3.5 border-t border-line first:border-t-0 scroll-mt-24"
    >
      <div className="flex items-baseline gap-3">
        <span
          aria-hidden
          className="mt-2 shrink-0"
          style={{
            width: 7,
            height: 7,
            borderRadius: 9999,
            backgroundColor: firing ? "var(--seal)" : "transparent",
            border: firing ? "none" : "1px solid var(--line-2)",
            display: "inline-block",
          }}
        />
        <div className="min-w-0">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span
              className={
                firing
                  ? "text-ink font-medium"
                  : "text-ink-3 font-medium"
              }
            >
              {humanise(signal.signal_type)}
            </span>
            {!firing ? (
              <span className="text-ink-3 text-sm">checked · not firing</span>
            ) : (
              <span className="text-ink-3 text-sm">
                strength {signal.strength.toFixed(2)}
              </span>
            )}
          </div>
          {firing ? (
            <p className="text-ink-2 text-[0.95rem] mt-1 leading-relaxed">
              {signal.raw_evidence}
            </p>
          ) : null}
          {firing ? (
            <p className="text-ink-3 text-sm mt-1">
              {signal.source}
              {signal.observed_at ? ` · ${freshness(signal.observed_at)}` : ""}
              {signal.source_ref ? (
                <>
                  {" · "}
                  <span className="ref">{signal.source_ref}</span>
                </>
              ) : null}
            </p>
          ) : null}
        </div>
      </div>
    </li>
  );
}

export function SignalList({ signals }: { signals: SignalOut[] }) {
  if (!signals.length) {
    return (
      <p className="text-ink-3">No signals recorded against this site yet.</p>
    );
  }
  // Firing first, then checked-not-firing (shown, dimmed).
  const ordered = [...signals].sort(
    (a, b) => Number(b.fired) - Number(a.fired) || b.strength - a.strength,
  );
  return (
    <ul className="list-none p-0 m-0">
      {ordered.map((s) => (
        <SignalRow key={s.id} signal={s} />
      ))}
    </ul>
  );
}
