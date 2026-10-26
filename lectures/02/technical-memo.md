# 第2回 技術メモ：宿題（基礎・実装・発展）を再現するためのコード変更

このメモは、第2回の宿題 3 レベルを他の人が再現できるように、`notebooks/lora_format_tuning.ipynb` に加える変更と、そのまま貼り付けて使えるテンプレートを説明します。結果と考察は [answer.md](answer.md) にあります。

## 0. 共通：実行環境と、ノートブックをローカルで動かすための変更

Colab の T4 で動かす場合、この節の変更は必要ありません。本メモの結果は、ローカルの RTX 3090 Ti（24GB）で次の環境を作って得ました。

```bash
# リポジトリの外に専用の venv を作る（リポジトリの uv.lock には触れない）
uv venv envs/lec02 --python 3.13
VIRTUAL_ENV=envs/lec02 uv pip install "torch==2.11.0" --index-url https://download.pytorch.org/whl/cu130
VIRTUAL_ENV=envs/lec02 uv pip install "transformers==5.18.0" "peft==0.21.1" "trl==1.14.2" \
    "accelerate==1.15.0" "datasets==5.1.0" pandas ipykernel nbconvert
```

版はノートブックのセクション 0 の `PINS` と、Colab 同梱の torch（2.11.0+cu130）に揃えています。ノートブックには次の 2 か所だけ手を入れます。

| 場所 | 変更 | 理由 |
|---|---|---|
| セクション 0 の `%pip uninstall` / `%pip install` の行 | コメントアウトする | 上の venv に入れ済み。Colab 用の torchao の削除も不要 |
| セクション 1 の `CONFIG["work_dir"]` | `"/content/qlora_lab"` をローカルのパスに変える | `/content` は Colab のパス |

ノートブックはコマンドラインからも実行できます。条件を変えて何度も回すときに便利です。

```bash
envs/lec02/bin/jupyter nbconvert --to notebook --execute <ノートブック>.ipynb \
    --output <ノートブック>.executed.ipynb --ExecutePreprocessor.timeout=3600
```

`causal_conv1d` / `flash-linear-attention` が無いため遅い参照実装で動く、という警告が出ます。結果は変わらないので、Colab と条件を揃えるために入れていません。

### 学習ログを読むときの注意（3 レベル共通）

- **表示される `Training Loss` は、`logging_steps=10` ごとの直前 10 ステップの平均です。** 学習が 10 ステップしかない設定（例：5 エポック）では、表示される唯一の値が学習全体の平均になり、「学習後の loss」にはなりません
- **TRL 1.14 の `SFTTrainer` は、`messages` 形式のデータでは既定で系列全体（system・FAQ・質問・応答）に loss をかけます**（`SFTConfig.assistant_only_loss=False`）。応答部分だけの loss とは値が違います

設定どうしを同じ基準で比べるため、本メモでは保存した adapter を読み込み、学習データの応答部分の loss を評価モードで測り直しました。ノートブックの最後に足せるセルを示します（セクション 3 の `SYSTEM`・`tok`、セクション 2 の `train` をそのまま使います）。

```python
# 学習データの「応答部分」だけの平均 loss を、評価モードで測る
def response_loss(model, rows):
    total, count = 0.0, 0
    for r in rows:
        msgs = build_messages(r) + [{"role": "assistant", "content": r["target"]}]
        full = tok.apply_chat_template(msgs, tokenize=False)
        start = full.rindex(r["target"])          # 応答の開始位置（文字単位）
        enc = tok(full, return_tensors="pt", return_offsets_mapping=True)
        offsets = enc.pop("offset_mapping")[0]
        labels = enc["input_ids"].clone()
        labels[0, offsets[:, 0] < start] = -100   # 応答より前のトークンは loss に含めない
        with torch.no_grad():
            out = model(**{k: v.to(model.device) for k, v in enc.items()}, labels=labels.to(model.device))
        n = int((labels[0, 1:] != -100).sum())    # モデル内部で 1 つずらして比べるので、先頭を除いて数える
        total += out.loss.item() * n; count += n
    return total / count

with tuned.disable_adapter():
    print("学習前:", round(response_loss(tuned, train), 4))
print("学習後:", round(response_loss(tuned, train), 4))
```

