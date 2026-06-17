import type { SiteOut } from "@/lib/types";
import { humanise } from "@/lib/format";

// Definition list of site facts (§9.3). Mono only for the UPRN (a true
// machine identifier); everything else reads as prose.

function Row({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[10rem_1fr] gap-x-4 py-2.5 border-t border-line first:border-t-0">
      <dt className="text-ink-3 text-sm pt-0.5">{term}</dt>
      <dd className="text-ink">{children}</dd>
    </div>
  );
}

export function PropertyFacts({ site }: { site: SiteOut }) {
  return (
    <dl className="m-0">
      <Row term="UPRN">
        <span className="ref">{site.uprn}</span>
      </Row>
      <Row term="Address">{site.address}</Row>
      {site.postcode ? <Row term="Postcode">{site.postcode}</Row> : null}
      {site.property_type ? (
        <Row term="Property type">{humanise(site.property_type)}</Row>
      ) : null}
      {site.tenure ? <Row term="Tenure">{humanise(site.tenure)}</Row> : null}
      {site.local_authority ? (
        <Row term="Local authority">{site.local_authority}</Row>
      ) : null}
      <Row term="Resolution">
        <span className="text-ink-2">
          address → UPRN matched at confidence{" "}
          {site.resolution_confidence.toFixed(2)}
        </span>
      </Row>
    </dl>
  );
}
