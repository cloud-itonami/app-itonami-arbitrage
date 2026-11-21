#!/usr/bin/env python3
# awai-arb price-difference observation tick (AWAI-3207, owner decision 2026-11-22).
#
# Private and local: one tick reads public spot / catalog prices with plain GET
# requests and appends one JSON line to a local file. Nothing is posted, mailed or
# published, and no paid API is used. The output is price-difference observation
# data (価格差の観測データ): it is not a proposal, a trading signal or investment
# advice, and the differences do not include fees, transfer time or slippage (DISCLAIMER).
#
# Scope: spot crypto-assets and things that are not financial instruments only.
# Derivatives (futures, perpetuals, options), securities and FX are refused by
# check_scope() below; see EXCLUDED for the sources removed on 2026-11-22.
#
#   python3 arb_measure.py [--data-dir DIR] [--interval-s 60] [--audit-net]
#
# Data dir: --data-dir, else $AWAI_ARB_DATA_DIR, else <profile>/workspace (host-local,
# never in git). Writes one file per UTC day, price_observations-YYYY-MM-DD.jsonl
# (append-only). When all daily files together exceed 1 GiB, the oldest ones (never
# today's) are gzipped in place until the total is back under; nothing is deleted.
#
# Run every --interval-s seconds (default 60, launchd StartInterval). Public GET only:
# no API key, no order, no POST. On HTTP 429 or 5xx that exchange alone is skipped for
# a doubled interval (120 s, 240 s, ... ceiling 600 s), kept in backoff_state.json; its
# first successful answer resets it. Other exchanges keep their normal interval.
# --audit-net also appends every socket connect and urllib request this process makes
# to net_audit.jsonl in the same dir, so a run can show it sent nothing anywhere else.
#
# Freshness: a source answer is used for a comparison only when it is "fresh" (quick, its
# server Date is near the local clock, prices finite and positive); a pair is "comparable"
# only when its two prices were fetched within MAX_FETCH_SKEW_MS and differ by no more
# than SUSPECT_BPS. Everything is still recorded, with the reason it was set aside.
#
# stdout: one status line per tick, then NOT_FRESH / FAILED / OBSERVED / EXCLUDED lines.
# exit 0 at least one source read or deliberately skipped, 3 nothing read (not success),
# 4 the tick passed TICK_DEADLINE_S and was cut off (nothing written for it).
import json, math, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

SCHEMA = "awai-arb.price-observation.v1"
UA = "awai-arb/0.2 (+https://itonami.cloud)"  # CF-fronted endpoints 403 on no-UA python
ALLOWED_CATEGORIES = {"crypto-spot", "non-financial"}
LABEL = "価格差の観測データ (price-difference observation data)"
DISCLAIMER = ("投資助言ではありません。売買の提案や推奨でもありません。表示する差は、手数料・送金時間・"
              "スリッページを含みません。各価格は記録した取得時刻の値です。 / Not investment advice, "
              "not a proposal or recommendation. Differences exclude fees, transfer time and slippage. "
              "Each price is as of its recorded fetch time.")

# Freshness and sanity (owner addition 2026-11-22: never present an old or wrong price as current).
MAX_FETCH_S = 10          # a source answer that took longer is marked not fresh
MAX_CLOCK_SKEW_S = 60     # server Date header vs local clock; larger means a cached/stale answer or a bad clock
MAX_FETCH_SKEW_MS = 5000  # two prices fetched further apart than this are not compared
SUSPECT_BPS = 500         # a difference this large between spot venues is treated as a probable bad price

# Removed 2026-11-22 (AWAI-3207, Legal memo awai-3207-arb-advice.md §2-3).
EXCLUDED = [
    {"source": "torihiki-devnet /head /book", "category": "derivative",
     "reason": "perpetual order book (margin, funding, liquidation; kotoba-lang/torihiki README)"},
]

# Each source: name, category, url, parse(json) -> [{instrument, price, unit, ...}].
def _coinbase(pair):
    def parse(d):
        return [{"instrument": pair, "price": float(d["data"]["amount"]), "unit": "USD",
                 "quote": "coinbase /v2 spot"}]
    return parse

KRAKEN_MAP = {"XXBTZUSD": "BTC-USD", "XETHZUSD": "ETH-USD", "USDCUSD": "USDC-USD"}

