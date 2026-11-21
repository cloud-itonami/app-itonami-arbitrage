# Offline checks for the private price-difference observation (AWAI-3207).
# Every price below is a made-up round number, not an observed one.
#   python3 -m unittest discover -s test -p 'arb_*_test.py'
import glob, gzip, importlib.util, io, json, os, sys, tempfile, unittest, urllib.error, urllib.parse
from email.utils import formatdate

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "itonami", "profiles", "awai-arb", "scripts")

def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, name + ".py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

measure, summary = load("arb_measure"), load("arb_summary")

FIXTURES = {
    "api.coinbase.com": lambda url: {"data": {"amount": {"BTC-USD": "1000.6", "ETH-USD": "200", "USDC-USD": "1.0001"}[url.split("/")[-2]]}},
    "api.kraken.com": lambda url: {"error": [], "result": {
        "XXBTZUSD": {"a": ["1000.1"], "b": ["999.9"], "c": ["1000"]},
        "XETHZUSD": {"a": ["200"], "b": ["200"], "c": ["200"]},
        "USDCUSD": {"a": ["0.9999"], "b": ["0.9999"], "c": ["0.9999"]}}},
    "x402.nexus": lambda url: {"items": [{"seller": "s", "method": "GET", "path-prefix": "/x", "price": {"usd": "0.01", "asset": "USDC"}}]},
    "api.murakumo.cloud": lambda url: {"data": [{"id": "m", "free": True}]},
}

class Measure(unittest.TestCase):
    def test_sources_are_spot_or_non_financial_only(self):
        self.assertTrue(all(s["category"] in measure.ALLOWED_CATEGORIES for s in measure.SOURCES))
        hosts = {urllib.parse.urlsplit(s["url"]).hostname for s in measure.SOURCES}
        self.assertNotIn("torihiki-node.04-feasts-minded.workers.dev", hosts)

    def test_out_of_scope_source_is_refused(self):
        with self.assertRaises(SystemExit):
            measure.check_scope([{"source": "x", "category": "derivative", "url": "https://e.x/"}])

    def test_tick_records_times_prices_and_gaps_without_sending(self):
        calls = []
        def fake_get(url, timeout=25):
            calls.append(url)
            return FIXTURES[urllib.parse.urlsplit(url).hostname](url), formatdate(usegmt=True)
        measure.get = fake_get
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(measure.main(["--data-dir", d]), 0)
            files = glob.glob(os.path.join(d, "price_observations-*.jsonl"))
            self.assertEqual(len(files), 1)
            tick = json.loads(open(files[0]).read())
        self.assertEqual(len(calls), len(measure.SOURCES))
        self.assertTrue(all(s["ok"] and s["fresh"] and s["fetched_at"] for s in tick["sources"]))
        self.assertTrue(all(g["comparable"] for g in tick["gaps"]))
        btc = next(g for g in tick["gaps"] if g["instrument"] == "BTC-USD")
        self.assertEqual((btc["low"]["source"], btc["high"]["source"]), ("kraken", "coinbase"))
        self.assertAlmostEqual(btc["diff_bps"], 0.6 / 1000.3 * 1e4, places=6)
        self.assertIn("価格差の観測データ", tick["label"])
        self.assertIn("手数料・送金時間・スリッページを含みません", tick["disclaimer"])

    def rec(self, **kw):
        r = {"category": "crypto-spot", "elapsed_ms": 100, "_t": 1_800_000_000.0,
             "prices": [{"instrument": "BTC-USD", "price": 1000.0}]}
        r.update(kw); return r

    def test_stale_server_date_is_not_fresh(self):
        r = self.rec(); measure.freshness(r, formatdate(1_800_000_000 - 3600, usegmt=True))
        self.assertFalse(r["fresh"]); self.assertIn("server Date", r["not_fresh_reasons"][0])

    def test_bad_price_and_missing_date_are_not_fresh(self):
        r = self.rec(prices=[{"instrument": "BTC-USD", "price": 0.0}]); measure.freshness(r, None)
        self.assertFalse(r["fresh"]); self.assertEqual(len(r["not_fresh_reasons"]), 2)

    def test_not_fresh_source_and_outlier_are_not_compared(self):
        mk = lambda src, price, fresh=True: {"source": src, "ok": True, "fresh": fresh, "fetched_at": "x",
                                             "_t": 0.0, "prices": [{"instrument": "BTC-USD", "price": price}]}
        self.assertEqual(measure.gaps([mk("a", 1000), mk("b", 1001, fresh=False)]), [])
        g, = measure.gaps([mk("a", 1000), mk("b", 1100)])
        self.assertFalse(g["comparable"]); self.assertIn("probable bad price", g["excluded"][0])

