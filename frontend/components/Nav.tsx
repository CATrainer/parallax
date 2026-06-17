"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import clsx from "clsx";
import { BRAND } from "@/lib/format";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { UsageOut } from "@/lib/types";

// Editorial top bar links (§ brief). "Briefings" and "My patch" are the same
// surface (the patch feed) in this build; the patch editor lives inline there.
const NAV = [
  { href: "/patch", label: "Briefings" },
  { href: "/search", label: "Search" },
  { href: "/watchlist", label: "Watchlist" },
  { href: "/broker", label: "Broker" },
];

function CreditsIndicator() {
  const { token, ready } = useAuth();
  const [usage, setUsage] = useState<UsageOut | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!ready || !token) {
      setUsage(null);
      return;
    }
    api
      .usage()
      .then((u) => {
        if (!cancelled) setUsage(u);
      })
      .catch(() => {
        if (!cancelled) setUsage(null);
      });
    return () => {
      cancelled = true;
    };
  }, [ready, token]);

  if (!usage) return null;

  return (
    <span className="text-ink-3 text-sm whitespace-nowrap" title="Validation credits remaining">
      {usage.credits_remaining} credit{usage.credits_remaining === 1 ? "" : "s"}
      <span className="text-line-2 mx-1.5">·</span>
      <span className="capitalize">{usage.rung}</span>
    </span>
  );
}

export function Nav() {
  const pathname = usePathname();
  const { token, signOut } = useAuth();

  // Don't render the nav on the login screen.
  if (pathname === "/login") return null;

  return (
    <header className="border-b border-line">
      <div className="mx-auto max-w-wide px-5 sm:px-8 h-16 flex items-center gap-6">
        <Link
          href="/patch"
          className="font-serif text-xl text-ink no-underline tracking-tight shrink-0"
        >
          {BRAND}
        </Link>

        <nav className="hidden sm:flex items-center gap-5 flex-1" aria-label="Primary">
          {NAV.map((link) => {
            const active =
              pathname === link.href ||
              pathname.startsWith(link.href + "/") ||
              (link.href === "/patch" && pathname.startsWith("/sites"));
            return (
              <Link
                key={link.label}
                href={link.href}
                className={clsx(
                  "text-sm no-underline transition-colors",
                  active ? "text-ink font-medium" : "text-ink-2 hover:text-ink",
                )}
                aria-current={active ? "page" : undefined}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>

        <div className="flex items-center gap-4 ml-auto">
          <CreditsIndicator />
          {token ? (
            <button
              type="button"
              onClick={signOut}
              className="text-sm text-ink-3 hover:text-ink transition-colors"
            >
              Sign out
            </button>
          ) : null}
        </div>
      </div>

      {/* Mobile nav row */}
      <nav
        className="sm:hidden border-t border-line px-5 h-12 flex items-center gap-5 overflow-x-auto"
        aria-label="Primary"
      >
        {NAV.map((link) => {
          const active =
            pathname === link.href || pathname.startsWith(link.href + "/");
          return (
            <Link
              key={link.label}
              href={link.href}
              className={clsx(
                "text-sm no-underline whitespace-nowrap",
                active ? "text-ink font-medium" : "text-ink-2",
              )}
            >
              {link.label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