`offset_mapping` は、各トークンが元の文字列のどの位置から始まるかを表します。応答の開始位置より前のトークンのラベルを `-100` にすると、その部分は loss の計算から外れます。

---

## 1. 基礎：エポック数を変えて再学習する

### 変更点

セクション 1 の `CONFIG` の 1 行だけを変えます。

```python
CONFIG = {
    ...
    "num_train_epochs": 5,   # 元は 20。本メモでは 5 と 10 を試した
    ...
}
```

- 学習データは 14 件、`per_device_train_batch_size=4`、`gradient_accumulation_steps=2` なので、1 エポックは 2 ステップです。5 エポックなら 10 ステップ、10 エポックなら 20 ステップになります
- **学習率のスケジュールも一緒に変わります。** `lr_scheduler_type="cosine"` は全ステップ数に合わせて学習率を下げます。`warmup_steps=6` は固定なので、5 エポックでは「6 ステップかけて学習率を上げ、残り 4 ステップで 0 まで下げる」形になります。エポック数だけを純粋に比べているわけではない点に注意します
- 設定ごとに `work_dir` を分けると、`result.json` を上書きせずに並べて比べられます

### 手順

1. `num_train_epochs` を変える（`work_dir` も変えておく）
2. **ランタイム → セッションを再起動**してから、セクション 0 から 7 まで上から実行する。学習後のモデル（adapter が差し込まれた `model`）が残っていると、学習前の評価が正しく取れません
3. `result.json` の `after`、セクション 4 の学習時間と Training Loss、上の「応答部分の loss」を記録する

### 比較用のテンプレート

複数の `result.json` を並べる表は、次のコードで作れます。

```python
import json, pandas as pd
runs = {"ep5": "out_basic_ep5", "ep10": "out_basic_ep10", "ep20": "out"}   # 名前: work_dir
rows = []
for name, d in runs.items():
    r = json.load(open(f"{d}/result.json"))
    rows.append({"run": name, "epochs": r["config"]["num_train_epochs"],
                 "format_rate": r["after"]["format_rate"], "content_rate": r["after"]["content_rate"],
                 "regressed": len(r["regressed"])})
display(pd.DataFrame(rows).set_index("run"))
```

### 確認したこと（監査）

- 元のノートブックとの差分が `num_train_epochs` と `work_dir` だけであること
- 学習前の評価（貪欲生成）の出力原文が、3 つの設定で完全に一致すること。違えば、学習前の時点で何かが混ざっています
- `trainer_state.json` の `max_steps` が 10 / 20 / 40 になっていること

---

## 2. 実装：題材を自分の FAQ に置き換える

### 変更点の全体

| セクション | 変える箇所 | 内容 |
|---|---|---|
| 2 | `FAQ` 〜 `UNGROUNDED_ANSWER`（`def make_example` より前すべて） | 題材のデータを丸ごと差し替える |
| 3 | `SYSTEM` の冒頭 | 「講座 FAQ の回答係」を題材に合わせる |
| 6 | `KNOWLEDGE_QUESTIONS` | 題材に合わせた「FAQ に無い質問」と対照の質問 |

`make_example` から後ろ（データの分割、評価関数、学習、比較）は変えません。JSON の形式と `needs_review` の設計も同じです。

### データの差し替えテンプレート

セクション 2 のセルで、`def make_example` より前を次のように置き換えます。本メモでは架空の「研究室 GPU サーバの利用ルール」を使いました。

