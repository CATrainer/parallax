"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import type { BriefingCard as BriefingCardData, PatchIn, PatchOut } from "@/lib/types";
import { BriefingCard } from "@/components/BriefingCard";
import { Eyebrow, EmptyState, ErrorState, Loading } from "@/components/primitives";
import { bandWord } from "@/lib/format";

const OPPORTUNITY_TYPES = [
  "probate_inherited",
  "empty_vacant",
  "distressed_owner",
  "below_market",
  "development_planning",
  "portfolio_exit",
  "wrong_use_commercial",
];

function PatchEditor({
  patch,
  onSaved,
}: {
  patch: PatchOut | null;
  onSaved: (p: PatchOut) => void;
}) {
  const [open, setOpen] = useState(false);
  const [postcodes, setPostcodes] = useState(
    (patch?.postcodes ?? []).join(", "),
  );
  const [floor, setFloor] = useState(patch?.conviction_floor ?? 31);
  const [types, setTypes] = useState<string[]>(patch?.opportunity_types ?? []);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggleType(t: string) {
    setTypes((cur) =>
      cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t],
    );
  }

  async function save() {
    setSaving(true);
    setError(null);
    const body: PatchIn = {
      name: patch?.name ?? "My patch",
      postcodes: postcodes
        .split(",")
        .map((p) => p.trim().toUpperCase())
        .filter(Boolean),
      buy_box: patch?.buy_box ?? { property_types: [] },
      opportunity_types: types,
      conviction_floor: floor,
    };
    try {
      const saved = await api.savePatch(body);
      onSaved(saved);
      setOpen(false);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Couldn’t save your patch. Try again.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mb-2">
      <button
        type="button"
        className="text-sm text-ink-2 hover:text-ink transition-colors"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        {open ? "Close patch settings" : "Edit patch"}
      </button>

      {open ? (
        <div className="mt-5 pt-6 border-t border-line space-y-6 max-w-reading">
          <div>
            <label htmlFor="postcodes" className="block text-sm text-ink-2 mb-1.5">
              Postcodes — the ground the engine works
            </label>
            <input
              id="postcodes"
              className="field"
              placeholder="e.g. LS6, LS7, BD3"
              value={postcodes}
              onChange={(e) => setPostcodes(e.target.value)}
            />
            <p className="text-ink-3 text-sm mt-1.5">
              Comma-separated. Outcodes or full postcodes.
            </p>
          </div>

          <div>
            <label htmlFor="floor" className="block text-sm text-ink-2 mb-1.5">
              Conviction floor — {floor} ({bandWord(bandForFloor(floor))})
            </label>
            <input
              id="floor"
              type="range"
              min={0}
              max={100}
              step={1}
              value={floor}
              onChange={(e) => setFloor(Number(e.target.value))}
              className="w-full accent-[var(--ink)]"
            />
            <p className="text-ink-3 text-sm mt-1.5">
              You receive every briefing at or above this floor. Lower to see
              more candidates; raise for lead-grade only.
            </p>
          </div>

          <div>
            <p className="text-sm text-ink-2 mb-2">Opportunity types</p>
            <div className="flex flex-wrap gap-2">
              {OPPORTUNITY_TYPES.map((t) => {
                const on = types.includes(t);
                return (
                  <button
                    key={t}
                    type="button"
                    onClick={() => toggleType(t)}
                    aria-pressed={on}
                    className={
                      on
                        ? "btn btn-secondary border-ink text-ink"
                        : "btn btn-secondary text-ink-2"
                    }
                    style={{ padding: "0.35rem 0.7rem", fontSize: "0.85rem" }}
                  >
                    {t.replace(/_/g, " ")}
                  </button>
                );
              })}
            </div>
            <p className="text-ink-3 text-sm mt-2">
              Leave all off to receive every type above the floor.
            </p>
          </div>

          {error ? (
            <p className="text-seal text-sm" role="alert">
              {error}
            </p>
          ) : null}

          <button
            type="button"
            className="btn btn-primary"
            onClick={save}
            disabled={saving}
          >
            {saving ? "Saving…" : "Save patch"}
          </button>
        </div>
      ) : null}
    </div>
  );
}

function bandForFloor(floor: number): string {
  if (floor >= 81) return "STRONG";
  if (floor >= 56) return "LIKELY";
  if (floor >= 31) return "MONITOR";
  return "LOW";
}

export default function PatchPage() {
  const { token, ready } = useRequireAuth();
  const [patch, setPatch] = useState<PatchOut | null>(null);
  const [cards, setCards] = useState<BriefingCardData[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const p = await api.getPatch().catch(() => null);
      setPatch(p);
      const feed = await api.patchBriefings();
      setCards(feed);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Couldn’t load your patch feed. Try again shortly.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (ready && token) load();
  }, [ready, token, load]);

  if (!ready || !token) return null;

  const hasPatch = patch && patch.postcodes.length > 0;

  return (
    <div className="pt-10">
      <Eyebrow className="mb-3">My patch · push feed</Eyebrow>
      <h1 className="font-serif text-3xl mb-2">Briefings in your patch</h1>
      <p className="text-ink-2 max-w-reading leading-relaxed mb-6">
        The engine works your postcodes continuously and brings findings above
        your conviction floor here. Open one to read the reasoning.
      </p>

      <PatchEditor patch={patch} onSaved={(p) => {
        setPatch(p);
        load();
      }} />

      <div className="mt-6">
        {loading ? (
          <Loading label="Working your patch" />
        ) : error ? (
          <ErrorState message={error} onRetry={load} />
        ) : !hasPatch ? (
          <EmptyState
            title="Define your patch and the engine starts working it"
            body="Add the postcodes you cover and set a conviction floor. Findings appear here as the engine corroborates them across sources — you won’t have to go hunting."
            action={null}
          />
        ) : cards && cards.length > 0 ? (
          <div>
            {cards.map((c) => (
              <BriefingCard key={c.id} card={c} />
            ))}
          </div>
        ) : (
          <EmptyState
            title="Nothing above your floor yet"
            body="Your patch is set and the engine is working it. When a site clears your conviction floor, its briefing lands here. Lower the floor to see earlier-stage candidates."
            action={null}
          />
        )}
      </div>
    </div>
  );
}
