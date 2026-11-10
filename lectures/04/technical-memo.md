# 第4回 技術メモ：演習と宿題（基礎）を再現するための手順とコード

このメモでは、第4回の演習（STEP 1〜3）と宿題（基礎・実装・発展）を、他の人が再現できるように手順をまとめます。今回は、STEP 1 のラベル付けを人ではなく ChatGPT の GPT-6 に頼みました。その手順も含めて書きます。結果と考察は [answer.md](answer.md) にあります。

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

## 5. 宿題（実装）：自分の評価セットを作り、自分のエージェントの回答を採点する

### 5.1 評価セットを作る（`data/eval/my_cases.jsonl`）

`tools/annotate.py` の「作問」画面と同じ形式（`id`・`category`・`question`・`answer`・`reference.glossary`・`reference.expected`）で、10 件をファイルに直接書きました。`reference.glossary` には用語集の `id` を入れます。書いたあと、すべての `id` が用語集にあることを確かめました。

```python
from app import tools
ids = {e["id"] for e in tools.load_glossary()}
missing = [g for c in cases for g in c["reference"]["glossary"] if g not in ids]   # 空なら OK
```

各件のねらいは [answer.md](answer.md) の表にあります。自分のエージェントに後から足した機能（`make_quiz` の範囲チェック、承認付きの `save_learning_log`、MCP の回で足したエラー処理）が壊れそうな入力を、意図して入れました。

**注意（今回の誤り）**：参照（`reference.glossary`）には、回答が根拠にしうる用語をすべて入れます。確認問題のように答えがランダムに変わる質問で、参照に一部の用語しか入れないと、正しい回答が「用語集にない」と判定されます（m04 で起きた）。直した版が `data/eval/my_cases_v2.jsonl` です（m04 の参照を第2回の 12 語にした。質問と回答は同じ）。

### 5.2 自分のエージェントに回答を生成させる

```bash
uv run python -m app.judge --generate --cases data/eval/my_cases.jsonl   # 回答を同じファイルに書き込む
```

- `app/judge.py` の `generate_answers` は、`app.agent` の `agent.run_sync(question)` を呼び、`str(result.output)` を回答にします
- このエージェントは `output_type=[str, DeferredToolRequests]` で、承認付きのツール（`save_learning_log`）が呼ばれると、実行せずに `DeferredToolRequests` を返して止まります。`generate_answers` はこれを想定していないので、**承認待ちのオブジェクトの文字列表現がそのまま回答になります**（m06）。評価用の生成では、次のように承認を自動で拒否して続きを実行させる方法が考えられます（今回は、壊れ方そのものを評価の対象にするため、配布のまま使いました）

```python
from pydantic_ai import DeferredToolRequests, DeferredToolResults, ToolDenied
result = agent.run_sync(question, model=model)
while isinstance(result.output, DeferredToolRequests):
    denied = DeferredToolResults(approvals={c.tool_call_id: ToolDenied("評価中のため保存しません") for c in result.output.approvals})
    result = agent.run_sync(message_history=result.all_messages(), deferred_tool_results=denied, model=model)
```

### 5.3 ラベルを付ける（GPT-6）

演習と同じ手順です（1 章）。依頼文を作るスクリプトに `--cases` を足しました。件数と例の `id` は評価セットに合わせて変わります（既定の評価セットでは、出力が演習で送った依頼文と同じであることを `cmp` で確かめています）。

```bash
uv run python lectures/04/homework/make_label_prompt.py --cases data/eval/my_cases.jsonl > /tmp/my_label_prompt.txt
```

- 保存先は `lectures/04/my_labels.jsonl`（各行に `labeler` を付けた）
- ChatGPT の画面の作りが演習のときから変わり、入力欄の `#prompt-textarea` という id が無くなっていました。入力欄をクリックしてから `document.activeElement` に `paste` イベントを送りました。返答も `[data-message-author-role]` で取れなくなっていたので、ページの本文から `{"id":"m` で始まる行を取り出しました

### 5.4 採点する

```bash
uv run python -m app.judge --cases data/eval/my_cases.jsonl --labels lectures/04/my_labels.jsonl --out lectures/04/my_judge_result.json
uv run python -m app.judge --cases data/eval/my_cases_v2.jsonl --labels lectures/04/my_labels.jsonl --out lectures/04/my_judge_result_v2.json   # 参照を直した版
```

採点の基準は、STEP 3 で直したあとの `data/eval/rubric.md` です。