def _kraken(d):
    if d.get("error"):
        raise RuntimeError(f"kraken error {d['error']}")
    out = []
    for k, t in (d.get("result") or {}).items():
        if k not in KRAKEN_MAP:
            continue
        bid, ask = float(t["b"][0]), float(t["a"][0])
        out.append({"instrument": KRAKEN_MAP[k], "price": (bid + ask) / 2, "unit": "USD",
                    "bid": bid, "ask": ask, "last": float(t["c"][0]), "quote": "kraken ticker mid"})
    return out

def _x402(d):
    out = []
    for it in d.get("items") or []:
        p = it.get("price") or {}
        if p.get("usd") is None:
            continue
        out.append({"instrument": f"x402:{it.get('seller')}:{it.get('method')} {it.get('path-prefix')}",
                    "price": float(p["usd"]), "unit": "USD/call", "settlement_asset": p.get("asset")})
    return out

def _murakumo(d):
    out = []
    for m in d.get("data") or []:
        rec = {"instrument": f"murakumo:{m.get('id')}", "unit": "pricing-object",
               "free": m.get("free"), "pricing": m.get("pricing"),
               "withheld": (m.get("murakumo") or {}).get("withheld")}
        rec["price"] = 0.0 if m.get("free") is True else None
        out.append(rec)
    return out

SOURCES = [
    {"source": "coinbase", "category": "crypto-spot",
     "url": f"https://api.coinbase.com/v2/prices/{p}/spot", "parse": _coinbase(p)}
    for p in ("BTC-USD", "ETH-USD", "USDC-USD")
] + [
    {"source": "kraken", "category": "crypto-spot",
     "url": "https://api.kraken.com/0/public/Ticker?pair=XBTUSD,ETHUSD,USDCUSD", "parse": _kraken},
    {"source": "x402.nexus", "category": "non-financial",
     "url": "https://x402.nexus/catalog", "parse": _x402},
    {"source": "murakumo", "category": "non-financial",
     "url": "https://api.murakumo.cloud/v1/models", "parse": _murakumo},
]

# Instruments compared across sources (same asset, same unit).
GAP_INSTRUMENTS = ["BTC-USD", "ETH-USD", "USDC-USD"]

def check_scope(sources):
    hosts = set()
    for s in sources:
        if s["category"] not in ALLOWED_CATEGORIES:
            raise SystemExit(f"REFUSE\t{s['source']}\tcategory {s['category']} is out of scope")
        hosts.add(urllib.parse.urlsplit(s["url"]).hostname)
    return hosts

def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")

def get(url, timeout=25):
    """GET only, no body. Returns (json, server Date header or None)."""
    req = urllib.request.Request(url, method="GET",
                                 headers={"User-Agent": UA, "Accept": "application/json",
                                          "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace")), r.headers.get("Date")

def freshness(rec, server_date):
    """Mark a source answer fresh only when it is quick, dated near our clock and has sane prices."""
    reasons = []
    if rec["elapsed_ms"] > MAX_FETCH_S * 1000:
        reasons.append(f"slow answer {rec['elapsed_ms']} ms")
    if server_date:
        try:
            skew = parsedate_to_datetime(server_date).timestamp() - rec["_t"]
            rec["server_date"] = server_date
            rec["clock_skew_s"] = round(skew, 1)
            if abs(skew) > MAX_CLOCK_SKEW_S:
                reasons.append(f"server Date {skew:+.0f} s from local clock")
        except (TypeError, ValueError):
            reasons.append("unparseable server Date")
    else:
        reasons.append("no server Date header")
    for p in rec.get("prices") or []:
        v = p.get("price")
        if v is not None and (not math.isfinite(v) or v < 0 or (v == 0 and rec["category"] == "crypto-spot")):
            reasons.append(f"bad price {p['instrument']}={v}")
    rec["fresh"] = not reasons
    if reasons:
        rec["not_fresh_reasons"] = reasons

def data_dir(argv):
    if "--data-dir" in argv:
        return os.path.abspath(argv[argv.index("--data-dir") + 1])
    if os.environ.get("AWAI_ARB_DATA_DIR"):
        return os.path.abspath(os.environ["AWAI_ARB_DATA_DIR"])
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workspace")

