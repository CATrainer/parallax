"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import type { BrokerIntelligenceOut } from "@/lib/types";
import { OwnershipBlock } from "@/components/OwnershipBlock";
import { PropertyFacts } from "@/components/PropertyFacts";
import { Eyebrow, ErrorState, Loading } from "@/components/primitives";
import { bandWord, isSignal } from "@/lib/format";

export default function BrokerIntelligencePage() {
  const { token, ready } = useRequireAuth();
  const params = useParams<{ uprn: string }>();
  const uprn = params.uprn;

  const [intel, setIntel] = useState<BrokerIntelligenceOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.brokerIntelligence(uprn);
      setIntel(res);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Couldn’t load this intelligence. Try again shortly.",
      );
    } finally {
      setLoading(false);
    }
  }, [uprn]);

  useEffect(() => {
    if (ready && token) load();
  }, [ready, token, load]);

  if (!ready || !token) return null;

  if (loading) {
    return (
      <div className="pt-10">
        <Loading label="Reading the owner situation" />
      </div>
    );
  }

  if (error || !intel) {
    return (
      <div className="pt-10">
        <ErrorState
          message={error || "This intelligence isn’t available."}
          onRetry={load}
        />
      </div>
    );
  }

  const sealed = isSignal(intel.band);

  return (
    <article className="pt-10">
      <Eyebrow className="mb-4">
        Broker intelligence ·{" "}
        <Link href="/broker" className="text-ink-3 hover:text-ink no-underline">
          back to console
        </Link>
      </Eyebrow>

      <h1 className="font-serif text-[2.1rem] sm:text-4xl leading-tight mb-2 max-w-reading">
        {intel.site.address}
      </h1>
      <p className="text-ink-2 mb-6">
        {intel.site.postcode ? `${intel.site.postcode} · ` : ""}
        <span className="ref">{intel.site.uprn}</span>
      </p>

      {/* The one --seal moment: mortgage-event likelihood */}
      <p className="font-serif text-lg leading-relaxed text-ink-2 max-w-reading">
        <span
          className={
            sealed
              ? "text-seal font-medium tracking-wide"
              : "text-ink font-medium tracking-wide"
          }
        >
          {bandWord(intel.band)}
        </span>
        <span> · mortgage-event likelihood </span>
        <span className="text-ink">{intel.mortgage_event_likelihood}</span>
        <span>. {intel.owner_situation}</span>
      </p>

      {intel.drivers.length ? (
        <section className="pt-8 mt-8 border-t border-line max-w-reading">
          <Eyebrow className="mb-4">What’s driving it</Eyebrow>
          <ul className="list-none p-0 m-0">
            {intel.drivers.map((d, i) => (
              <li
                key={i}
                className="py-3 border-t border-line first:border-t-0 text-ink leading-relaxed"
              >
                {d}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="pt-8 mt-8 border-t border-line max-w-reading">
        <Eyebrow className="mb-4">Ownership</Eyebrow>
        <OwnershipBlock ownership={intel.ownership} />
      </section>

      <section className="pt-8 mt-8 border-t border-line max-w-reading">
        <Eyebrow className="mb-4">Property facts</Eyebrow>
        <PropertyFacts site={intel.site} />
      </section>
    </article>
  );
}