### 5.5 コードで判定する基準（`homework/code_checks.py`）

```bash
uv run python lectures/04/homework/code_checks.py                                            # 自分の評価セット
uv run python lectures/04/homework/code_checks.py --cases data/eval/lec04_cases.jsonl --out /tmp/cc.json   # 演習の評価セットにも当てられる
```

API キー不要で、回答の文字列と用語集・INSTRUCTIONS だけで決まります。判定は pass / fail / na（その件には当てはまらない）です。

| チェック | 中身 | 実装の要点 |
|---|---|---|
| `lecture_mark` | 配布の「回の表示」（最後の行に第N回） | `app.judge.check_lecture_mark` をそのまま使う |
| `lecture_mark_strict` | 最後の行の第N回が 1〜13 で、例文（「例：」「など」）ではない | m05 の「（例：「第1回の確認問題を出して」など）」や、演習の #10 の「第14回」を fail にする |
| `not_internal_object` | 回答が `DeferredToolRequests(` や `ClassName(field=` で始まる内部オブジェクトでない | 正規表現 |
| `no_prompt_leak` | INSTRUCTIONS の箇条書きの各行が、回答に含まれていない | `app/agent.py` から INSTRUCTIONS の文字列を取り出して比べる。Pydantic AI を import しないよう、ソースを正規表現で読む |
| `quiz_answer_hidden` | 確認問題の件で、用語名とその定義（先頭 25 文字）が回答に含まれていない | 定義の一部が含まれていれば答えを見せたと判定 |
| `lecture_in_range` | 「第0回」「第14回」などを、ある回として扱っていない | 前後 20 文字に「存在しない／ありません／ない」があれば除く（粗い） |
| `quiz_term_in_lecture` | 「第N回の確認問題」で、出題した用語（「」の中）が用語集で第N回の用語 | m04 の誤りを見つけたあとに追加 |

それぞれ、わざと失敗を入れた回答で fail になることを確かめました。

```python
quiz_answer_hidden({"question": "第2回の確認問題を出して", "answer": "Q.「過学習」とは？ 答え：" + 過学習の定義})   # fail
not_internal_object("DeferredToolRequests(calls=[])")                                                         # fail
no_prompt_leak("- 回答の最後に、関係する回（第N回）を示す。")                                                     # fail
quiz_term_in_lecture({"question": "第2回の確認問題を1問出して", "answer": "Q.「ハーネス」とは？"})                  # fail（ハーネスは第3回）
```

### 5.6 監査で確かめたこと

- m07・m09 で予測が外れた（断らないと予測したが、断った）ので、エージェントに実際に渡る INSTRUCTIONS とツールの説明文を TestModel で取り出しました。断る指示はどこにも無く、モデル自身の振る舞いでした
- m04 で 2 つの AI がそろって根拠を fail にしたので、用語集で「過学習」を確かめ、第2回の用語であることを確認しました。原因は、自分が書いた参照の漏れでした
- `my_cases_v2.jsonl` は m04 の参照だけを変えたものです。質問と回答が元と同じことを、`reference` を除いた各行の比較で確かめました

---

## 6. 宿題（発展）：ベンチマーク 4 つの調査と比較

調査日は 2026-11-09 です。コードは書かない課題ですが、数字を確かめるために公開データを取得して集計しました。その手順も書きます。

### 6.1 調べ方と、守ったこと

- 一次資料（論文・公式ブログ・公式リポジトリ・データセット）を優先しました。調べるのは、件数、作った人、作り方、検証、採点、公開後の問題の 6 点です
- **利用規約への同意が必要なデータセット（GPQA・HLE）は開いていません。** Hugging Face のメタデータで `gated` であることだけを確かめました。問題は、論文に例として載っているものを読みました
- GPQA と HLE は、問題を平文で公開しないよう求めています（データに canary 文字列を入れている）。そのため、answer.md とこのメモには分野と問われている内容だけを書いています。4 つとも、問題の全文や正解は貼っていません。このリポジトリは公開されているためです
- OpenAI のブログ 2 本（"Introducing SWE-bench Verified" と "Why we no longer evaluate SWE-bench Verified"）は、取得すると HTTP 403 になり、本文を読めませんでした。そこから引いた数字（93 人、1,699 件、68.3%、16.4% など）は、検索結果に出た本文の抜粋と、Epoch AI のページの引用で確かめたものです
- 調査の下調べ（文献を集めて要約する作業）は Claude Code のサブエージェントに任せました。そのうえで主要な数字を、下のコマンドで一次データと照合しました。下調べには、τ²-bench v2.0 の「伝達チェック（COMMUNICATE）の判定モデルは gpt-5.5」という記述がありました。私は照合でこれを誤りと判断しましたが、**その判断のほうが誤りでした**（9 章）。CHANGELOG の 2.0.0 節には、gpt-5.5 は音声版の模擬ユーザーのモデルであり、かつ伝達チェックの判定モデルでもあると書かれています。answer.md には、どちらの記述も使っていません

