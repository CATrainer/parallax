"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import type { BriefingOut, ValidationOut } from "@/lib/types";
import { Conviction } from "@/components/Conviction";
import { SignalList } from "@/components/SignalList";
import { OwnershipBlock } from "@/components/OwnershipBlock";
import { PropertyFacts } from "@/components/PropertyFacts";
import { BriefingProse } from "@/components/BriefingProse";
import { ActionBar } from "@/components/ActionBar";
import { ValidationResult } from "@/components/ValidationResult";
import { Eyebrow, ErrorState, Loading } from "@/components/primitives";
import { humanise, freshness } from "@/lib/format";

type ValidationPhase = "idle" | "running" | "done" | "error";

export default function BriefingPage() {
  const { token, ready } = useRequireAuth();
  const params = useParams<{ uprn: string }>();
  const uprn = params.uprn;

  const [briefing, setBriefing] = useState<BriefingOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Validation flow state
  const [phase, setPhase] = useState<ValidationPhase>("idle");
  const [validation, setValidation] = useState<ValidationOut | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  // Watchlist state
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // keep a ref of phase for the timeout closure
  const phaseRef = useRef<ValidationPhase>("idle");
  useEffect(() => {
    phaseRef.current = phase;
  }, [phase]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const b = await api.briefing(uprn);
      setBriefing(b);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Couldn’t load this briefing. Try again shortly.",
      );
    } finally {
      setLoading(false);
    }
  }, [uprn]);

  useEffect(() => {
    if (ready && token) load();
  }, [ready, token, load]);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  async function onValidate() {
    setPhase("running");
    setValidationError(null);
    setValidation(null);
    try {
      const job = await api.startValidation(uprn);
      // Poll the validation result until it settles.
      let settled = false;
      pollRef.current = setInterval(async () => {
        try {
          const result = await api.validation(job.id);
          if (
            result.status === "complete" ||
            result.status === "done" ||
            result.status === "failed" ||
            result.status === "error"
          ) {
            settled = true;
            if (pollRef.current) clearInterval(pollRef.current);
            setValidation(result);
            setPhase(result.error ? "error" : "done");
          }
        } catch (err) {
          if (pollRef.current) clearInterval(pollRef.current);
          setValidationError(
            err instanceof ApiError
              ? err.message
              : "Validation couldn’t complete. Your credits weren’t charged.",
          );
          setPhase("error");
        }
      }, 1500);

      // Safety stop after ~45s.
      setTimeout(() => {
        if (!settled && pollRef.current) {
          clearInterval(pollRef.current);
          if (phaseRef.current === "running") {
            setValidationError(
              "Validation is taking longer than expected. Check back shortly — your result will appear here.",
            );
            setPhase("error");
          }
        }
      }, 45_000);
    } catch (err) {
      setValidationError(
        err instanceof ApiError
          ? err.message
          : "Couldn’t start validation. Try again.",
      );
      setPhase("error");
    }
  }

  async function onAddToWatchlist() {
    setSaving(true);
    setSaveError(null);
    try {
      await api.addToWatchlist(uprn, "watching");
      setSaved(true);
    } catch (err) {
      setSaveError(
        err instanceof ApiError
          ? err.message
          : "Couldn’t add to your watchlist. Try again.",
      );
    } finally {
      setSaving(false);
    }
  }

  if (!ready || !token) return null;

  if (loading) {
    return (
      <div className="pt-10">
        <Loading label="Synthesising the briefing" />
      </div>
    );
  }

  if (error || !briefing) {
    return (
      <div className="pt-10">
        <ErrorState
          message={error || "This briefing isn’t available."}
          onRetry={load}
        />
      </div>
    );
  }

  const b = briefing;
  const site = b.site;
  const signalCount = b.signals.filter((s) => s.fired).length;

  // Eyebrow: provenance — source(s) + freshness
  const sources = Array.from(new Set(b.signals.map((s) => s.source))).slice(0, 4);
  const provenance =
    (sources.length ? sources.join(" · ") : "Parallax synthesis") +
    (b.computed_at ? ` · synthesised ${freshness(b.computed_at)}` : "") +
    (b.is_stale ? " · refreshing" : "");

  // Subtitle: the facts line
  const factBits = [
    site.property_type ? humanise(site.property_type) : null,
    site.tenure ? humanise(site.tenure) : null,
    site.postcode,
    site.local_authority,
  ].filter(Boolean);

  return (
    <article className="pt-10">
      {/* eyebrow → provenance */}
      <Eyebrow className="mb-4">{provenance}</Eyebrow>

      {/* serif title → address */}
      <h1 className="font-serif text-[2.1rem] sm:text-4xl leading-tight mb-2 max-w-reading">
        {site.address}
      </h1>

      {/* subtitle → facts line */}
      <p className="text-ink-2 mb-6">
        {factBits.join(" · ")}
        {factBits.length ? " · " : ""}
        <span className="ref">{site.uprn}</span>
      </p>

      {/* verdict line → the one --seal use */}
      <Conviction
        band={b.band}
        conviction={b.conviction}
        signalCount={signalCount || b.signals.length}
        headlineOpportunity={b.headline_opportunity}
      />

      {/* THE FINDING */}
      <div className="mt-10">
        <BriefingProse
          lede={b.lede}
          paragraphs={b.paragraphs}
          takeaway={b.takeaway}
          signals={b.signals}
        />
      </div>

      {/* Conclusions (manufactured, phrased as inference) */}
      {b.conclusions.length ? (
        <section className="pt-8 mt-8 border-t border-line max-w-reading">
          <Eyebrow className="mb-4">What we think is going on</Eyebrow>
          <ul className="list-none p-0 m-0">
            {b.conclusions.map((c, i) => (
              <li key={i} className="py-3 border-t border-line first:border-t-0">
                <p className="text-ink leading-relaxed">{c.statement}</p>
                <p className="text-ink-3 text-sm mt-0.5">
                  {humanise(c.type)} · confidence {c.confidence.toFixed(2)}
                </p>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {/* Signals */}
      <section className="pt-8 mt-8 border-t border-line max-w-reading">
        <Eyebrow className="mb-4">Signals · what the engine checked</Eyebrow>
        <SignalList signals={b.signals} />
      </section>

      {/* Ownership */}
      <section className="pt-8 mt-8 border-t border-line max-w-reading">
        <Eyebrow className="mb-4">Ownership</Eyebrow>
        <OwnershipBlock ownership={b.ownership} />
      </section>

      {/* Property facts */}
      <section className="pt-8 mt-8 border-t border-line max-w-reading">
        <Eyebrow className="mb-4">Property facts</Eyebrow>
        <PropertyFacts site={site} />
      </section>

      {/* Action bar — docked inline at the page bottom, never overlapping */}
      <div className="max-w-reading">
        <ActionBar
          primaryLabel={
            phase === "running" ? "Validating…" : "Validate this briefing"
          }
          onPrimary={onValidate}
          primaryDisabled={phase === "running"}
          secondaryLabel={saved ? "Added to watchlist" : "Add to watchlist"}
          onSecondary={onAddToWatchlist}
          secondaryDisabled={saving || saved}
          note={
            phase === "idle" && !saved
              ? "Validation spends credits to confirm ownership, occupancy and a contact route — materially more than this free briefing."
              : saved
                ? "Saved. Find it under Watchlist."
                : undefined
          }
        >
          {saveError ? (
            <p className="text-seal text-sm mt-2" role="alert">
              {saveError}
            </p>
          ) : null}

          {phase === "running" ? (
            <p className="text-ink-2 text-sm mt-4" aria-live="polite">
              Spending the validation budget in cost order — deeper records
              first, paid checks only where conviction justifies it.
            </p>
          ) : null}

          {phase === "error" && validationError ? (
            <p className="text-seal text-sm mt-4" role="alert">
              {validationError}
            </p>
          ) : null}

          {validation && phase === "done" ? (
            <ValidationResult result={validation} />
          ) : null}
        </ActionBar>
      </div>
    </article>
  );
}