```python
FAQ = {
    "reserve": "GPU の利用は研究室カレンダーで前日 18:00 までに予約します。",
    "limit": "1 人あたりの連続利用は最大 72 時間までです。",
    "storage": "/data 以下のファイルは 30 日間アクセスがないと自動で削除されます。",
    "contact": "障害が起きたら Slack の #gpu-admin チャンネルに連絡します。",
    "account": "アカウントは指導教員の承認を得てから管理者に申請して発行してもらいます。",
}
FAQ_TEXT = "\n".join(f"- {v}" for v in FAQ.values())

# 根拠あり: (FAQ キー, 質問テンプレート 4 つ, 正解の answer に含まれるべき語)
# テンプレートは先頭 2 つが train、3 つ目が valid、4 つ目が test に入る（split_templates）
GROUNDED = {
    "reserve": (["GPU の予約方法を教えてください", "いつまでに予約すればいいですか", "予約はどこでしますか", "予約の締切は？"], ["カレンダー", "前日"]),
    "limit": (["連続で何時間使えますか", "利用時間の上限はありますか", "1 回のジョブはどのくらい回せますか", "最長の利用時間は？"], ["72 時間"]),
    "storage": (["データはいつ消えますか", "/data に置いたファイルは保存され続けますか", "データの自動削除について教えてください", "ファイルが消える条件は？"], ["30 日"]),
    "contact": (["障害が起きたらどこに連絡しますか", "サーバが落ちたときの連絡先は？", "トラブルの報告先を教えてください", "不具合はどこに報告しますか"], ["#gpu-admin"]),
    "account": (["アカウントはどうやって作りますか", "利用登録の手順は？", "サーバを使い始めるには何をすればいいですか", "アカウント申請の流れは？"], ["指導教員", "承認"]),
}
# 根拠なし: 8 問。i % 4 で [train, train, valid, test] に振られるので、並べる順番で配分が決まる
# near = FAQ の項目と語や話題が重なる質問、far = 無関係な質問
UNGROUNDED = [
    "予約をキャンセルするにはどうすればいいですか",   # near → train
    "研究室の電話番号を教えてください",               # far  → train
    "連続利用の上限を延長してもらえますか",           # near → valid
    "削除されたデータは復元できますか",               # near → test
    "GPU サーバの電気代は誰が払っていますか",         # far  → train
    "アカウントの有効期限はいつまでですか",           # near → train
    "研究室のコーヒーメーカーは使えますか",           # far  → valid
    "学会の旅費はどう申請しますか",                   # far  → test
]
# test だけに入れる追加の質問（言い換え・紛らわしい質問）
TEST_EXTRA_GROUNDED = {
    "reserve": ["GPU サーバの予約はどこで、いつまでに行いますか", "明日 GPU を使いたい場合、いつまでに予約が必要ですか"],
    "limit": ["1 人が続けて GPU を使える時間の上限を教えてください", "4 日間続けて学習を回してもいいですか"],
    "storage": ["/data のファイルはどのくらい放置すると削除されますか", "しばらく使っていないデータはどうなりますか"],
    "contact": ["GPU サーバが止まったら誰に知らせればいいですか", "サーバの障害はどのチャンネルに書けばいいですか"],
    "account": ["GPU サーバのアカウントを発行してもらう手順を教えてください", "アカウントの申請に誰の承認が必要ですか"],
}
TEST_EXTRA_UNGROUNDED = [
    "/home ディレクトリの容量制限はありますか",       # near
    "#gpu-admin は何時まで対応していますか",          # near
    "GPU は何枚まで同時に使えますか",                 # near
    "研究室の鍵はどこで借りますか",                   # far
]
UNGROUNDED_ANSWER = "この FAQ には記載がありません。管理者に確認が必要です。"
```

### 題材を作るときの注意

- **`must_include` の語は、FAQ の文にそのまま含まれていること。** 内容の採点は「answer にこの語が全部含まれるか」なので、FAQ に無い表記（例：「72時間」と「72 時間」の空白の違い）を書くと、正しく答えても × になります。差し替えた後に次のセルで確かめます

  ```python
  for k, (_, must) in GROUNDED.items():
      assert all(w in FAQ[k] for w in must), (k, must)
  ```