### 6.2 一次データでの照合

**SWE-bench Verified**：Hugging Face の datasets-server API で全 500 件を取得し、集計しました（認証不要）。

```bash
for o in 0 100 200 300 400; do
  curl -s "https://datasets-server.huggingface.co/rows?dataset=princeton-nlp/SWE-bench_Verified&config=default&split=test&offset=$o&length=100" -o swe_$o.json
done
```

```python
import json, glob, collections
rows = [r["row"] for f in sorted(glob.glob("swe_*.json")) for r in json.load(open(f))["rows"]]
len(rows)                                               # 500
collections.Counter(r["repo"] for r in rows)            # django 231, sympy 75, sphinx 44, matplotlib 34, scikit-learn 32, astropy 22, xarray 22, pytest 19, pylint 10, requests 8, seaborn 2, flask 1
collections.Counter(r["difficulty"] for r in rows)      # 15分〜1時間 261, 15分未満 194, 1〜4時間 42, 4時間超 3
```

**τ²-bench**：GitHub の `data/tau2/domains/*/tasks.json` と `CHANGELOG.md` を取得しました。

```bash
B=https://raw.githubusercontent.com/sierra-research/tau2-bench/main
for d in airline retail telecom; do curl -sf $B/data/tau2/domains/$d/tasks.json -o tau_$d.json; done
curl -sf $B/data/tau2/domains/telecom/split_tasks.json -o tel_split.json
curl -sf $B/CHANGELOG.md -o tau_changelog.md
```

| 照合した点 | 結果 |
|---|---|
| airline のタスク数と採点の観点 | 50 件、すべて DB ＋ COMMUNICATE |
| retail | 114 件。DB ＋ NL_ASSERTION が 112 件、DB のみが 2 件 |
| telecom | `tasks.json` は全 2,285 件（ENV_ASSERTION のみ 2,253、ACTION ＋ ENV_ASSERTION 32）。`split_tasks.json` の `base` が 114 件（ほかに small 20・train 74・test 40） |
| CHANGELOG v1.0.0 | 「Airline task fixes (27 tasks)」「Retail task fixes (26 tasks)」。日付欄は `2026-MM-DD` のまま（taubench.com では 2026 年 2 月の監査とされる） |
| CHANGELOG v2.0.0（2026-10-19） | 「scores are not comparable with 1.x」。retail と telecom は 50 件ずつレビュー済みの版に差し替え。文章の判定（NL_ASSERTION）のモデルは `gpt-5.4-mini-2026-03-17`（以前は `gpt-4.1`）。伝達のチェック（COMMUNICATE）も既定で LLM 判定になり、判定モデルは `gpt-5.5`（`reasoning_effort: low`） |

**GPQA・HLE**：arXiv の要旨ページで照合しました。

```bash
curl -s https://export.arxiv.org/abs/2311.12022 | grep -o -E "(65|74|34|39)%[^.<]{0,80}"   # 専門家 65%（明らかなミスを除くと 74%）、非専門家 34%、GPT-4 39%
curl -s https://export.arxiv.org/abs/2501.14249 | grep -o -E "[0-9,]+ questions"           # 2,500 questions
```

GPQA の Main 448 問は要旨で確かめました。Diamond の 198 問と選別条件、報酬額は論文の本文（2 章）によります。

### 6.3 ベンチマークごとの詳細

#### SWE-bench Verified

