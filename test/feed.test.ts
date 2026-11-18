// Domain checks for the proposal reader and the local filter.
import test from "node:test";
import assert from "node:assert/strict";
import { parseFeed, filterProposals, countByKind, asText, FeedError, KINDS, MAX_PROPOSALS } from "../src/domain/feed.ts";

const doc = (proposals: unknown[], extra: Record<string, unknown> = {}) => JSON.stringify({ status: "PENDING_POST", proposals, ...extra });
const ok = (id: string, kind = "goods", over: Record<string, unknown> = {}) => ({ id, kind, evidence: "tick 2026-11-18T00:00Z gap 1.2%", proposal: "compare the two quotes", ...over });

test("reads the bot's pending_proposals document, newest id first", () => {
  const f = parseFeed(doc([ok("arb-20261117-a"), ok("arb-20261118-b", "information")]));
  assert.equal(f.status, "PENDING_POST");
  assert.deepEqual(f.proposals.map((p) => p.id), ["arb-20261118-b", "arb-20261117-a"]);
  assert.deepEqual(f.rejected, []);
});

test("applies arb_post.py's rule and gives a reason for each rejection", () => {
  const f = parseFeed(doc([
    ok("x-1"),
    ok("arb-2", "stocks"),
    ok("arb-3", "goods", { evidence: "" }),
    ok("arb-4", "goods", { proposal: "   " }),
    "not an object",
    ok("arb-5"),
    ok("arb-5"),
  ]));
  assert.deepEqual(f.proposals.map((p) => p.id), ["arb-5"]);
  assert.deepEqual(f.rejected.map((r) => [r.index, r.reason]), [
    [0, "id must start with arb-"],
    [1, `kind must be one of ${KINDS.join(", ")}`],
    [2, "evidence is missing"],
    [3, "proposal is missing"],
    [4, "not an object"],
    [6, "duplicate id"],
  ]);
});

test("structured evidence is kept as readable JSON text", () => {
  const f = parseFeed(doc([ok("arb-1", "goods", { evidence: { ticks: ["t1"], gap_pct: 1.2 } })]));
  assert.match(f.proposals[0].evidence, /"gap_pct": 1.2/);
  assert.equal(asText(undefined), "");
});

test("a file that is not a feed is refused as a whole", () => {
  for (const [text, msg] of [["{", /not JSON/], ["[]", /not a proposal document/], ['{"status":"x"}', /no proposals list/]] as const) {
    assert.throws(() => parseFeed(text), (e: unknown) => e instanceof FeedError && msg.test((e as Error).message));
  }
  assert.throws(() => parseFeed("x".repeat(1_000_001)), FeedError);
});

test("keeps at most MAX_PROPOSALS and lists the rest as rejected", () => {
  const many = Array.from({ length: MAX_PROPOSALS + 2 }, (_, i) => ok(`arb-${String(i).padStart(5, "0")}`));
  const f = parseFeed(doc(many));
  assert.equal(f.proposals.length, MAX_PROPOSALS);
  assert.equal(f.rejected.length, 2);
});

test("filters by kind and by text, case-insensitively, on the device", () => {
  const f = parseFeed(doc([ok("arb-1", "goods"), ok("arb-2", "social", { proposal: "Benefit Office hours" }), ok("arb-3", "procedural")]));
  assert.deepEqual(filterProposals(f.proposals, { kinds: ["social", "procedural"] }).map((p) => p.id), ["arb-3", "arb-2"]);
  assert.deepEqual(filterProposals(f.proposals, { query: "benefit" }).map((p) => p.id), ["arb-2"]);
  assert.equal(filterProposals(f.proposals, {}).length, 3);
  assert.deepEqual(countByKind(f.proposals), { information: 0, goods: 1, procedural: 1, social: 1 });
});
