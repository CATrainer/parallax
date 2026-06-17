"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { BRAND } from "@/lib/format";
import { Eyebrow } from "@/components/primitives";

export default function LoginPage() {
  const router = useRouter();
  const { signIn } = useAuth();
  const [email, setEmail] = useState("demo@parallax.dev");
  const [password, setPassword] = useState("demo1234");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const token = await api.login(email, password);
      signIn(token.access_token);
      router.replace(token.is_broker ? "/broker" : "/patch");
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Sign-in failed. Check your details and try again.";
      setError(message);
      setBusy(false);
    }
  }

  return (
    <div className="min-h-[70vh] flex items-center">
      <div className="w-full max-w-sm mx-auto">
        <Eyebrow className="mb-3">Sign in</Eyebrow>
        <h1 className="font-serif text-3xl mb-2">{BRAND}</h1>
        <p className="text-ink-2 mb-8 leading-relaxed">
          Written, sourced findings about specific sites. Sign in to work your
          patch.
        </p>

        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          <div>
            <label htmlFor="email" className="block text-sm text-ink-2 mb-1.5">
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="username"
              className="field"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div>
            <label
              htmlFor="password"
              className="block text-sm text-ink-2 mb-1.5"
            >
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              className="field"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          {error ? (
            <p className="text-seal text-sm" role="alert">
              {error}
            </p>
          ) : null}

          <button
            type="submit"
            className="btn btn-primary w-full"
            disabled={busy}
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="text-ink-3 text-sm mt-6">
          Demo access is prefilled —{" "}
          <span className="ref">demo@parallax.dev</span>.
        </p>
      </div>
    </div>
  );
}