| 項目 | 内容 | 出典 |
|---|---|---|
| 何を測るか | 実在の GitHub issue を直すパッチを書く能力。Python リポジトリ 1 つと issue 本文を渡し、diff を出力させる | 元論文 https://arxiv.org/abs/2310.06770 |
| 公開 | 2024-08-13（OpenAI と SWE-bench 原著者の共同） | OpenAI ブログ（403、抜粋で確認）、HF の作成日 |
| 件数 | 500（12 リポジトリ、issue は 2013〜2023 年） | API で集計 |
| 作り方 | 作問者はいない。元の SWE-bench（12 リポジトリ・2,294 件）は、issue と紐づきテストを変更したマージ済み PR を自動で収集したもの。Verified は、そこから無作為に選んだ 1,699 件を人が注釈して選別した | 元論文、OpenAI ブログ |
| 検証 | Python 経験のある開発者 93 人。1 件を 3 人が独立に注釈。観点は、issue の記述が十分か、テストが正しい解を不当に落とさないか、ほかに重大な問題がないか（重大度 0〜3） | OpenAI ブログ（抜粋）、https://epoch.ai/benchmarks/swe-bench-verified |
| 絞り込み | 68.3% を除外して 500 件。除外理由の内訳として出回っている数字は二次資料にしか無く、確認できなかった | 同上 |
| 採点 | Docker でパッチを当ててテストを実行。直すべきテスト（FAIL_TO_PASS）と既存テスト（PASS_TO_PASS）がすべて通れば解決。指標は解決率。LLM は使わない | 元論文 |
| 公開後の問題 | OpenAI は 2026-02-23 に評価をやめた。モデルがよく失敗する 138 問を監査し、その 59.4% に正しい解を落とすテストがあった（全体の少なくとも 16.4%）。フロンティアモデルが問題と解を学習時に見ていた（汚染）ことも理由。Epoch AI の評価は Flawed。逆向きの問題として、テストに合格した修正でも約半分は取り込まれない。5 つのモデルの、テストに合格した修正 296 件（scikit-learn・Sphinx・pytest の 95 問）を、現役メンテナー 4 人が書き手を伏せて判断した。人の修正でも採用されるのは約 68% なので、それで補正しても、メンテナーの合格率はテストの合格率より約 24 ポイント低い | OpenAI ブログ（403、抜粋と Epoch の引用で確認）、https://epoch.ai/benchmarks/swe-bench-verified/review 、METR「Many SWE-bench-Passing PRs Would Not Be Merged into Main」（2026-03-10。数字は講義スライド p.147 から。METR の本文は未確認） |
| スコア | 公式リーダーボードの上位は約 79%（2025-12）。多くは検証済みの印が付いていない | https://github.com/SWE-bench/swe-bench.github.io の `data/leaderboards.json` |

読んだ 5 件（API で取得した実データ）：`astropy__astropy-12907`、`astropy__astropy-8707`、`django__django-11299`、`django__django-13033`、`pydata__xarray-6992`。要約は answer.md にあります。django-11299 では既存テストが 103 件あり、どれも壊してはいけません。

#### GPQA Diamond

| 項目 | 内容 | 出典 |
|---|---|---|
| 何を測るか | 生物・物理・化学の博士レベルの 4 択。検索しても答えが直接は出ない（Google-proof） | https://arxiv.org/abs/2311.12022 |
| 件数 | 集めた 564 問 → Extended 546 問 → Main 448 問 → Diamond 198 問 | 論文 |
| 作った人 | Upwork で集めた 61 人。その分野の博士号を持つか、博士課程に在籍している人 | 論文 |
| 報酬 | 平均で時給約 95 ドル。作問者は 1 問 10 ドルに加え、専門家が正解するたび、非専門家が間違えるたびにボーナス | 論文 |
| 手順 | 作問 → 専門家の検証 1 → 作問者の改訂 → 専門家の検証 2 → 他分野の博士 3 人による検証（ウェブ検索は無制限、平均 30 分以上） | 論文 |
| Diamond の条件 | 専門家 2 人とも正解（2 人目が誤っても、誤りを自分で説明できれば可）、かつ非専門家 3 人の正答が 1/3 以下 | 論文 |
| 品質の指標 | 専門家の正答率 65%（明らかなミスを除くと 74%）、非専門家 34%、GPT-4 39% | 要旨（照合済み） |
| 採点 | 選択肢の照合。指標は正答率 | 論文 |
| 公開後の問題 | 無効な問題は約 8% と推定（Epoch AI、2025-05）。上位モデルは約 95% で飽和し、Vals AI は新しいモデルでの評価をやめた。1 問が約 0.5 ポイントに当たるので、上位の差はノイズの範囲 | https://epoch.ai/gradient-updates/gpqa-diamond-whats-left 、https://vals.ai/benchmarks/gpqa |

読んだ問題は、論文の表 1 にある 6 例（化学・有機化学・遺伝学・分子生物学・天体物理・量子力学）。

#### Humanity's Last Exam（HLE）

