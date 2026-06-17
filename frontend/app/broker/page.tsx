"use client";

import { useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import type { BrokerEnrichOut } from "@/lib/types";
import { Eyebrow, ErrorState, Loading } from "@/components/primitives";
import { bandWord, isSignal } from "@/lib/format";

export default function BrokerPage() {
  const { token, ready } = useRequireAuth();
  const [raw, setRaw] = useState("");
  const [result, setResult] = useState<BrokerEnrichOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function enrich() {
    const addresses = raw
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    if (!addresses.length) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.brokerEnrich(addresses);
      setResult(res);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Couldn’t enrich that list. Try again shortly.",
      );
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  if (!ready || !token) return null;

  return (
    <div className="pt-10">
      <Eyebrow className="mb-3">Broker console</Eyebrow>
      <h1 className="font-serif text-3xl mb-2">Enrich a contact list</h1>
      <p className="text-ink-2 max-w-reading leading-relaxed mb-6">
        Paste a list of addresses, one per line. The engine reads each owner’s
        situation and returns a transaction-likelihood briefing — who looks
        close to a mortgage event, and why.
      </p>

      <div className="max-w-reading">
        <label htmlFor="list" className="block text-sm text-ink-2 mb-1.5">
          Addresses
        </label>
        <textarea
          id="list"
          className="field"
          rows={6}
          placeholder={"14 Mill Lane, Leeds LS6 2AB\n8 Tinshill Road, Leeds LS16"}
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
        />
        <div className="mt-3">
          <button
            type="button"
            className="btn btn-primary"
            onClick={enrich}
            disabled={loading || !raw.trim()}
          >
            {loading ? "Reading situations…" : "Enrich list"}
          </button>
        </div>
      </div>

      <div className="mt-10">
        {loading ? (
          <Loading label="Reading owner situations" />
        ) : error ? (
          <ErrorState message={error} />
        ) : result ? (
          result.rows.length ? (
            <div>
              <Eyebrow className="mb-4">
                {result.total} address{result.total === 1 ? "" : "es"} read
              </Eyebrow>
              <ul className="list-none p-0 m-0">
                {result.rows.map((row, i) => {
                  const sealed = isSignal(row.band);
                  const inner = (
                    <>
                      <div className="flex items-baseline justify-between gap-4">
                        <h3 className="font-serif text-lg text-ink">
                          {row.resolved_address || row.input_address}
                        </h3>
                        <span
                          className={
                            sealed
                              ? "eyebrow text-seal shrink-0"
                              : "eyebrow text-ink-3 shrink-0"
                          }
                        >
                          {bandWord(row.band)} · {row.transaction_likelihood}
                        </span>
                      </div>
                      <p className="text-ink-2 leading-relaxed mt-1.5 max-w-reading">
                        {row.rationale}
                      </p>
                      {row.signal_summary.length ? (
                        <p className="text-ink-3 text-sm mt-1.5">
                          {row.signal_summary.join(" · ")}
                        </p>
                      ) : null}
                      {row.uprn ? (
                        <p className="text-ink-3 text-sm mt-1">
                          <span className="ref">{row.uprn}</span>
                        </p>
                      ) : (
                        <p className="text-ink-3 text-sm mt-1">
                          Didn’t resolve to a UPRN — check the address.
                        </p>
                      )}
                    </>
                  );
                  return (
                    <li
                      key={`${row.input_address}-${i}`}
                      className="py-6 border-t border-line first:border-t-0"
                    >
                      {row.uprn ? (
                        <Link
                          href={`/broker/site/${encodeURIComponent(row.uprn)}`}
                          className="block no-underline group"
                        >
                          {inner}
                        </Link>
                      ) : (
                        inner
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : (
            <p className="text-ink-3 max-w-reading">
              None of those resolved to sites the engine can read. Check the
              addresses include a postcode.
            </p>
          )
        ) : (
          <p className="text-ink-3 max-w-reading">
            Enriched rows appear here, each linking to the owner-situation
            intelligence for that site.
          </p>
        )}
      </div>
    </div>
  );
}
