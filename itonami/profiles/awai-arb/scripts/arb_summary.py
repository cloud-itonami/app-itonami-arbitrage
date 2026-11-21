#!/usr/bin/env python3
# awai-arb price-difference summary (AWAI-3207). Local only: reads
# the daily price_observations-*.jsonl[.gz] files and prints, per instrument, how many observations had a
# difference at or above a threshold (count), how large it was (bps), and how long it
# lasted (episodes of consecutive observations at or above the threshold).
# Reads and writes only the local data dir; makes no network call.
#
#   python3 arb_summary.py [--data-dir DIR] [--threshold-bps 10] [--max-skew-ms 5000]
#                          [--since ISO] [--interval-s 60] [--unchanged-run 6] [--json]
#
# Duration is bounded by the observation interval: duration_min_s is first-to-last
# observation at/above the threshold; duration_max_s runs from the observation before
# the episode to the one after it (null when the episode is at either end of the data,
# so it may still be running). An observation whose two prices were fetched more than
# --max-skew-ms apart, or that arb_measure.py marked not comparable (a source not fresh,
# or a difference above its bad-price bound), is not counted. The summary also reports how
# old the last observation is (STALE beyond 2 x --interval-s) and lists sources whose price
# did not change for --unchanged-run ticks in a row (possible frozen feed).
import glob, gzip, json, os, statistics, sys, time
from datetime import datetime

def arg(argv, name, default):
    return argv[argv.index(name) + 1] if name in argv else default

def data_dir(argv):
    if "--data-dir" in argv:
        return os.path.abspath(arg(argv, "--data-dir", None))
    if os.environ.get("AWAI_ARB_DATA_DIR"):
        return os.path.abspath(os.environ["AWAI_ARB_DATA_DIR"])
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workspace")

def ts(s):
    return datetime.fromisoformat(s).timestamp()

def summarize(ticks, threshold, max_skew_ms):
    series = {}
    for t in ticks:
        for g in t.get("gaps") or []:
            series.setdefault(g["instrument"], []).append((ts(t["started_at"]), t["started_at"], g))
    out = {}
    for inst, rows in sorted(series.items()):
        rows.sort(key=lambda r: r[0])
        usable = [r for r in rows if r[2].get("diff_bps") is not None and r[2].get("comparable", True)
                  and r[2]["fetch_skew_ms"] <= max_skew_ms]
        bps = [r[2]["diff_bps"] for r in usable]
        above = [r for r in usable if r[2]["diff_bps"] >= threshold]
        episodes, cur = [], []
        for i, r in enumerate(usable):
            if r[2]["diff_bps"] >= threshold:
                if not cur:
                    cur = [i]
                cur_end = i
            elif cur:
                episodes.append((cur[0], cur_end)); cur = []
        if cur:
            episodes.append((cur[0], cur_end))
        eps = []
        for a, b in episodes:
            seg = usable[a:b + 1]
            eps.append({"start": usable[a][1], "end": usable[b][1], "observations": len(seg),
                        "max_bps": max(x[2]["diff_bps"] for x in seg),
                        "duration_min_s": round(usable[b][0] - usable[a][0]),
                        "duration_max_s": round(usable[b + 1][0] - usable[a - 1][0])
                        if a > 0 and b + 1 < len(usable) else None,
                        "open_at_edge": a == 0 or b + 1 == len(usable)})
        out[inst] = {
            "observations": len(rows), "usable": len(usable),
            "set_aside": len(rows) - len(usable),
            "at_or_above_threshold": len(above),
            "diff_bps": {"min": min(bps), "median": statistics.median(bps), "max": max(bps)} if bps else None,
            "episodes": eps,
        }
    return out

PEGGED = {"USDC-USD"}