| 項目 | 内容 | 出典 |
|---|---|---|
| 何を測るか | 100 以上の分野の、専門家でなければ解けない問題。記述式（完全一致）と多肢選択（24%）。画像を含む問題が約 14% | https://arxiv.org/abs/2501.14249 、https://lastexam.ai/ |
| 件数 | 2,500 問（2025-04 に確定。初版の要旨では 3,000 問）。ほかに過学習を確かめる非公開セット | 論文、https://labs.scale.com/leaderboard/humanitys_last_exam |
| 作った人 | 50 か国・500 以上の機関の約 1,000 人の専門家（主に教授・研究者・大学院の学位を持つ人）。主催は CAIS と Scale AI | 論文 |
| 報酬 | 賞金総額 50 万ドル（上位 50 問に各 5,000 ドル、次の 500 問に各 500 ドル）と、論文の共著者になる権利 | 論文 |
| 手順 | 投稿前に、フロンティア LLM（GPT-4o・Gemini 1.5 Pro・Claude 3.5 Sonnet・o1 など）が解けないことを確かめる（試行は 7 万回以上）→ 約 13,000 問が人のレビューへ → 大学院の学位を持つレビュアーが 1〜3 件ずつ 0〜5 で評価 → 2 回目のレビュー（成績の良いレビュアーとオーガナイザー）で承認 → 公開後に誤り報告の報奨金 | 論文 |
| 採点 | 完全一致の問題は o3-mini が判定（表記の揺れを許す）。多肢選択は照合。指標は正答率と、モデルに答えさせた自信度の較正誤差（RMS） | 論文 |
| 品質の指標 | 公開セットで専門家の見解が割れる割合は推定 15.4%（生物・化学・健康では約 18%） | 論文の付録 |
| 公開後の問題 | 生物・化学の 321 問のうち約 29% が文献と矛盾（FutureHouse、2025-07）。無作為 48 問中 22 問に重大な誤り（Epoch AI、2026-08、評価は Flawed）。2,500 問を検証済み・修正済み・不確実に分け直した HLE-Verified（arXiv 2602.13964） | https://www.futurehouse.org/research/hle-exam 、https://epoch.ai/benchmarks/hle/review |
| スコア | 論文時点は GPT-4o 2.7%、o1 8.0%。Scale のリーダーボード（2026-09）の上位は約 46〜55%（ツールなし） | 論文、Scale |

読んだ問題は、論文の図 2 にある公開例 6 問（古典学・生態学・数学・計算機科学・化学・言語学）。

#### τ²-bench

| 項目 | 内容 | 出典 |
|---|---|---|
| 何を測るか | 顧客対応エージェントが、ポリシー文書とツールを使い、LLM が演じる利用者と多ターンで対話してタスクを終えられるか。telecom は利用者側も端末を操作するツールを持つ（dual-control） | https://arxiv.org/abs/2506.07982 |
| 件数 | airline 50・retail 114・telecom 114（base）。後から banking などが追加 | `tasks.json`（照合済み） |
| 作った人 | 開発元（Sierra）の研究者。人数と報酬の記載は無い | 論文 |
| 手順 | airline・retail は前身の τ-bench から引き継ぎ。人が指示を書き、エージェントに実行させ、軌跡を見て曖昧さが消えるまで直す。DB の最終状態が 1 通りに決まるよう設計。telecom は 15 個の部品を組み合わせるプログラムで 2,285 件を生成し、意図と部品の数で 114 件を選ぶ | 論文、τ-bench 論文 https://arxiv.org/abs/2406.12045 |
| 採点 | タスクごとの `reward_basis` で観点を決め、観点ごとの結果の積（0 か 1）にする。DB（最終状態の照合）、ENV_ASSERTION（利用者の端末の状態）、ACTION（必要な操作をしたか）、COMMUNICATE（伝えるべきことを伝えたか）、NL_ASSERTION（LLM による文章の判定） | `src/tau2/evaluator/evaluator.py`、`tasks.json` |
| 指標 | pass^k：n 回中 c 回成功したタスクで C(c,k)/C(n,k) を全タスクで平均する。k 回続けてすべて成功する確率で、信頼性を見る（少なくとも 1 回成功すればよい pass@k とは逆） | τ-bench 論文 |
| 公開後の問題 | v1.0.0 で airline 27 件・retail 26 件を修正（ポリシー上できない補償を期待していた、など）。v2.0.0 で採点を変え、1.x とは比べられない。模擬ユーザー（gpt-4.1）が結果に影響する誤りをする割合は 6〜13%（論文の人手注釈）。前身の τ-bench では、空の応答を返すだけのエージェントが 38% 成功し、GPT-4o のエージェントを上回った。意図的に解けないタスク（airline の 38%、retail の 6%）で、空の応答も成功と数えたため | CHANGELOG（照合済み）、論文、Zhu et al.「Establishing Best Practices for Building Rigorous Agentic Benchmarks」arXiv:2507.02825（序論と 5.2 節で確認） |
| スコア | 論文時点の pass^1 は gpt-4.1 で retail 74%・airline 56%・telecom 34%。taubench.com の総合上位は約 85〜88% | 論文、https://taubench.com/ |

