"use client";

import Link from "next/link";

interface ScopeTrailProps {
  brand?: { id: string; name: string };
  campaign?: { id: string; name: string };
  lineItem?: { name: string };
}

/**
 * Breadcrumb-style trail showing where you are in the hierarchy.
 * Used in the topbar of drill-down pages so the user always knows
 * which Advertiser → Order → Line Item they're looking at.
 */
export function ScopeTrail({ brand, campaign, lineItem }: ScopeTrailProps) {
  return (
    <div className="flex items-center gap-1.5 text-xs">
      {brand ? (
        <Link
          href="/dashboard"
          className="text-ink-200 hover:text-ink-50"
        >
          {brand.name}
        </Link>
      ) : null}
      {campaign ? (
        <>
          <span className="text-ink-500">›</span>
          <Link
            href={`/campaign/${campaign.id}`}
            className="text-ink-200 hover:text-ink-50"
          >
            {campaign.name}
          </Link>
        </>
      ) : null}
      {lineItem ? (
        <>
          <span className="text-ink-500">›</span>
          <span className="text-ink-50">{lineItem.name}</span>
        </>
      ) : null}
    </div>
  );
}
