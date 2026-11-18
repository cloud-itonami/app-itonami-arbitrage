// Local state for Awai Arbitrage: the last imported proposal document and the
// viewer's filter, kept in localStorage on this device only. Nothing here talks
// to a network, and the filter never leaves the device.

export const STATE_SCHEMA = "itonami.arbitrage.state.v1";

const empty = () => ({ schema: STATE_SCHEMA, source: null, feed: null, filter: { kinds: [], query: "" } });

export class LocalState {
  /** @param {{ storage?: { getItem(k: string): string | null, setItem(k: string, v: string): void, removeItem?(k: string): void } | null, key: string }} options */
  constructor({ storage = null, key }) {
    if (!key) throw new Error("LocalState needs a key");
    this.storage = storage;
    this.key = key;
    this.value = this.#load();
  }

  #load() {
    if (!this.storage) return empty();
    let raw = null;
    try { raw = this.storage.getItem(this.key); } catch { return empty(); }
    if (!raw) return empty();
    try {
      const v = JSON.parse(raw);
      if (!v || v.schema !== STATE_SCHEMA) return empty();
      return { ...empty(), ...v, filter: { ...empty().filter, ...(v.filter ?? {}) } };
    } catch {
      return empty();
    }
  }

  #save() {
    if (!this.storage) return;
    try {
      this.storage.setItem(this.key, JSON.stringify(this.value));
    } catch (error) {
      throw new Error("local save failed: " + (error?.message ?? String(error)));
    }
  }

  /** Keep an imported feed: where it came from (a file name), when, and the parsed result. */
  setFeed(feed, source) {
    this.value = { ...this.value, feed, source: { name: String(source?.name ?? ""), importedAt: String(source?.importedAt ?? "") } };
    this.#save();
  }

  setFilter(filter) {
    this.value = { ...this.value, filter: { kinds: [...(filter.kinds ?? [])], query: String(filter.query ?? "") } };
    this.#save();
  }

  /** Forget everything this app stored on the device. */
  clear() {
    this.value = empty();
    if (!this.storage) return;
    try {
      if (typeof this.storage.removeItem === "function") this.storage.removeItem(this.key);
      else this.storage.setItem(this.key, JSON.stringify(this.value));
    } catch (error) {
      throw new Error("local clear failed: " + (error?.message ?? String(error)));
    }
  }
}
