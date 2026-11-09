# 第4回 技術メモ：演習と宿題（基礎）を再現するための手順とコード

このメモでは、第4回の演習（STEP 1〜3）と宿題（基礎）を、他の人が再現できるように手順をまとめます。今回は、STEP 1 のラベル付けを人ではなく ChatGPT の GPT-6 に頼みました。その手順も含めて書きます。結果と考察は [answer.md](answer.md) にあります。

`app/` と `tests/` は変えていません。変えたのは、採点の基準 `data/eval/rubric.md`（STEP 3）だけです。

## 0. 共通：実行環境

| 用途 | 環境 | 使ったもの |
|---|---|---|
| 採点（STEP 2・3、宿題） | repo の環境（Pydantic AI 2.57.0） | `uv sync --frozen`。`GEMINI_API_KEY` が必要 |
| ラベル付け（STEP 1 の代わり） | ブラウザの ChatGPT（GPT-6、思考量 Extra High） | API ではなく、ChatGPT の画面に依頼文を貼った。OpenAI の API キーは使っていない |
| ラベル付け（人が付けるとき） | Streamlit 1.66.1 | `uv run --with streamlit==1.66.1 streamlit run tools/annotate.py`（今回は未使用） |

- 採点のモデルは、既定で `gemini-3.5-flash-lite`（`AIE_MODEL` か `--model` で変える）。temperature は 0 です
- Pydantic AI の起動時のバナーは、`PYDANTIC_AI_NO_BANNER=1` で消せます
- `lectures/04/homework/` のスクリプトはパスを指定して実行するので、先頭でリポジトリ直下を `sys.path` に足しています（第3回と同じ）

### 上流の取り込み（2026-11-09）

第4回の配布と同時に、上流で MCP の回が第5回から第6回に移りました（上流 `6df1d11`）。取り込みのときに次を行いました。

- 第5回として取り組んだ MCP の成果物を `lectures/05/` から `lectures/06/` に移し、本文のパスと回の番号を第6回に合わせた
- `app/mcp_server.py` と `tests/test_agent.py` の競合は、上流の直し方を含むこちらの実装を残した
- `tests/test_tools.py` の「第4回には用語が無い」という決め打ちが、第4回の用語が用語集に入ったことで落ちた。用語が無い回をその場で選ぶように直した

---

## 1. STEP 1：ラベル付けを GPT-6 に頼む

演習では、人が `tools/annotate.py` の画面で 10 件にラベルを付けます。今回は講師（人）と AI のラベルの差を見るため、GPT-6 に付けさせました。

### 1.1 依頼文を作る

[homework/make_label_prompt.py](homework/make_label_prompt.py) が依頼文を作ります（API キー不要）。

```bash
uv run python lectures/04/homework/make_label_prompt.py > /tmp/label_prompt.txt
```

- 渡すのは、ラベル付けの画面に出るのと同じ情報だけです：質問・回答・参照（用語集のエントリと、期待するふるまい）・5 つの基準の説明
- 参照は `app.judge.reference_text` で作ります。Gemini の採点に渡る参照と同じ文面になるので、ラベルを付ける側と採点する側で、見ている材料がそろいます
- 基準の説明は、`problem.md` の基準の表と、ラベル付け画面の説明（`tools/annotate.py` の `CRITERION_HELP`）をもとにしました。採点の基準（`rubric.md`）の細かい決まり（「基準は独立に見る」の理由など）は渡していません。人がラベルを付けるときも、画面には `rubric.md` は出ないためです
- **講師のラベル（`lectures/04/reference/labels_instructor.jsonl`）は読みません。** 講師のメモには「仕込んだ失敗」の説明があり、見せると答えが漏れます
- 出力は、`labels.jsonl` と同じ形の JSON Lines を 1 つのコードブロックで返すよう指示します。画面のラベルは合格／不合格の 2 択に「迷った」のチェックなので、GPT-6 にも pass / fail を必ず選ばせ、迷ったら `unsure_flag: true` にさせました

実際に送った依頼文（5,697 文字）は、このスクリプトの出力と 1 文字も違わないことを `cmp` で確かめています。

### 1.2 ChatGPT に送る

1. ブラウザで chatgpt.com を開き、ログインする
2. 入力欄の右のモデル選択で **GPT-6** を選ぶ。思考量は **Extra High** にした
3. 依頼文を貼り付けて送る。長い文章を貼るときは、改行の Enter で途中送信されないよう、クリップボードから貼り付ける
4. 返ってきたコードブロック（10 行の JSON Lines）をコピーする