def unchanged_runs(ticks, min_run):
    """Sources whose price for an instrument stayed identical over >= min_run ticks in a row:
    a frozen feed looks like this, so such runs are listed for a person to check."""
    runs, last = [], {}
    for t in ticks:
        for s in t.get("sources") or []:
            if s.get("category") != "crypto-spot":
                continue
            for p in s.get("prices") or []:
                if p["instrument"] in PEGGED:
                    continue  # a pegged stablecoin quote is often unchanged for hours
                k = (s["source"], p["instrument"])
                v, n, start = last.get(k, (None, 0, None))
                last[k] = (p["price"], n + 1, start) if p["price"] == v else (p["price"], 1, t["started_at"])
                if last[k][1] == min_run:
                    runs.append({"source": k[0], "instrument": k[1], "price": p["price"], "since": last[k][2]})
    return runs

def data_files(ddir):
    """Daily files (plain or gzipped by arb_measure.py) plus the single pre-2026-11-22 file."""
    legacy = os.path.join(ddir, "price_observations.jsonl")
    daily = sorted(glob.glob(os.path.join(ddir, "price_observations-*.jsonl"))
                   + glob.glob(os.path.join(ddir, "price_observations-*.jsonl.gz")))
    return ([legacy] if os.path.exists(legacy) else []) + daily

def main(argv):
    ddir = data_dir(argv)
    threshold = float(arg(argv, "--threshold-bps", "10"))
    max_skew = float(arg(argv, "--max-skew-ms", "5000"))
    since = arg(argv, "--since", None)
    files = data_files(ddir)
    if not files:
        print(f"NO_DATA\t{ddir}"); return 3
    path = ddir
    ticks = []
    for fp in files:
        opener = gzip.open if fp.endswith(".gz") else open
        with opener(fp, "rt") as f:
            for line in f:
                line = line.strip()
                if line:
                    t = json.loads(line)
                    if since is None or ts(t["started_at"]) >= ts(since):
                        ticks.append(t)
    ticks.sort(key=lambda t: ts(t["started_at"]))
    interval_s = float(arg(argv, "--interval-s", "60"))
    last_age = round(time.time() - ts(ticks[-1]["started_at"])) if ticks else None
    summary = {"label": "価格差の観測データの集計 (price-difference observation summary)",
               "disclaimer": ticks[-1].get("disclaimer") if ticks else None,
               "last_observation_age_s": last_age,
               "stale": last_age is None or last_age > 2 * interval_s,
               "unchanged_price_runs": unchanged_runs(ticks, int(arg(argv, "--unchanged-run", "6"))),
               "file": path, "ticks": len(ticks),
               "first": ticks[0]["started_at"] if ticks else None,
               "last": ticks[-1]["started_at"] if ticks else None,
               "threshold_bps": threshold, "max_skew_ms": max_skew,
               "instruments": summarize(ticks, threshold, max_skew)}
    if "--json" in argv:
        print(json.dumps(summary, ensure_ascii=False, indent=2)); return 0
    print(summary["label"]); print(summary["disclaimer"] or "")
    print(f"TICKS\t{summary['ticks']}\t{summary['first']} .. {summary['last']}")
    print(f"LAST_AGE\t{last_age} s\t{'STALE: no new observation within 2 intervals' if summary['stale'] else 'fresh'}")
    for r in summary["unchanged_price_runs"]:
        print(f"UNCHANGED\t{r['source']}\t{r['instrument']}\t{r['price']} since {r['since']} (frozen feed?)")
    print(f"THRESHOLD\t{threshold} bps\tMAX_SKEW\t{max_skew:.0f} ms")
    for inst, s in summary["instruments"].items():
        b = s["diff_bps"] or {}
        print(f"{inst}\tobs {s['observations']}\tusable {s['usable']}\tat/above {s['at_or_above_threshold']}"
              f"\tbps min {b.get('min', 0):.2f} med {b.get('median', 0):.2f} max {b.get('max', 0):.2f}"
              f"\tepisodes {len(s['episodes'])}")
        for e in s["episodes"]:
            print(f"  EPISODE\t{e['start']}\t{e['observations']} obs\tmax {e['max_bps']:.2f} bps"
                  f"\t{e['duration_min_s']}s..{e['duration_max_s'] if e['duration_max_s'] is not None else 'open'}s")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