- 根拠なしの正解の語は `["確認"]` なので、`UNGROUNDED_ANSWER` には「確認」を入れます
- `UNGROUNDED` は 8 問にします。`i % 4` で振り分けるので、train 4 / valid 2 / test 2 になります。どの質問がどこに入るかは並べる順番で決まります
- 質問が train / valid / test のどこかで重複すると、セクション 2 の `assert` で止まります
- **根拠なしの質問の作り方で、測れることが変わります。** FAQ と無関係な質問（far）だけだと簡単になりすぎます。FAQ と語や話題が重なる紛らわしい質問（near）を混ぜると、「答えがあるかどうか」の判断の弱さが見えます

### system プロンプトと知識質問

セクション 3 の `SYSTEM` の冒頭を変えます（それ以外の文は形式の指示なので、そのまま使います）。

```python
SYSTEM = "あなたは研究室 GPU サーバの FAQ の回答係です。与えられた FAQ だけを根拠に、..."   # 以降は元のまま
```

セクション 6 の `KNOWLEDGE_QUESTIONS` を差し替えます。

```python
KNOWLEDGE_QUESTIONS = [
    "GPU サーバの OS のバージョンは何ですか",       # FAQ に無い
    "管理者の名前は何ですか",                       # FAQ に無い
    "予約できる GPU の種類は何ですか",              # FAQ に無い（予約の項目と語が重なる）
    "GPU の予約方法を教えてください",               # FAQ にある（対照）
]
```

表の「FAQ にある」列は `q in gold`（test の質問かどうか）で判定しています。対照の質問を train のテンプレートから選ぶと、この列は `False` と表示されます。元のノートブックの「課題の提出期限はいつですか」も train のテンプレートなので同じです。

### 確認したこと（監査）

- `train.jsonl` / `test.jsonl` / `gold.json` を開き、根拠なしの near・far が想定どおり train 2・2、test 4・2 に入っていること
- train と test に同じ質問が無いこと
- 差し替えた `SYSTEM` と `KNOWLEDGE_QUESTIONS` が、実行済みノートブックに反映されていること

---

## 3. 発展：講座の用語集で学習し、用語集の検索と比べる

発展は FAQ の題材と JSON 形式を使わないので、ノートブックを書き換えるより、1 本のスクリプトにまとめた方が見通しがよくなります。[homework/advanced_glossary.py](homework/advanced_glossary.py) に、データ作成・学習前の評価・検索方式の評価・学習・学習後の評価をまとめました。

```bash
# リポジトリ直下で（PINS と同じ版が入った環境）
python lectures/02/homework/advanced_glossary.py --out <出力ディレクトリ>           # 全部（3090 Ti で約 10 分）
python lectures/02/homework/advanced_glossary.py --out <出力ディレクトリ> --rescore  # 保存済みの出力を採点し直すだけ
```

出力ディレクトリには、`glossary_sft.jsonl`（学習データ）、`eval_before.json` / `eval_rag.json` / `eval_after.json`（30 問の出力原文と採点）、`result.json`（設定・loss・要約）、`adapter/` ができます。Colab で使う場合は、`data/glossary.json`・`scripts/make_sft_dataset.py`・`app/tools.py` をリポジトリと同じ相対位置に置きます。

以下、要所のコードを説明します。

### 3.1 学習データ：配布スクリプトの出力に「載っていません」の例を足す

```python
ABSENT_ANSWER = "「{term}」は講座の用語集に載っていません。"
ABSENT_TRAIN = ["LangChain", "ベクトルデータベース", "DPO", "Docker", "強化学習",
                "トランスフォーマー", "lecNN-end タグ", "提出ボーナス", "Kubernetes", "埋め込み"]

def make_train_records() -> list[dict]:
    # 配布スクリプトをそのまま実行し、出力（messages 形式の JSONL）を読む
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "make_sft_dataset.py")],
                         capture_output=True, text=True, check=True).stdout
    records = [json.loads(line) for line in out.splitlines() if line.strip()]
    for term in ABSENT_TRAIN:
        for template in TEMPLATES:               # make_sft_dataset.py と同じテンプレート
            records.append({"messages": [{"role": "user", "content": template.format(term=term)},
                                         {"role": "assistant", "content": ABSENT_ANSWER.format(term=term)}]})
    return records
```