今回は Claude Code から Claude in Chrome（ブラウザ拡張）で操作しました。入力欄（`#prompt-textarea`）への貼り付けは、次の JavaScript で `paste` イベントを送っています。

```javascript
const ed = document.querySelector('#prompt-textarea');
ed.focus();
const dt = new DataTransfer(); dt.setData('text/plain', promptText);
ed.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true}));
```

### 1.3 保存する

返ってきた 10 行を `lectures/04/labels.jsonl` に保存します。各行に `"labeler": "GPT-6 (ChatGPT, 思考量 Extra High)"` を足して、人のラベルと区別できるようにしました（`app.judge` は余分なキーを無視します）。

```json
{"id":"05","grounding":"pass","scope":"pass","hint":"pass","clarity":"pass","lecture_mark":"fail","unsure_flag":true,"note":"…","labeler":"GPT-6 (ChatGPT, 思考量 Extra High)"}
```

### 1.4 講師のラベルと比べる（API 不要）

```bash
uv run python -m app.judge --compare lectures/04/reference/labels_instructor.jsonl
```

基準別の一致数と、判定が違う項目（講師のメモ付き）が出ます。

---

## 2. STEP 2：Gemini に採点させる

```bash
uv run python -m app.judge          # 結果は lectures/04/judge_result.json
```

- 採点のプロンプトは `data/eval/rubric.md` の全文に、出力の形式（基準ごとに reason を先に書き、そのあと verdict）を足したものです（`app/judge.py` の `build_judge`）
- **ラベルは採点に使われません。** `judge_cases` が受け取るのは評価セット（質問・回答・参照）だけで、ラベルは `summarize` で一致率を数えるときにだけ使います。そのため、同じ採点を別のラベルと比べたいときは、ラベルファイルだけを変えて流せます

```bash
# 講師のラベルと比べる（採点はもう一度行われる）
uv run python -m app.judge --labels lectures/04/reference/labels_instructor.jsonl --out lectures/04/judge_result_before_vs_instructor.json
```

STEP 3 で採点し直すと `judge_result.json` が上書きされるので、直す前の結果は `judge_result_before.json` として残しました。

### 監査：同じ入力でも判定が変わった

上の 2 回（GPT-6 のラベルと比べた回と、講師のラベルと比べた回）は、Gemini への入力がまったく同じです。それでも、#06 の判定が違いました。2 つの結果ファイルの判定を、次のように比べて確かめました。

```python
import json
a = json.load(open("lectures/04/judge_result_before.json"))["verdicts"]
b = json.load(open("lectures/04/judge_result_before_vs_instructor.json"))["verdicts"]
for cid in a:
    for k in a[cid]:
        if a[cid][k]["verdict"] != b[cid][k]["verdict"]:
            print(cid, k, a[cid][k]["verdict"], b[cid][k]["verdict"])
# 06 grounding fail pass
# 06 clarity pass fail
```

コードを見直し、2 回とも同じ関数（`build_llm_model`・`build_judge`・`judge_cases`）を、同じ採点の基準で呼んでいることを確かめました。違いは、temperature 0 でも残るモデル側の揺れです。そのため宿題では、1 回の採点ではなく、同じ設定で 3 回ずつ採点しました。

---

## 3. STEP 3：基準を 1 か所直して、もう一度採点する

要確認（unsure）になったのは #05 の根拠（用語集にない RAG を、「用語集にはない」と伝えたうえで一般的に説明した回答）の 1 件でした。方針を pass に決め、`data/eval/rubric.md` を次のように直しました。

```diff
 - 回答が「分からない」「用語集にはない」と伝えているだけなら、矛盾はないので pass
+- 用語集にない語を、「用語集にはない」と伝えたうえで一般的に説明するのは、断定ではない（pass）。用語集にないと伝えずに説明した場合は fail
 ...
 ## まだ決めていないこと（当てはまる回答は unsure にする）

-- 用語集にない語について、「用語集にはない」と伝えたうえで一般的な説明をすることが、「推測で断定する」にあたるかどうか
+- （なし）
```

- 直すのは 1 か所だけです（根拠の基準の下に 1 行を足し、決めた論点を消す）
- 後半の「伝えずに説明した場合は fail」は、方針を決めた結果、断らずに説明する回答まで pass になるのを防ぐために足しました
- 直したあと `uv run pytest -q` が通ることを確かめました。`tests/test_judge.py` に、評価セットと採点の基準が食い違っていないかを確かめるテストがあります