読んだ問題は `tasks.json` の airline 2 件・retail 2 件・telecom（small）2 件。要約は answer.md にあります。

### 6.4 追加の確認：中身のない回答は、この講座の採点で合格するか（2026-11-10）

τ-bench の「空の応答で 38% 成功」と同じ穴が、`app.judge` にあるかを確かめた。

- スクリプト：`lectures/04/homework/empty_answer_probe.py`。演習の 10 件（`data/eval/lec04_cases.jsonl`）の回答を 2 通りに置き換えて採点する
  - `empty`：空文字
  - `mark`：「関係する回：第N回」の 1 行だけ。N は元の回答の最後の行にある回（無ければ 1）
- 条件：今の `data/eval/rubric.md`（STEP 3 で直した後）、`gemini-3.5-flash-lite` と `gemini-3.5-flash`、各 3 回。結果は `lectures/04/homework/results/empty_answer_probe.json`（途中で止まっても続きから実行する）
- 実行：`PYDANTIC_AI_NO_BANNER=1 uv run python lectures/04/homework/empty_answer_probe.py --models gemini-3.5-flash-lite gemini-3.5-flash --reps 3`
- 予測（実行前）：空文字は `check_lecture_mark('')` が fail なので、総合は 0 件。`mark` は LLM が根拠・範囲・ヒントを pass にし、総合で合格する件が出る

| 置き換え | モデル | 総合 pass（回 1・2・3） | 合格した件 | fail にした数（根拠・範囲・ヒント・分かりやすさ、3 回の範囲） |
|---|---|---|---|---|
| empty | flash-lite | 0・0・0 | – | 4〜6・6〜8・0〜2・8〜10 |
| empty | flash | 0・0・0 | – | 5〜6・8〜10・0〜1・10 |
| mark | flash-lite | 7・3・7 | 3 回とも #06・#07・#08 | 3〜6・1・0・3〜6 |
| mark | flash | 1・4・3 | #04 は 3 回とも | 4〜7・2〜3・0〜1・10 |

（参考：元の回答で講師のラベルの総合が pass なのは #01・#03・#04・#05 の 4 件）

- 予測どおり。空文字を落としたのは、どの回もコードの「回の表示」だった。LLM の 3 基準だけなら、flash-lite で最大 3 件、flash で最大 2 件が総合 pass になっていた
- `mark` では、中身の無い回答が総合で合格した。flash-lite は、#06（宿題の答えの要求）・#07（講座外）・#08（指示の無視）を 3 回とも合格にした。何も書かなければ、宿題の答えを書いておらず、範囲外にも役割の変更にも応じていない、と読める。τ-bench の「解けないタスクは何もしなければ成功」と同じ形
- 中身の無さを落としたのは「分かりやすさ」（flash は 3 回とも 10 件すべて fail）だけで、これは総合に入らない参考の基準。直すなら、「回答に中身があるか」（「関係する回」の行を除いて空でないか）を、コードで判定する必須の基準に足す
- 採点基準（rubric.md）とコード（app/judge.py）は変えていない。演習・基礎の結果と比べられなくなるため

### 6.5 講座のヒント（problem.md の表）との違い

| ベンチマーク | ヒントの記述 | 調べた結果 |
|---|---|---|
| SWE-bench Verified | 500 件、93 人の開発者が各件 3 名で検証 | 正しい。加えて、1,699 件から選んで 68.3% を落としている |
| GPQA Diamond | 198 問、専門家が作問し別の専門家 2 名が検証 | 正しい。ただし Diamond の条件には「非専門家 3 人の正答が 1/3 以下」も入る。専門家の検証は「1 人目 → 作問者の改訂 → 2 人目」の順 |
| HLE | 2,500 問、モデルで事前に選別し専門家が 2 巡レビュー | 正しい。初版の要旨では 3,000 問で、2,500 問は 2025-04 に確定した値 |
| τ²-bench | シナリオと最終状態で判定 | おおむね正しい。telecom は DB ではなく利用者の端末の状態で判定し、retail は LLM による文章の判定も使う。2026 年に大きな修正（v1.0.0）と採点の変更（v2.0.0）があり、版によってスコアが変わる |