- `scripts/make_sft_dataset.py` は、58 語 × 2 テンプレート（「「〇〇」とは何ですか？」「〇〇について簡単に説明してください。」）で 116 件を作ります。これだけだと「知らない語」の例が無く、何を聞かれても定義らしい文を作るようになります。そこで、用語集に無い語への「載っていません」の例を 20 件足しました
- `ABSENT_TRAIN` の語は、`search_glossary` で検索して「見つかりませんでした」になることを確かめてから選びます。「RAG」は用語集の見出しにはありませんが、「ファインチューニング」の定義文に含まれるため検索に当たります。「載っていません」の例には使いませんでした
- 各行は `messages` 形式なので、`Dataset.from_list(records)` をそのまま `SFTTrainer` に渡せます

### 3.2 評価セット：3 種類の質問と正解の語

```python
# (種別, 質問, 検索方式で search_glossary に渡す語, 正解の answer に含まれるべき語)
EVAL = [
    ("seen", "「Pi」とは何ですか？", "Pi", ["MIT"]),
    ("paraphrase", "Low-Rank Adaptation ってどういう仕組みですか？", "Low-Rank Adaptation", ["低ランク"]),
    ("paraphrase", "AIE2026 で標準に使うモデルは何ですか？", "既定モデル", ["gemini-3.5-flash-lite"]),
    ("absent", "「蒸留」とは何ですか？", "蒸留", None),
    ...
]
```

- `seen` は学習データと同じ質問文、`paraphrase` は学習データに無い言い回しや別名、`absent` は用語集に無い語（学習用の `ABSENT_TRAIN` とは別の語）です
- 正解の語は、**検索で 1 件目に返る定義の中に、その語がそのまま含まれる**ように選びます。次のチェックを通してから評価します

  ```python
  for kind, q, query, must in EVAL:
      if must:
          d = json.loads(search_glossary(query))[0]["definition"]
          assert all(w in d for w in must), (q, must)
  ```

- スクリプトは、`seen` 以外の評価質問が学習データに入っていないことを `assert` で確かめます

### 3.3 検索方式（RAG）：第 3 回のツールの結果をプロンプトに入れる

```python
from app.tools import search_glossary

RAG_SYSTEM = ("あなたは講座の用語集に基づいて答えるアシスタントです。与えられた検索結果だけを根拠に、簡潔に答えてください。"
              "検索結果に質問の語が無いときは「用語集に載っていません」とだけ答えてください。")
rag = lambda q, query: [{"role": "system", "content": RAG_SYSTEM},
                        {"role": "user", "content": f"検索結果:\n{search_glossary(query)}\n\n質問: {q}"}]
```

- 学習していない同じモデル（Qwen3.5-0.8B）を使い、違いは「検索結果を渡すかどうか」だけにします
- 検索語（`query`）は、エージェントが質問から取り出すはずの語を評価セットに書いておきます。実際のエージェントでは、モデルが検索語を選ぶ段階でも失敗しうるので、この方式の成績はやや楽観的です
- `search_glossary` は完全一致・部分一致・定義文の中の一致の順に最大 3 件を返し、無ければ「用語集に「〇〇」は見つかりませんでした。」を返します

### 3.4 採点：空白の揺れと「見つかりませんでした」に注意する

```python
ABSENT_PATTERNS = ("用語集に載っていません", "見つかりませんでした")

def _norm(text):
    return text.replace(" ", "").replace("　", "")

def score(kind, must_include, raw):
    said_absent = any(p in raw for p in ABSENT_PATTERNS)
    if kind == "absent":
        return said_absent
    return not said_absent and all(_norm(w) in _norm(raw) for w in must_include)
```

最初は「`"用語集に載っていません" in raw`」と「`w in raw`」だけで採点していました。結果が予測と合わなかったので出力を見直すと、次の 2 つの採点ミスがありました。

