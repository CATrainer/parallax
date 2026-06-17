"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import type { WatchlistOut } from "@/lib/types";
import { Eyebrow, EmptyState, ErrorState, Loading } from "@/components/primitives";
import { bandWord, isSignal } from "@/lib/format";

const STATUS_COPY: Record<string, string> = {
  pursuing: "Pursuing",
  watching: "Watching",
  dead: "Dead",
};

function StatusControl({
  item,
  onChange,
  busy,
}: {
  item: WatchlistOut;
  onChange: (status: "pursuing" | "dead") => void;
  busy: boolean;
}) {
  // Only pursuing|dead are settable via /status (watching is the default save).
  const current = item.status;
  return (
    <div className="flex items-center gap-2">
      <span className="text-ink-3 text-sm mr-1">
        {STATUS_COPY[current] ?? current}
      </span>
      <button
        type="button"
        className="text-sm text-ink-2 hover:text-ink transition-colors disabled:opacity-40"
        onClick={() => onChange("pursuing")}
        disabled={busy || current === "pursuing"}
      >
        Pursue
      </button>
      <span className="text-line-2">·</span>
      <button
        type="button"
        className="text-sm text-ink-2 hover:text-ink transition-colors disabled:opacity-40"
        onClick={() => onChange("dead")}
        disabled={busy || current === "dead"}
      >
        Mark dead
      </button>
    </div>
  );
}

export default function WatchlistPage() {
  const { token, ready } = useRequireAuth();
  const [items, setItems] = useState<WatchlistOut[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await api.watchlist();
      setItems(list);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Couldn’t load your watchlist. Try again shortly.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (ready && token) load();
  }, [ready, token, load]);

  async function changeStatus(item: WatchlistOut, status: "pursuing" | "dead") {
    setBusyId(item.id);
    try {
      await api.setStatus(item.site_uprn, status);
      setItems((cur) =>
        cur
          ? cur.map((x) => (x.id === item.id ? { ...x, status } : x))
          : cur,
      );
    } catch {
      // Reload to reflect true state on failure.
      load();
    } finally {
      setBusyId(null);
    }
  }

  if (!ready || !token) return null;

  return (
    <div className="pt-10">
      <Eyebrow className="mb-3">Watchlist</Eyebrow>
      <h1 className="font-serif text-3xl mb-2">What you’re tracking</h1>
      <p className="text-ink-2 max-w-reading leading-relaxed mb-6">
        Sites you’ve saved. Move them to pursuing or mark them dead — your calls
        train what the engine surfaces next.
      </p>

      <div className="max-w-reading mt-6">
        {loading ? (
          <Loading label="Loading your watchlist" />
        ) : error ? (
          <ErrorState message={error} onRetry={load} />
        ) : items && items.length > 0 ? (
          <ul className="list-none p-0 m-0">
            {items.map((item) => {
              const sealed = isSignal(item.band);
              return (
                <li
                  key={item.id}
                  className="py-5 border-t border-line first:border-t-0"
                >
                  <div className="flex items-baseline justify-between gap-4">
                    <Link
                      href={`/sites/${encodeURIComponent(item.site_uprn)}`}
                      className="font-serif text-lg text-ink no-underline hover:underline decoration-line-2 underline-offset-4"
                    >
                      {item.address || item.site_uprn}
                    </Link>
                    {item.conviction !== null &&
                    item.conviction !== undefined ? (
                      <span
                        className={
                          sealed
                            ? "eyebrow text-seal shrink-0"
                            : "eyebrow text-ink-3 shrink-0"
                        }
                      >
                        {bandWord(item.band)} · {item.conviction}
                      </span>
                    ) : null}
                  </div>
                  {item.note ? (
                    <p className="text-ink-2 text-[0.95rem] mt-1">{item.note}</p>
                  ) : null}
                  <div className="mt-2">
                    <StatusControl
                      item={item}
                      busy={busyId === item.id}
                      onChange={(s) => changeStatus(item, s)}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        ) : (
          <EmptyState
            title="Nothing saved yet"
            body="When a briefing looks worth tracking, add it to your watchlist. It’ll collect here so you can pursue or close it off later."
            action={
              <Link href="/patch" className="btn btn-secondary no-underline">
                Go to your patch
              </Link>
            }
          />
        )}
      </div>
    </div>
  );
}