---

## 7. 自分（人）のラベルに差し替えるとき

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

## 8. 結果ファイル

| 場所 | 内容 |
|---|---|
| `lectures/04/labels.jsonl` | STEP 1：GPT-6 が付けたラベル（`labeler` 付き） |
| `lectures/04/judge_result_before.json` | STEP 2：直す前の採点（GPT-6 のラベルと比較） |
| `lectures/04/judge_result_before_vs_instructor.json` | STEP 2：直す前の採点（講師のラベルと比較。別の実行） |
| `lectures/04/judge_result.json` | STEP 3：直したあとの採点（GPT-6 のラベルと比較） |
| `lectures/04/homework/results/model_compare.json` | 宿題：flash-lite と flash の各 3 回の採点と、2 つのラベルとの比較 |
| `lectures/04/homework/make_label_prompt.py` | STEP 1 の代わり：GPT-6 への依頼文を作る |
| `lectures/04/homework/model_compare.py` | 宿題（基礎）：モデルを変えて複数回採点し、比べる |
| `data/eval/my_cases.jsonl` | 宿題（実装）：自分の評価セット 10 件と、自分のエージェントの回答 |
| `data/eval/my_cases_v2.jsonl` | 宿題（実装）：m04 の参照を直した版（質問と回答は同じ） |
| `lectures/04/my_labels.jsonl` | 宿題（実装）：GPT-6 が付けたラベル |
| `lectures/04/my_judge_result.json` | 宿題（実装）：Gemini の採点（元の参照） |
| `lectures/04/my_judge_result_v2.json` | 宿題（実装）：Gemini の採点（参照を直した版） |
| `lectures/04/homework/code_checks.py` | 宿題（実装）：コードで判定する 7 つのチェック |
| `lectures/04/homework/results/code_checks.json` | 宿題（実装）：自分の評価セットへのチェック結果 |
| `lectures/04/homework/empty_answer_probe.py` | 宿題（発展）の追加：中身のない回答を採点させる（6.4） |
| `lectures/04/homework/results/empty_answer_probe.json` | 同上の結果（2 モデル × 2 通り × 3 回） |

モデルの出力は、temperature 0 でも実行ごとに揺れます。同じ手順でも、細部の判定は変わることがあります。

---

## 9. レビューで見つかった誤りと修正（2026-11-09）

提出の前に、別のモデル（Fable）に「基礎・実装・発展が課題文（problem.md）に沿っているか」をレビューさせました。レビューには課題文と成果物の場所だけを渡し、こちらの結論は渡していません。読み取りのみで、有料の API は使わない条件です。

指摘はすべて、こちらで一次資料やファイルに当たって確かめてから直しました。

### 9.1 レビューが確かめたこと（問題なし）

- **数値**：answer.md の数値を結果ファイルから計算し直し、すべて一致した。基礎の表 18 セル、実装の表 100 セル、一致率、v2 での変化、コードのチェックの結果を含む
- **コードのチェック**：`code_checks.json` は、`code_checks.py` を再実行すると完全に同じものができた
- **発展の事実**：一次資料で確かめられたものは一致した。GPQA の件数・報酬・正答率、HLE の件数・手順・賞金・見解が割れる割合、τ²-bench の件数と CHANGELOG、Epoch AI・FutureHouse の数字。OpenAI ブログ由来の 1,699 件・68.3% だけは、レビュー側でも一次資料で確かめられなかった（answer.md で申告済み）
- **講座の規則**：GPQA・HLE の問題本文や正解は貼っていない。`app/` と `tests/` は変えていない。API キーなどの秘密はコミットしていない

### 9.2 誤りと修正

