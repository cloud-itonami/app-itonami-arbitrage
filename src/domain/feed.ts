// Awai Arbitrage domain core. It reads an awai-arb proposal document and
// filters it, entirely on this device. Nothing here talks to a network.
//
// The document shape is the one the bot drafts and `arb_post.py` checks before
// it sends a proposal to the ossekai intake
// (itonami/profiles/awai-arb/scripts/arb_post.py):
//
//   {"status": "PENDING_POST", "proposals": [{"id": "arb-<ts>-<slug>",
//     "kind": "information" | "goods" | "procedural" | "social",
//     "evidence": ..., "proposal": ...}]}
//
// The same rule decides what is shown here: an arb- id, a known kind, and a
// non-empty evidence and proposal. Anything else is listed as rejected, with
// the reason, and is never shown as a proposal.

export type Kind = "information" | "goods" | "procedural" | "social";

export const KINDS: readonly Kind[] = ["information", "goods", "procedural", "social"];

export const KIND_LABELS: Readonly<Record<Kind, string>> = {
  information: "情報の格差",
  goods: "物の価格差",
  procedural: "手続きの難しさ",
  social: "社会的な格差",
};

export interface Proposal {
  id: string;
  kind: Kind;
  evidence: string;
  proposal: string;
}

export interface Rejected {
  index: number;
  id: string | null;
  reason: string;
}

export interface Feed {
  status: string | null;
  proposals: Proposal[];
  rejected: Rejected[];
}

/** Largest document read, in characters (a feed file is small JSON). */
export const MAX_TEXT = 1_000_000;
/** Most proposals kept from one document. */
export const MAX_PROPOSALS = 2_000;

export class FeedError extends Error {}

/** Text of an evidence or proposal value: a string as is, anything else as JSON. */
export function asText(value: unknown): string {
  if (typeof value === "string") return value.trim();
  if (value === null || value === undefined) return "";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return "";
  }
}

function isEmpty(value: unknown): boolean {
  if (value === null || value === undefined || value === false) return true;
  if (typeof value === "string") return value.trim() === "";
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === "object") return Object.keys(value as object).length === 0;
  return false;
}

function check(raw: unknown, index: number): Proposal | Rejected {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
    return { index, id: null, reason: "not an object" };
  }
  const p = raw as Record<string, unknown>;
  const id = typeof p.id === "string" ? p.id : null;
  if (!id || !id.startsWith("arb-")) return { index, id, reason: "id must start with arb-" };
  if (!KINDS.includes(p.kind as Kind)) return { index, id, reason: `kind must be one of ${KINDS.join(", ")}` };
  if (isEmpty(p.evidence)) return { index, id, reason: "evidence is missing" };
  if (isEmpty(p.proposal)) return { index, id, reason: "proposal is missing" };
  return { id, kind: p.kind as Kind, evidence: asText(p.evidence), proposal: asText(p.proposal) };
}

/**
 * Parse a proposal document. Throws FeedError when the text is not a feed at
 * all; individual bad proposals are returned in `rejected` instead.
 */
export function parseFeed(text: string): Feed {
  if (typeof text !== "string") throw new FeedError("the file is not text");
  if (text.length > MAX_TEXT) throw new FeedError(`the file is larger than ${MAX_TEXT} characters`);
  let doc: unknown;
  try {
    doc = JSON.parse(text);
  } catch {
    throw new FeedError("the file is not JSON");
  }
  if (doc === null || typeof doc !== "object" || Array.isArray(doc)) throw new FeedError("the file is not a proposal document");
  const d = doc as Record<string, unknown>;
  if (!Array.isArray(d.proposals)) throw new FeedError("the document has no proposals list");
  const proposals: Proposal[] = [];
  const rejected: Rejected[] = [];
  const seen = new Set<string>();
  d.proposals.forEach((raw, index) => {
    const r = check(raw, index);
    if ("reason" in r) {
      rejected.push(r);
    } else if (seen.has(r.id)) {
      rejected.push({ index, id: r.id, reason: "duplicate id" });
    } else if (proposals.length >= MAX_PROPOSALS) {
      rejected.push({ index, id: r.id, reason: `more than ${MAX_PROPOSALS} proposals` });
    } else {
      seen.add(r.id);
      proposals.push(r);
    }
  });
  // Ids are arb-<timestamp>-<slug>: newest first.
  proposals.sort((a, b) => (a.id < b.id ? 1 : a.id > b.id ? -1 : 0));
  return { status: typeof d.status === "string" ? d.status : null, proposals, rejected };
}

export interface Filter {
  kinds?: readonly Kind[];
  query?: string;
}

/** Proposals of the chosen kinds whose text contains the query (case-insensitive). */
export function filterProposals(proposals: readonly Proposal[], filter: Filter = {}): Proposal[] {
  const kinds = filter.kinds && filter.kinds.length > 0 ? new Set(filter.kinds) : null;
  const q = (filter.query ?? "").trim().toLowerCase();
  return proposals.filter((p) => {
    if (kinds && !kinds.has(p.kind)) return false;
    if (!q) return true;
    return [p.id, p.proposal, p.evidence].some((t) => t.toLowerCase().includes(q));
  });
}

/** Count of proposals per kind, every kind present (0 when none). */
export function countByKind(proposals: readonly Proposal[]): Record<Kind, number> {
  const out = { information: 0, goods: 0, procedural: 0, social: 0 } as Record<Kind, number>;
  for (const p of proposals) out[p.kind] += 1;
  return out;
}