| 症状 | 原因 | 直し方 |
|---|---|---|
| 検索方式の `absent` が 1/8 と低すぎる | モデルが検索ツールの「用語集に「蒸留」は見つかりませんでした。」をそのまま答えていた。振る舞いは正しいのに、判定の文言と違うので × になった | 「見つかりませんでした」も正解にする |
| 「どれか 1 つ」が、正解の語「1つ」に一致しない | 半角空白の有無の違い | 比べる前に空白を取り除く |

直したあとの数字は `--rescore` で出しました（生成はやり直していないので、出力原文は同じです）。直す前後の要約は次のとおりです。

| 方式 | 直す前（seen / paraphrase / absent） | 直した後 |
|---|---|---|
| 学習前 | 0/10・0/12・0/8 | 0/10・0/12・0/8 |
| 検索 | 6/10・10/12・1/8 | 6/10・11/12・5/8 |
| 学習後 | 10/10・2/12・3/8 | 10/10・2/12・3/8 |

**語が含まれるかどうかで採点する方法には、まだ偏りが残っています。** 検索方式は「簡潔に」と指示したため、内容は正しくても採点の語を省くことがあります（`seen` の × 4 問）。一方、学習後のモデルは定義を丸写しするので、語を含む判定では有利です。反対に、学習後の誤った説明に採点の語が紛れ込んで ○ になる例もありました。数字だけで判断せず、`eval_*.json` の出力原文を読んで目視の判定を併記してください。

### 3.5 学習と評価の流れ

```python
results = {"before": evaluate("before", plain), "rag": evaluate("rag", rag)}   # 学習前に 2 方式を評価
trainer = SFTTrainer(model=model, args=sft, train_dataset=Dataset.from_list(train), peft_config=lora, processing_class=tok)
trainer.train()
model = trainer.model; model.eval()
results["after"] = evaluate("after", plain)                                       # 学習後
```

- 検索方式の評価は、学習**前**のモデルで行います。学習後は `model` に adapter が差し込まれているためです（演習の注意と同じ）
- `plain` は system なしで質問だけを渡します。学習データ（`make_sft_dataset.py` の出力）も system なしなので、形を揃えています
- LoRA の設定は演習と同じです。データが 136 件なので 1 エポック 17 ステップ、10 エポックで 170 ステップです。`save_strategy="no"` にして、途中のチェックポイントは保存しません（最後に adapter だけ保存）
- `max_new_tokens=160` にしています。定義文は中央値 105 字、最長 212 字です。学習前のモデルは長く答えるので途中で切れ、学習後も長い定義は最後まで出ないことがあります。そのため、採点の語は定義の前半から選んでいます

### 確認したこと（監査）

- `glossary_sft.jsonl` が 136 件（配布スクリプトの出力 116 件と「載っていません」の 20 件）で、すべて user と assistant の組であること
- `seen` 以外の評価質問が学習データに無いこと（スクリプト内の `assert`）
- 正解の語が、検索で 1 件目に返る定義に含まれること（3.2 のチェック）
- 各方式で正解になった質問の一覧が、出力原文を目で見た判定と合うこと。合わなかった 2 種類の採点ミスを 3.4 で直した

---

## 4. 結果ファイル

| 場所 | 内容 |
|---|---|
| `lectures/02/result.json` | 演習（20 エポック） |
| `lectures/02/homework/results/basic_ep5/result.json` | 基礎：5 エポック |
| `lectures/02/homework/results/basic_ep10/result.json` | 基礎：10 エポック |
| `lectures/02/homework/results/impl/result.json` | 実装：研究室 GPU サーバの FAQ |
| `lectures/02/homework/results/advanced/` | 発展：`result.json` と、3 方式の出力原文と採点（`eval_*.json`） |

GPU 上の学習は seed を固定しても完全には再現しないので、同じ手順で実行しても、残る失敗の質問は変わることがあります。比べるときは、数字だけでなく失敗の型を見てください。
