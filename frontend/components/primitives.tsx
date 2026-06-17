import type { ReactNode } from "react";
import clsx from "clsx";

/** Small-caps provenance / section label (§9.3). */
export function Eyebrow({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <p className={clsx("eyebrow", className)}>{children}</p>;
}

/** A titled section separated from the page by a hairline rule (no boxes). */
export function Band({
  title,
  children,
  className,
}: {
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={clsx("pt-8 mt-8 border-t border-line", className)}>
      {title ? (
        <Eyebrow className="mb-4">{title}</Eyebrow>
      ) : null}
      {children}
    </section>
  );
}

/** Empty state that directs rather than decorates (§9.3). */
export function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?: ReactNode;
}) {
  return (
    <div className="max-w-reading py-16">
      <h2 className="font-serif text-2xl mb-3">{title}</h2>
      <p className="text-ink-2 mb-6 leading-relaxed">{body}</p>
      {action}
    </div>
  );
}

/** Error state in interface voice (§9.4) — what happened + next step. */
export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="max-w-reading py-12">
      <Eyebrow className="mb-3 text-seal">Couldn’t load</Eyebrow>
      <p className="text-ink leading-relaxed mb-5">{message}</p>
      {onRetry ? (
        <button className="btn btn-secondary" onClick={onRetry} type="button">
          Try again
        </button>
      ) : null}
    </div>
  );
}

/** Quiet loading line — calm, no spinner-as-decoration. */
export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <p className="text-ink-3 py-12 max-w-reading" aria-live="polite">
      {label}…
    </p>
  );
}
