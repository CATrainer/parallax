import Link from "next/link";

export default function NotFound() {
  return (
    <div className="pt-16 max-w-reading">
      <p className="eyebrow mb-3">Not found</p>
      <h1 className="font-serif text-3xl mb-3">There’s nothing here</h1>
      <p className="text-ink-2 leading-relaxed mb-6">
        That page doesn’t exist, or the briefing has moved. Head back to your
        patch to pick up where you left off.
      </p>
      <Link href="/patch" className="btn btn-secondary no-underline">
        Go to your patch
      </Link>
    </div>
  );
}
