"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import type { SearchResult } from "@/lib/types";
import { Eyebrow, EmptyState, ErrorState, Loading } from "@/components/primitives";
import { bandWord, isSignal } from "@/lib/format";

function kindLabel(kind: SearchResult["kind"]): string {
  if (kind === "site") return "Site";
  if (kind === "company") return "Company";
  return "Person";
}

function ResultRow({ result }: { result: SearchResult }) {
  const sealed = isSignal(result.band);
  const body = (
    <>
      <div className="flex items-baseline justify-between gap-4">
        <h3 className="font-serif text-lg text-ink">{result.label}</h3>
        {result.conviction !== null && result.conviction !== undefined ? (
          <span
            className={
              sealed ? "eyebrow text-seal shrink-0" : "eyebrow text-ink-3 shrink-0"
            }
          >
            {bandWord(result.band)} · {result.conviction}
          </span>
        ) : null}
      </div>
      <p className="text-ink-3 text-sm mt-1">
        {kindLabel(result.kind)}
        {result.sublabel ? ` · ${result.sublabel}` : ""}
      </p>
    </>
  );

  // Site-first: sites link to their briefing; non-sites are shown for context.
  if (result.kind === "site" && result.uprn) {
    return (
      <Link
        href={`/sites/${encodeURIComponent(result.uprn)}`}
        className="block py-5 border-t border-line first:border-t-0 no-underline group"
      >
        {body}
      </Link>
    );
  }
  return (
    <div className="py-5 border-t border-line first:border-t-0">{body}</div>
  );
}

export default function SearchPage() {
  const { token, ready } = useRequireAuth();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const query = q.trim();
    if (!query) return;
    setLoading(true);
    setError(null);
    setSearched(true);
    try {
      const res = await api.search(query);
      // Site-first ordering.
      const ordered = [...res].sort(
        (a, b) =>
          Number(b.kind === "site") - Number(a.kind === "site") ||
          (b.conviction ?? -1) - (a.conviction ?? -1),
      );
      setResults(ordered);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Search failed. Try again in a moment.",
      );
      setResults(null);
    } finally {
      setLoading(false);
    }
  }

  if (!ready || !token) return null;

  return (
    <div className="pt-10">
      <Eyebrow className="mb-3">Search · pull entry</Eyebrow>
      <h1 className="font-serif text-3xl mb-2">Look up a site</h1>
      <p className="text-ink-2 max-w-reading leading-relaxed mb-6">
        Enter an address, a postcode, a company, or an owner. The engine
        resolves it to sites and returns a briefing on demand.
      </p>

      <form onSubmit={onSubmit} className="max-w-reading flex gap-3 mb-2">
        <input
          className="field"
          placeholder="14 Mill Lane, LS6 — or a company name"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label="Search"
        />
        <button type="submit" className="btn btn-primary shrink-0" disabled={loading}>
          Search
        </button>
      </form>

      <div className="mt-6 max-w-reading">
        {loading ? (
          <Loading label="Resolving" />
        ) : error ? (
          <ErrorState message={error} />
        ) : results && results.length > 0 ? (
          <div>
            {results.map((r, i) => (
              <ResultRow key={`${r.kind}-${r.uprn ?? r.label}-${i}`} result={r} />
            ))}
          </div>
        ) : searched ? (
          <EmptyState
            title="Nothing resolved for that"
            body="The engine couldn’t match that to a site. Try a fuller address with a postcode, or a registered company name."
            action={null}
          />
        ) : (
          <p className="text-ink-3">
            Results appear here, sites first.
          </p>
        )}
      </div>
    </div>
  );
}