```bash
uv run python -m app.judge          # 直した基準で採点し直す（judge_result.json を上書き）
```

---

## 4. 宿題（基礎）：採点のモデルを変える

[homework/model_compare.py](homework/model_compare.py) は、採点のモデルだけを変え、同じ設定で何回か採点して、GPT-6 と講師の両方のラベルと比べます。

```bash
uv run python lectures/04/homework/model_compare.py --models gemini-3.5-flash-lite gemini-3.5-flash --reps 3
```

- 採点は `app.judge` と同じ関数（`build_judge`・`judge_cases`・`summarize`）で行います。採点の基準は、STEP 3 で直したあとの `rubric.md` です
- 1 回の採点結果を、2 つのラベル（`lectures/04/labels.jsonl` と講師のラベル）の両方と比べます。ラベルは採点に使われないので、採点は 1 回で済みます
- 1 件ごとに 1 秒待ちます（レート制限の対策）
- **途中から続けられます。** 1 回分の採点が終わるたびに結果を保存し、もう一度実行すると、済んだ (モデル, 回) を飛ばします。今回 `gemini-3.5-flash` の 3 回目で、サーバー側のエラー（500 INTERNAL）が出たため、この仕組みを足しました
- 一時的なエラー（429・500・503）は、30 秒待ってその 1 回分をやり直します（最大 4 回）

結果（`homework/results/model_compare.json`）の各要素は、`model`・`rep`・`verdicts`（基準ごとの reason と verdict）・`summary`（`gpt6` と `instructor` のそれぞれとの一致率・要確認・不一致）です。モデルごとの揺れは、次のように数えられます。

```python
import json
runs = json.load(open("lectures/04/homework/results/model_compare.json"))
for m in ("gemini-3.5-flash-lite", "gemini-3.5-flash"):
    rs = [r for r in runs if r["model"] == m]
    for cid in rs[0]["verdicts"]:
        for k in ("grounding", "scope", "hint", "clarity"):
            vs = [r["verdicts"][cid][k]["verdict"] for r in rs]
            if len(set(vs)) > 1:
                print(m, cid, k, vs)   # 今回は flash-lite の #10 scope だけ
```

---

## 5. 自分（人）のラベルに差し替えるとき

1. GPT-6 のラベルを退避する：`cp lectures/04/labels.jsonl lectures/04/labels_gpt6.jsonl`
2. `uv run --with streamlit==1.66.1 streamlit run tools/annotate.py` で 10 件にラベルを付ける（`lectures/04/labels.jsonl` に保存される）
3. 比べる
   - 人と講師：`uv run python -m app.judge --compare lectures/04/reference/labels_instructor.jsonl`
   - 人と GPT-6：`uv run python -m app.judge --compare lectures/04/labels_gpt6.jsonl`
4. STEP 2・3 と宿題をもう一度流す。`model_compare.py` の `LABELS` に、人のラベルを足すと 3 者を一度に比べられる

注意：`rubric.md` は STEP 3 で直したあとの状態です。直す前から流し直すときは、配布時の版を取り出して `--rubric` で渡します。

```bash
git show lec04-start:data/eval/rubric.md > /tmp/rubric_before.md
uv run python -m app.judge --rubric /tmp/rubric_before.md --out lectures/04/judge_result_before.json
```

---

## 6. 結果ファイル

| 場所 | 内容 |
|---|---|
| `lectures/04/labels.jsonl` | STEP 1：GPT-6 が付けたラベル（`labeler` 付き） |
| `lectures/04/judge_result_before.json` | STEP 2：直す前の採点（GPT-6 のラベルと比較） |
| `lectures/04/judge_result_before_vs_instructor.json` | STEP 2：直す前の採点（講師のラベルと比較。別の実行） |
| `lectures/04/judge_result.json` | STEP 3：直したあとの採点（GPT-6 のラベルと比較） |
| `lectures/04/homework/results/model_compare.json` | 宿題：flash-lite と flash の各 3 回の採点と、2 つのラベルとの比較 |
| `lectures/04/homework/make_label_prompt.py` | STEP 1 の代わり：GPT-6 への依頼文を作る |
| `lectures/04/homework/model_compare.py` | 宿題：モデルを変えて複数回採点し、比べる |

モデルの出力は、temperature 0 でも実行ごとに揺れます。同じ手順でも、細部の判定は変わることがあります。
