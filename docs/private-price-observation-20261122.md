# 価格差の観測データ：非公開 cron の準備（AWAI-3207、2026-11-22）

オーナー決定（2026-11-22、委任）と Legal のメモ（`awai-3207-arb-advice.md`）による。
観測は非公開で、結果はこの Mac の手元に記録するだけ。費用は 0（有料 API・有料 host を使わない）。
公開 feed、有料 gate、アフィリエイト、個別の通知、host への配置はしない。

> 投資助言ではありません。売買の提案や推奨でもありません。表示する差は、手数料・送金時間・
> スリッページを含みません。各価格は記録した取得時刻の値です。

## 1. 外した source

| source | どこにあったか | 種類 | 扱い |
|---|---|---|---|
| torihiki-node devnet `/head` `/book` | `scripts/arb_measure.py`（cron `awai-arb-measure`） | perpetual の板（margin・funding・liquidation。`kotoba-lang/torihiki` README） | 外した。`EXCLUDED` に理由つきで残す |
| Yahoo Finance、Stooq、JPX、REIT.com | `worker/kotodama.jsonld` の prompt | 有価証券（株・ETF・REIT） | prompt から外した |
| CME、LME | 同上 | 先物・先渡し | 同上 |
| FRED | 同上 | 金利・マクロ指標（証券・先物の比較に使う前提） | 同上 |
| FX（`arb-fx`） | 同上の channel | 通貨（金商法 2 条 24 項 3 号の金融商品） | channel を外した |
| `arb-eq` `arb-fut` `arb-com` `arb-re` | 同上の channel | 株式・先物・商品の現物/先物・REIT | channel を外した |
| CoinGecko、MLIT 地価公示 | 同上の prompt | 現物暗号資産の集計／地価（金融商品でない） | 範囲内だが cron では使っていないので書かない |

外部へ送る経路も止めた（cron は手元の記録だけにする）:

- `awai-arb-propose-post`（`arb_post.py`、ossekai intake へ POST）: `enabled: false`。
- `awai-arb-ossekai-report`（murakumo の推論で「提案」を下書き）: `enabled: false`。
- `yakuwari.edn` / `itonami.edn` の `propose_trade` を `:blocked` にした。
- `arb_mail.py`（Resend）は cron に入っていない。変更なし。

## 2. 残した source（GET だけ、鍵なし、無料）

| source | URL | 種類 | 記録するもの |
|---|---|---|---|
| Coinbase | `api.coinbase.com/v2/prices/{BTC,ETH,USDC}-USD/spot` | 現物の暗号資産 | spot 価格 |
| Kraken | `api.kraken.com/0/public/Ticker?pair=XBTUSD,ETHUSD,USDCUSD` | 現物の暗号資産 | bid・ask・mid・last |
| x402.nexus | `x402.nexus/catalog` | 計算資源・サービスの 1 回あたりの価格（Awai Network LLC 運営） | item ごとの USD/call |
| murakumo | `api.murakumo.cloud/v1/models` | 計算資源（Awai Network LLC 運営） | model ごとの `free`・`pricing`・`withheld` |

価格差（件数・大きさ・持続時間）は、2 つ以上の取引所に同じものがある BTC-USD・ETH-USD・USDC-USD で
計算する。x402 と murakumo は今は対になる相手が無いので、価格の時系列として記録するだけ。

記録は 1 日 1 ファイル（`price_observations-YYYY-MM-DD.jsonl`、日付は UTC）。

## 3. 記録と集計

- `scripts/arb_measure.py`: 1 tick で上の 6 本を GET し、`<data-dir>/price_observations-YYYY-MM-DD.jsonl`（UTC の日付）に 1 行追記する
  （schema `awai-arb.price-observation.v1`）。各 source の取得時刻 `fetched_at`、server の `Date`、
  時計のずれ、所要時間、価格を残す。範囲外の category の source を足すと起動を拒む（`check_scope`）。
- 鮮度と誤りの検査（オーナー追加、2026-11-22）: 答えが 10 秒を超えた、server の `Date` が手元の時計から
  60 秒を超えてずれている、`Date` が無い、価格が 0 以下や非数、のどれかなら、その source は `fresh: false`
  で、比較に使わない。2 つの価格の取得時刻が 5 秒を超えて離れている、または差が 500 bps を超える（誤った
  価格の疑い）組は `comparable: false` にする。どれも記録には理由つきで残す。