def install_net_audit(path, allowed_hosts):
    def hook(event, args):
        if event == "socket.connect":
            rec = {"event": event, "address": repr(args[1])}
        elif event == "socket.getaddrinfo":
            rec = {"event": event, "host": args[0], "allowed": args[0] in allowed_hosts}
        elif event == "urllib.Request":
            url, data, _headers, method = args
            rec = {"event": event, "url": url, "method": method, "has_body": data is not None,
                   "allowed": urllib.parse.urlsplit(url).hostname in allowed_hosts}
        else:
            return
        rec["ts"] = now_iso()
        with open(path, "a") as f:
            f.write(json.dumps(rec) + "\n")
    sys.addaudithook(hook)

def gaps(results):
    by_inst = {}
    for r in results:
        if not (r["ok"] and r.get("fresh")):
            continue
        for p in r["prices"]:
            if p["instrument"] in GAP_INSTRUMENTS and p.get("price") is not None:
                by_inst.setdefault(p["instrument"], []).append(
                    {"source": r["source"], "price": p["price"], "fetched_at": r["fetched_at"],
                     "t": r["_t"]})
    out = []
    for inst, rows in sorted(by_inst.items()):
        if len({x["source"] for x in rows}) < 2:
            continue
        rows = sorted(rows, key=lambda x: x["price"])
        lo = rows[0]
        hi = next((x for x in reversed(rows) if x["source"] != lo["source"]), rows[-1])
        mid = (lo["price"] + hi["price"]) / 2
        bps = (hi["price"] - lo["price"]) / mid * 1e4 if mid else None
        skew_ms = round(abs(hi["t"] - lo["t"]) * 1000)
        excluded = []
        if skew_ms > MAX_FETCH_SKEW_MS:
            excluded.append(f"fetched {skew_ms} ms apart")
        if bps is None or bps > SUSPECT_BPS:
            excluded.append(f"difference {bps} bps above {SUSPECT_BPS}: probable bad price")
        out.append({"comparable": not excluded, **({"excluded": excluded} if excluded else {}),"instrument": inst, "low": {"source": lo["source"], "price": lo["price"]},
                    "high": {"source": hi["source"], "price": hi["price"]},
                    "diff_abs": hi["price"] - lo["price"],
                    "diff_bps": bps, "fetch_skew_ms": skew_ms})
    return out

BASE_INTERVAL_S = 60       # owner 2026-11-22: default tick interval
MAX_INTERVAL_S = 600       # backoff ceiling: 10 minutes
STORE_LIMIT_BYTES = 1 << 30  # 1 GiB: above this, the oldest daily files are gzipped
RETRY_STATUS = lambda code: code == 429 or 500 <= code <= 599

def load_state(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}

def save_state(path, state):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)
    os.replace(tmp, path)

def backoff(state, source, now, base, code):
    """Double this exchange's interval on 429/5xx (ceiling MAX_INTERVAL_S)."""
    cur = state.get(source, {}).get("interval_s", base)
    nxt = min(max(cur * 2, base * 2), MAX_INTERVAL_S)
    state[source] = {"interval_s": nxt, "next_at": now + nxt, "last_status": code,
                     "since": state.get(source, {}).get("since") or now_iso()}

def reset(state, source):
    state.pop(source, None)

