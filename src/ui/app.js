// Awai Arbitrage UI. It shows the proposals of a feed file the user picks on
// this device and filters them locally. It builds DOM from text nodes only (no
// HTML strings) and makes no network request: the public feed is not connected
// yet (AWAI-3207), so a file is the only source.
import { parseFeed, filterProposals, countByKind, KINDS, KIND_LABELS, FeedError } from "./domain/feed.js";
import { LocalState } from "./state.js";

const STORAGE_KEY = "itonami.arbitrage.v1";

function storage() { try { return globalThis.localStorage ?? null; } catch { return null; } }
const state = new LocalState({ storage: storage(), key: STORAGE_KEY });
const ui = { message: null, error: null };

const el = (tag, props = {}, ...kids) => {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value === true) node.setAttribute(key, "");
    else if (value !== false && value != null) node.setAttribute(key, String(value));
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) node.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  return node;
};

function say(message, error = null) {
  ui.message = message; ui.error = error;
  const box = document.getElementById("notice");
  box.replaceChildren();
  if (error) box.append(el("p", { class: "error" }, error));
  else if (message) box.append(el("p", { class: "ok" }, message));
}

async function importFile(input) {
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  try {
    const feed = parseFeed(await file.text());
    state.setFeed(feed, { name: file.name, importedAt: new Date().toISOString() });
    say(`${file.name} を読み込みました: 提案 ${feed.proposals.length} 件、除外 ${feed.rejected.length} 件`);
  } catch (error) {
    say(null, error instanceof FeedError ? `読み込めません: ${error.message}` : `読み込めません: ${error?.message ?? String(error)}`);
  }
  render();
}

function setFilter(change) {
  const f = state.value.filter;
  try { state.setFilter({ ...f, ...change }); } catch (error) { say(null, error.message); }
  renderList();
}

function toggleKind(kind, on) {
  const kinds = new Set(state.value.filter.kinds);
  if (on) kinds.add(kind); else kinds.delete(kind);
  setFilter({ kinds: KINDS.filter((k) => kinds.has(k)) });
}

function forget() {
  try { state.clear(); say("この端末に保存した内容を消しました"); } catch (error) { say(null, error.message); }
  render();
}

function sourcePanel() {
  const input = el("input", { type: "file", id: "feed-file", accept: "application/json,.json", onchange: (ev) => importFile(ev.target) });
  const src = state.value.source;
  return el("section", { class: "card", "aria-labelledby": "src-h" },
    el("h2", { id: "src-h" }, "提案を読み込む"),
    el("p", { class: "muted" }, "awai-arb が下書きした提案ファイル（pending_proposals_<日付>.json）をこの端末から選びます。ファイルの中身は端末の外に送りません。公開 feed への接続はまだありません。"),
    el("label", { for: "feed-file" }, "提案ファイル"), el("div", {}, input),
    src && src.name ? el("p", { class: "muted" }, `読み込み済み: ${src.name}（${src.importedAt}）`) : null,
    el("button", { type: "button", class: "secondary", onclick: forget }, "端末の保存内容を消す"));
}

function filterPanel(feed) {
  const counts = countByKind(feed.proposals);
  const f = state.value.filter;
  return el("section", { class: "card", "aria-labelledby": "flt-h" },
    el("h2", { id: "flt-h" }, "絞り込み"),
    el("p", { class: "muted" }, "条件はこの端末の中だけで使います。"),
    el("fieldset", {}, el("legend", {}, "格差の種類"),
      ...KINDS.map((k) => el("label", { class: "check" },
        el("input", { type: "checkbox", checked: f.kinds.includes(k), onchange: (ev) => toggleKind(k, ev.target.checked) }),
        ` ${KIND_LABELS[k]}（${counts[k]}）`))),
    el("label", { for: "q" }, "言葉で探す"),
    el("input", { type: "search", id: "q", value: f.query, oninput: (ev) => setFilter({ query: ev.target.value }) }));
}

function proposalCard(p) {
  return el("article", { class: "card proposal" },
    el("p", { class: "kind" }, KIND_LABELS[p.kind]),
    el("h3", {}, p.id),
    el("p", { class: "body" }, p.proposal),
    el("details", {}, el("summary", {}, "根拠"), el("pre", {}, p.evidence)));
}

function renderList() {
  const box = document.getElementById("list");
  if (!box) return;
  const feed = state.value.feed;
  const shown = filterProposals(feed.proposals, state.value.filter);
  box.replaceChildren(
    el("p", { class: "muted" }, `${feed.proposals.length} 件中 ${shown.length} 件`),
    ...(shown.length ? shown.map(proposalCard) : [el("p", {}, "条件に合う提案はありません。")]));
}

function rejectedPanel(feed) {
  if (!feed.rejected.length) return null;
  return el("section", { class: "card" },
    el("details", {}, el("summary", {}, `除外した項目（${feed.rejected.length} 件）`),
      el("ul", {}, ...feed.rejected.map((r) => el("li", {}, `#${r.index} ${r.id ?? "(id なし)"}: ${r.reason}`)))));
}

function render() {
  const view = document.getElementById("view");
  const feed = state.value.feed;
  // replaceChildren turns null into the text "null", so drop absent parts first.
  view.replaceChildren(...[
    el("section", { class: "card warn", "aria-label": "注意" },
      el("p", {}, "ここにあるのは bot が測った価格差・情報格差の提案で、売買の指示や投資助言ではありません。この app は取引・送金・投稿をしません。")),
    sourcePanel(),
    feed ? filterPanel(feed) : el("section", { class: "card" }, el("p", {}, "まだ提案がありません。上のボタンから提案ファイルを選んでください。")),
    feed ? el("section", { id: "list", "aria-live": "polite" }) : null,
    feed ? rejectedPanel(feed) : null,
  ].filter(Boolean));
  if (feed) renderList();
}

async function hostLabel() {
  const invoke = globalThis.__TAURI__?.core?.invoke;
  const env = document.getElementById("env");
  if (!invoke) { env.textContent = "browser"; return; }
  try { const info = await invoke("awai_host_info"); env.textContent = info?.schema ? "Awai app" : "Tauri"; } catch { env.textContent = "Tauri"; }
}

render();
hostLabel();