- `scripts/arb_summary.py`: 手元のファイルだけを読み、銘柄ごとに、しきい値以上の件数、差の大きさ
  （最小・中央値・最大 bps）、持続（しきい値以上が続いた区間。`duration_min_s` は最初と最後の観測の間、
  `duration_max_s` は前後の観測の間で、端の区間は `open`）を出す。最後の観測が 2 間隔より古ければ
  `STALE`、同じ価格が 6 tick 続いた取引所の値は `UNCHANGED`（止まった feed の疑い。USDC は除く）。
- data dir: `--data-dir`、無ければ `$AWAI_ARB_DATA_DIR`、無ければ profile の `workspace/`。
  `itonami/profiles/*/workspace/` は `.gitignore` に入れた。
- `--audit-net`: この process の DNS・接続・urllib の request を `net_audit.jsonl` に残す。
- 検査: `python3 -m unittest discover -s test -p 'arb_*_test.py'`（network を使わない 8 件）。

## 4. この Mac での定期実行（登録済み、2026-11-22）

Owner bot の許可（2026-11-22）で launchd に登録した。条件: 間隔の既定値は 60 秒。公開の GET だけで、
API key を使わず、注文を送らない。429 や 5xx が返ったら、その取引所だけ間隔を倍に延ばす（上限 10 分）。
JSONL は 1 日 1 ファイルにし、合計が 1 GB を超えたら古いものから圧縮する。結果は外に出さない。

| | |
|---|---|
| plist | `~/Library/LaunchAgents/network.awai.arb-observe.plist`（label `network.awai.arb-observe`） |
| 実行 | `/opt/homebrew/bin/python3 -I ~/github/network-awai/app-itonami-arbitrage/itonami/profiles/awai-arb/scripts/arb_measure.py --data-dir <dir> --interval-s 60`、`StartInterval 60`、`RunAtLoad` |
| script の場所 | main の checkout `~/github/network-awai/app-itonami-arbitrage`（branch `main`） |
| 記録の dir | `~/github/workspaces/awai-arb/price-observation/` |
| 記録 | `price_observations-YYYY-MM-DD.jsonl`（日付は UTC）、古い日の `.jsonl.gz`、`backoff_state.json`（取引所ごとの延長）、`launchd.err.log`（stderr だけ。stdout は `/dev/null`。中身は JSONL にある） |

- 量: 1 tick 約 5.6 KB（murakumo の model 一覧が大半）、1 日 1440 tick で 約 8 MB。1 GB に届くのは約 4 か月後で、
  そこから古い日を gzip する（消さない。JSON は 1/10 前後になる）。今日のファイルは圧縮しない。
- 延長: 429・5xx で、その取引所だけ 120 → 240 → 480 → 600 秒。延長中の tick では `skipped: "backoff"` と
  再開時刻を記録する。最初の成功で既定値に戻る。Coinbase は 3 本の URL を 1 つの取引所として扱う。404 などは
  延長しない。ほかの取引所は 60 秒のまま。
- 1 tick は 55 秒で打ち切る（`TICK_DEADLINE_S`、exit 4、その tick は書かない）。読み終えたら打ち切りを外してから書くので、
  行が途中で切れることはない。launchd は前の tick が終わるまで次を起こさないので、止まった tick が後を塞がないようにする。
- `ProcessType` は `Standard`。最初の登録で `Background` と `LowPriorityIO` にしたら、CPU が 3.5% ほどに絞られ、
  TLS の証明書の読み込みだけで 4 分を超えて 1 行も書けなかった（2026-11-22 に確かめた）。そのため外した。
- 同時に 2 つ動かない: data dir の `.tick.lock`（手で回したときと launchd が重なったら `BUSY` で抜ける）。
- request の量: 1 分に Coinbase 3、Kraken 1、x402.nexus 1、murakumo 1。どれも公開の上限よりずっと少ない。
- Mac が眠っている間は動かない。その間は記録が空き、集計の持続時間はその空きを含んだ `duration_max_s` になる。

状態の確認・集計・止める:

```sh
launchctl print gui/$(id -u)/network.awai.arb-observe | grep -E 'state|runs|last exit'
python3 -I ~/github/network-awai/app-itonami-arbitrage/itonami/profiles/awai-arb/scripts/arb_summary.py \
  --data-dir ~/github/workspaces/awai-arb/price-observation
launchctl bootout gui/$(id -u)/network.awai.arb-observe      # 止める（unload）
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/network.awai.arb-observe.plist   # 再開
```

止めても記録は残る。登録自体をやめるときは、bootout のあとで plist を消す（記録の dir は消さない）。

## 5. 取引所 API の規約：市場データの公開再配布（公開 feed の条件の 1 つ）

2026-11-22 に調べた。規約のページは bot 対策で本文を直接取れなかったので、検索結果に引用された本文と
Kraken の開発者文書による。公開 feed を始める前に、規約の原文をブラウザで読み直す。

| 取引所 | 今の規約 | 公開 feed への意味 |
|---|---|---|
| Coinbase（Market Data Terms of Use, `coinbase.com/legal/market_data`） | 自分と自社の役員・従業員のための、非独占・譲渡不可・再許諾不可・取消可能の限定的な利用許諾。Coinbase の書面の事前同意なしに、Market Data と、それに基づく・それを参照する・それから派生したデータ・チャート・分析（Derived Works）を、組織外の第三者に再配布・表示・頒布してはならない。AI モデルの学習・評価への利用も禁止（地域版の記載）。再配布は Kaiko・Tardis.dev などの認定再配布業者との契約で扱われている。 | **このままでは公開できない。** 価格差も Derived Works にあたる。公開するなら Coinbase の書面の同意を取るか、認定再配布業者の有料 license が要る（費用 0 の方針と衝突する）。 |
| Kraken（開発者文書 `docs-legacy.kraken.com/api/docs/guides/global-intro`、Terms of Service） | 公開 endpoint のデータ（市場データ・取引所の状態など）でも、個人的でない商用の利用には事前の許可が要る。申請先は marketdata@kraken.com。API の利用は Kraken の Terms & Conditions に従う。legacy の文書なので、今の版で変わっていないか確かめる。 | **無料でも、事業としての公開 feed は事前の許可を取る前提で考える。** 個人的・内部の観測は今の規約の範囲に読める。 |
| x402.nexus、murakumo | Awai Network LLC が運営する自社の service。 | 外部の規約の制約はない。自社の公開方針で決める。 |

非公開の観測（この Mac に記録するだけ、組織外に出さない）は、Coinbase の「自分と自社のため」の
範囲、Kraken の個人・内部の利用の範囲に入ると読める。ただし Coinbase の AI 学習の禁止があるので、
記録を murakumo などの推論に入れる job（止めた `awai-arb-ossekai-report`）を戻す前に、それも確かめる。

### 出典

- Coinbase Market Data Terms of Use: <https://www.coinbase.com/legal/market_data>
- Coinbase institutional market data（認定再配布業者）: <https://www.coinbase.com/institutional/market-data>
- Kraken APIs（legacy guide）: <https://docs-legacy.kraken.com/api/docs/guides/global-intro/>
- Kraken Terms of Service: <https://www.kraken.com/legal/global-terms>
- 参考（二次資料）: <https://cryptomarkets.tools/guides/exchange-api-terms>

## 6. まだのこと

- 1 日以上の記録と、その集計の確認。merge 後の script の場所の向け直し。
- 公開 feed は、上の規約の許可、免責の表示、Legal の §3 の残りが揃うまでしない。
- `SOUL.md` の Mission と「知見の宛先」はまだ「提案」「ossekai に POST」と書いている。SOUL の人格の
  変更はオーナーの決定なので、この変更では直していない。
- `itonami.edn` の bundle CID は、`kotoba-lang/itonami-agent`（177c2bb）の `itonami-otehon bb profile refresh-bundle awai-arb` を
  store の写し（`ITONAMI_DIR` を task の `.agent-output/`）で回して計算し直した（files 9 → 10、`arb_summary.py` が増えた）。
  この tool は `itonami.edn` 全体を古い形で書き直すので、CID だけを写した。`check` はこの変更では回していない。
