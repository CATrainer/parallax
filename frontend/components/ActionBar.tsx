"use client";

import type { ReactNode } from "react";

// The briefing's action moment (§9.3). A single calm primary + a secondary,
// docked inline at the true page bottom — it is part of the document flow and
// can never overlap mid-scroll content. No sticky overlay.

export function ActionBar({
  primaryLabel,
  onPrimary,
  secondaryLabel,
  onSecondary,
  primaryDisabled,
  secondaryDisabled,
  note,
  children,
}: {
  primaryLabel: string;
  onPrimary: () => void;
  secondaryLabel?: string;
  onSecondary?: () => void;
  primaryDisabled?: boolean;
  secondaryDisabled?: boolean;
  note?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="mt-12 pt-8 border-t border-line-2">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className="btn btn-primary"
          onClick={onPrimary}
          disabled={primaryDisabled}
        >
          {primaryLabel}
        </button>
        {secondaryLabel && onSecondary ? (
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onSecondary}
            disabled={secondaryDisabled}
          >
            {secondaryLabel}
          </button>
        ) : null}
      </div>
      {note ? <p className="text-ink-3 text-sm mt-3">{note}</p> : null}
      {children}
    </div>
  );
}
