import type { OwnershipLinkOut } from "@/lib/types";
import { humanise, confidenceLabel } from "@/lib/format";

// Typeset ownership relations with confidence shown (§9.3 / §6.1). Links are
// probabilistic — phrase them as resolved relations, never hard assertions.

function ownerLine(link: OwnershipLinkOut): string {
  const role = humanise(link.role).toLowerCase();
  const name = link.owner.display_name;
  const verb = link.is_current ? "is" : "was";
  return `${name} ${verb} ${role}`;
}

export function OwnershipBlock({ ownership }: { ownership: OwnershipLinkOut[] }) {
  if (!ownership.length) {
    return (
      <p className="text-ink-2 leading-relaxed">
        Ownership isn’t resolved yet. Validate the briefing to pull confirmed
        title-level ownership.
      </p>
    );
  }

  return (
    <ul className="list-none p-0 m-0">
      {ownership.map((link) => (
        <li
          key={link.id}
          className="py-3.5 border-t border-line first:border-t-0"
        >
          <p className="text-ink leading-relaxed">
            {ownerLine(link)}
            {link.owner.company_number ? (
              <span className="text-ink-2">
                {" · company "}
                <span className="ref">{link.owner.company_number}</span>
              </span>
            ) : null}
          </p>
          <p className="text-ink-3 text-sm mt-0.5">
            {confidenceLabel(link.link_confidence)} · resolved from {link.source}
          </p>
        </li>
      ))}
    </ul>
  );
}