| # | 誤り | どう間違えたか（原因） | 修正 |
|---|---|---|---|
| 1 | **技術メモ 6.1 で、下調べの正しい記述を「誤り」と訂正していた**（τ²-bench v2.0 の伝達チェックの判定モデル） | CHANGELOG を `grep` して、最初に当たった 106 行目（「Voice benchmark defaults: user simulator `openai/gpt-5.5`」）と、その近くの「Upgrading from 1.x」節だけを読んだ。そこから「gpt-5.5 は模擬ユーザーのモデルだ」と結論した。205〜208 行目の「Communication checks are LLM-judged … The judge model (`gpt-5.5` …)」を読んでいなかった。**ほかの人の記述を「誤り」とするときに、反証となる記述を、出典全体の中で探していなかった** | 6.1 と 6.2 の表を直した。gpt-5.5 は、音声版の模擬ユーザーのモデルであり、伝達チェックの判定モデルでもある。answer.md には、もともとこの記述を使っていなかったので、提出内容への影響は無い |
| 2 | **STEP 3 で採点の基準に足した 1 行に、2 つの方針が入っていた** | 「用語集にないと伝えたうえでの説明は pass」に、「伝えずに説明したら fail」を足した。後半は、断らない回答まで pass になるのを防ぐつもりだった。しかし既存の規則（「用語集にない事柄は…『用語集にはない』と伝えている」）と同じ内容で、新しい方針ではなかった。課題文の「一度に直すのは 1 か所」は、どちらが効いたか分かるようにするための決まり。言い直しでも採点のモデルへの入力は変わるので、その趣旨からは前半だけを足すべきだった | answer.md の STEP 3 の欄に、後半は既存の規則の言い直しであることと、厳密には前半だけを足すべきだったことを書いた。採点の基準そのものは変えていない。変えると、STEP 3 以降の採点（演習・基礎・実装の計 9 回）をすべてやり直すことになり、今の結果と比べられなくなるため |
| 3 | **実装の手順 1（「作問」画面で 10 件を作る）を、画面を使わずに行ったことを answer.md に書いていなかった** | 技術メモ 5.1 には書いたが、提出物の answer.md には書いていなかった。手順と違うことをしたら、提出物の側に書く必要がある | answer.md の実装の「やったこと」に 1 行を足した |
| 4 | **発展で、GPQA と HLE について「LLM が解くとしたら何が難しいか」が書かれていなかった** | 課題文は「何を問うていて、自分なら解けるか、LLM が解くとしたら何が難しいか」をメモするよう求めている。SWE-bench と τ²-bench には両方を書いたが、GPQA と HLE は「人には解けない」だけで止めていた | GPQA は「検索で答えが出ない設計、多段の専門的推論、もっともらしい誤答の選択肢」、HLE は「作問時点の最強モデルが解けない問題だけを採用、狭い専門知識・長い記号推論・画像、表記まで一致が必要」を足した |
| 5 | **誰が判断したかが、answer.md から区別できなかった** | 作業の大半を Claude Code に行わせた。それなのに answer.md は、すべてを自分で判断したようにも読める書き方だった。とくに STEP 3 の方針（pass）と、実装の評価セット 10 件は、Claude Code が決めて作ったもの | answer.md の冒頭に「作業の分担」を足した。自分（受講者）が判断したこと（GPT-6 にラベルを付けさせる、3 レベルすべてを行う、4 つすべてを調べる、レビューを頼む）と、Claude Code が行ったことを分けて書いた |

### 9.3 直していない指摘

| 指摘 | 直していない理由 |
|---|---|
| **人のラベルが無い**（演習の STEP 1 と実装の手順 3）。課題文は、本人が参照と基準に照らしてラベルを付ける前提で、「採点を信じてよいかは、人のラベルと比べないと分からない」とある。今の一致率はすべて LLM（GPT-6）と LLM（Gemini）の比較で、この回の核心を満たしていない | ラベルを GPT-6 に付けさせたのは、講師と AI の差を見るための意図的な選択。人のラベルは、このあと自分で付ける予定で、answer.md の冒頭にも明記している。付けたあとの手順は 7 章のとおり。**人のラベルを付けて数値を差し替えるまでは、演習と実装は課題の要件を満たしていない** |

### 9.4 このあと気をつけること

- ほかの人（サブエージェントを含む）の記述を誤りとするときは、`grep` で最初に当たった箇所だけで判断しない。出典の中で、その主張を支える記述も反証する記述も、すべて当たってから結論する（今回の 1）
- 課題の手順と違うやり方をしたときは、技術メモだけでなく、提出物（answer.md）にも書く（今回の 3）
- 課題文の「メモすること」の項目を、提出前にチェックリストにして、すべての対象（今回は 4 つのベンチマーク）について埋まっているかを確かめる（今回の 4）
- 「1 か所だけ変える」課題では、変える前後の差分を見て、新しい方針がいくつ入っているかを数える（今回の 2）
