// Local state: kept on the device, survives a reload, and can be forgotten.
import test from "node:test";
import assert from "node:assert/strict";
import { LocalState, STATE_SCHEMA } from "../src/state.js";

const memory = () => { const m = new Map(); return { m, getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, v), removeItem: (k) => m.delete(k) }; };

test("feed and filter round-trip through storage", () => {
  const s = memory();
  const a = new LocalState({ storage: s, key: "k" });
  a.setFeed({ status: null, proposals: [{ id: "arb-1" }], rejected: [] }, { name: "p.json", importedAt: "2026-11-18T00:00:00Z" });
  a.setFilter({ kinds: ["goods"], query: "q" });
  const b = new LocalState({ storage: s, key: "k" });
  assert.equal(b.value.schema, STATE_SCHEMA);
  assert.equal(b.value.feed.proposals[0].id, "arb-1");
  assert.deepEqual(b.value.filter, { kinds: ["goods"], query: "q" });
  assert.equal(b.value.source.name, "p.json");
});

test("garbage or a foreign schema in storage reads as empty", () => {
  for (const raw of ["{", JSON.stringify({ schema: "other" })]) {
    const s = memory(); s.setItem("k", raw);
    assert.equal(new LocalState({ storage: s, key: "k" }).value.feed, null);
  }
});

test("clear forgets everything; a failing save is reported", () => {
  const s = memory();
  const a = new LocalState({ storage: s, key: "k" });
  a.setFilter({ kinds: ["social"] });
  a.clear();
  assert.equal(s.m.has("k"), false);
  assert.deepEqual(a.value.filter, { kinds: [], query: "" });
  const broken = new LocalState({ storage: { getItem: () => null, setItem: () => { throw new Error("quota"); } }, key: "k" });
  assert.throws(() => broken.setFilter({ kinds: [] }), /local save failed/);
});