class Backoff(unittest.TestCase):
    def run_ticks(self, d, status_by_host, clock):
        calls = []
        def fake_get(url, timeout=25):
            host = urllib.parse.urlsplit(url).hostname
            calls.append(host)
            code = status_by_host.get(host)
            if code:
                raise urllib.error.HTTPError(url, code, "x", {}, io.BytesIO(b""))
            return FIXTURES[host](url), formatdate(usegmt=True)
        measure.get = fake_get
        real = measure.time.time
        measure.time.time = lambda: clock[0]
        try:
            self.assertEqual(measure.main(["--data-dir", d]), 0)
        finally:
            measure.time.time = real
        return calls

    def test_429_backs_off_that_exchange_only_and_doubles_to_ceiling(self):
        with tempfile.TemporaryDirectory() as d:
            clock = [1_800_000_000.0]
            calls = self.run_ticks(d, {"api.kraken.com": 429}, clock)
            self.assertEqual(calls.count("api.kraken.com"), 1)
            st = json.load(open(os.path.join(d, "backoff_state.json")))
            self.assertEqual(list(st), ["kraken"]); self.assertEqual(st["kraken"]["interval_s"], 120)
            clock[0] += 60  # next launchd tick: kraken still waiting, the others are read
            calls = self.run_ticks(d, {"api.kraken.com": 429}, clock)
            self.assertNotIn("api.kraken.com", calls); self.assertIn("api.coinbase.com", calls)
            for expect in (240, 480, 600, 600):
                clock[0] += 601
                self.run_ticks(d, {"api.kraken.com": 503}, clock)
                self.assertEqual(json.load(open(os.path.join(d, "backoff_state.json")))["kraken"]["interval_s"], expect)
            clock[0] += 601
            self.run_ticks(d, {}, clock)  # first success resets
            self.assertEqual(json.load(open(os.path.join(d, "backoff_state.json"))), {})

    def test_coinbase_5xx_stops_its_other_pairs_in_the_same_tick(self):
        with tempfile.TemporaryDirectory() as d:
            calls = self.run_ticks(d, {"api.coinbase.com": 502}, [1_800_000_000.0])
            self.assertEqual(calls.count("api.coinbase.com"), 1)

    def test_404_does_not_back_off(self):
        with tempfile.TemporaryDirectory() as d:
            self.run_ticks(d, {"x402.nexus": 404}, [1_800_000_000.0])
            self.assertEqual(json.load(open(os.path.join(d, "backoff_state.json"))), {})

class Store(unittest.TestCase):
    def test_oldest_days_are_gzipped_first_and_today_is_kept(self):
        with tempfile.TemporaryDirectory() as d:
            for day in ("2026-11-20", "2026-11-21", "2026-11-22"):
                with open(os.path.join(d, f"price_observations-{day}.jsonl"), "w") as f:
                    f.write(('{"started_at": "%sT00:00:00+00:00", "gaps": []}\n' % day) * 2000)
            size = os.path.getsize(os.path.join(d, "price_observations-2026-11-22.jsonl"))
            done, total = measure.compress_old(d, limit=int(size * 2.5), today="price_observations-2026-11-22.jsonl")
            self.assertEqual(done, ["price_observations-2026-11-20.jsonl.gz"])
            done, _ = measure.compress_old(d, limit=1, today="price_observations-2026-11-22.jsonl")
            self.assertEqual(done, ["price_observations-2026-11-21.jsonl.gz"])
            self.assertTrue(os.path.exists(os.path.join(d, "price_observations-2026-11-22.jsonl")))
            self.assertEqual(len(summary.data_files(d)), 3)
            with gzip.open(os.path.join(d, "price_observations-2026-11-20.jsonl.gz"), "rt") as f:
                self.assertEqual(sum(1 for _ in f), 2000)

class Summary(unittest.TestCase):
    def tick(self, t, bps, skew=100):
        return {"started_at": f"2026-11-22T00:{t:02d}:00+00:00",
                "gaps": [{"instrument": "BTC-USD", "diff_bps": bps, "fetch_skew_ms": skew}]}

    def test_count_size_and_duration(self):
        ticks = [self.tick(0, 1), self.tick(5, 12), self.tick(10, 20), self.tick(15, 2),
                 self.tick(20, 30, skew=9000), self.tick(25, 15)]
        s = summary.summarize(ticks, 10, 5000)["BTC-USD"]
        self.assertEqual((s["observations"], s["usable"], s["set_aside"]), (6, 5, 1))
        self.assertEqual(s["at_or_above_threshold"], 3)
        first, last = s["episodes"]
        self.assertEqual((first["observations"], first["max_bps"]), (2, 20))
        self.assertEqual((first["duration_min_s"], first["duration_max_s"]), (300, 900))
        self.assertTrue(last["open_at_edge"]); self.assertIsNone(last["duration_max_s"])

    def test_frozen_feed_is_listed(self):
        ticks = [{"started_at": f"2026-11-22T00:{i:02d}:00+00:00", "sources": [
            {"source": "kraken", "category": "crypto-spot", "prices": [{"instrument": "BTC-USD", "price": 1.0}]}]}
            for i in range(6)]
        runs = summary.unchanged_runs(ticks, 6)
        self.assertEqual([(r["source"], r["since"]) for r in runs], [("kraken", "2026-11-22T00:00:00+00:00")])

if __name__ == "__main__":
    unittest.main()