def day_file(ddir, when=None):
    day = (when or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    return os.path.join(ddir, f"price_observations-{day}.jsonl")

def compress_old(ddir, limit=STORE_LIMIT_BYTES, today=None):
    """Keep the store at or under `limit`: gzip the oldest daily files first (never today's).
    Nothing is deleted. Returns the files compressed."""
    import glob, gzip, shutil
    today = today or os.path.basename(day_file(ddir))
    files = sorted(glob.glob(os.path.join(ddir, "price_observations-*.jsonl*")))
    total = sum(os.path.getsize(f) for f in files)
    done = []
    for f in files:
        if total <= limit:
            break
        if f.endswith(".gz") or os.path.basename(f) == today:
            continue
        before = os.path.getsize(f)
        with open(f, "rb") as src, gzip.open(f + ".gz.tmp", "wb") as dst:
            shutil.copyfileobj(src, dst)
        os.replace(f + ".gz.tmp", f + ".gz")
        os.remove(f)
        total += os.path.getsize(f + ".gz") - before
        done.append(os.path.basename(f) + ".gz")
    return done, total

TICK_DEADLINE_S = 55  # a tick that has not finished by then exits, so the next 60 s tick can start

def main(argv):
    import fcntl, signal
    def deadline(_sig, _frm):
        print(f"DEADLINE\ttick did not finish in {TICK_DEADLINE_S} s", file=sys.stderr)
        os._exit(4)
    if hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, deadline)
        signal.alarm(TICK_DEADLINE_S)
    hosts = check_scope(SOURCES)
    ddir = data_dir(argv)
    os.makedirs(ddir, exist_ok=True)
    lock = open(os.path.join(ddir, ".tick.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close(); print("BUSY\tanother tick holds the lock"); return 0
    try:
        return _tick(argv, ddir, hosts)
    finally:
        lock.close()

def _tick(argv, ddir, hosts):
    import signal, urllib.error
    if "--audit-net" in argv:
        install_net_audit(os.path.join(ddir, "net_audit.jsonl"), hosts)
    base = float(argv[argv.index("--interval-s") + 1]) if "--interval-s" in argv else BASE_INTERVAL_S
    state_path = os.path.join(ddir, "backoff_state.json")
    state = load_state(state_path)
    started = now_iso()
    results = []
    for s in SOURCES:
        t = time.time()
        rec = {"source": s["source"], "category": s["category"], "url": s["url"],
               "fetched_at": now_iso(), "_t": t}
        b = state.get(s["source"])
        if b and b.get("next_at", 0) > t:
            rec.update(ok=False, skipped="backoff", backoff_interval_s=b["interval_s"],
                       backoff_until=datetime.fromtimestamp(b["next_at"], timezone.utc).isoformat(timespec="seconds"),
                       elapsed_ms=0)
            results.append(rec)
            continue
        server_date = None
        try:
            body, server_date = get(s["url"])
            rec["prices"] = s["parse"](body)
            rec["ok"] = True
        except urllib.error.HTTPError as e:
            rec["ok"] = False
            rec["http_status"] = e.code
            rec["error"] = f"HTTP {e.code}"
            if RETRY_STATUS(e.code):
                backoff(state, s["source"], t, base, e.code)
                rec["backoff_interval_s"] = state[s["source"]]["interval_s"]
        except Exception as e:
            rec["ok"] = False
            rec["error"] = repr(e)[:300]
        rec["elapsed_ms"] = round((time.time() - t) * 1000)
        if rec["ok"]:
            freshness(rec, server_date)
            if s["source"] in state and not any(
                    x["source"] == s["source"] and x.get("http_status") for x in results):
                reset(state, s["source"])
        results.append(rec)
    if hasattr(signal, "SIGALRM"):
        signal.alarm(0)  # reading is over; never cut the write below
    save_state(state_path, state)
    tick = {"schema": SCHEMA, "label": LABEL, "disclaimer": DISCLAIMER, "started_at": started, "finished_at": now_iso(),
            "interval_s": base,
            "sources": [{k: v for k, v in r.items() if k != "_t"} for r in results],
            "gaps": gaps(results)}
    out = day_file(ddir)
    with open(out, "a") as f:
        f.write(json.dumps(tick, ensure_ascii=False) + "\n")
    compressed, total = compress_old(ddir, today=os.path.basename(out))
    ok = sum(r["ok"] for r in results)
    fresh = sum(bool(r.get("fresh")) for r in results)
    skipped = sum(1 for r in results if r.get("skipped"))
    print(f"{started}\tOK {ok}\tFRESH {fresh}\tSKIPPED {skipped}\tFAILED {len(results) - ok - skipped}"
          f"\tSTORE {total} B" + (f"\tCOMPRESSED {','.join(compressed)}" if compressed else ""))
    for r in results:
        if r["ok"] and not r.get("fresh"):
            print(f"  NOT_FRESH\t{r['source']}\t{'; '.join(r['not_fresh_reasons'])}")
        elif r.get("error"):
            print(f"  FAILED\t{r['source']}\t{r['error']}" + (f"\tbackoff {r['backoff_interval_s']:.0f}s" if r.get("backoff_interval_s") else ""))
    for g in tick["gaps"]:
        print(f"  {'OBSERVED' if g['comparable'] else 'EXCLUDED'}\t{g['instrument']}\t{g['diff_bps']:.2f} bps\t{g['low']['source']}<{g['high']['source']}\tskew {g['fetch_skew_ms']} ms")
    return 0 if ok or skipped else 3

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
