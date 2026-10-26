# 第3回 技術メモ：演習と宿題（基礎・実装・発展 a）を再現するためのコード変更

このメモでは、第3回の演習と宿題の 3 レベルを他の人が再現できるように、`app/` と `tests/` に加えた変更と、そのまま使えるテンプレートを説明します。結果と考察は [answer.md](answer.md) にあります。

## 0. 共通：実行環境

| 用途 | 環境 | 作り方 |
|---|---|---|
| 演習・基礎・実装 | repo の環境（Pydantic AI 2.57.0） | `uv sync --frozen` |
| 発展（a）ADK | repo の外の別の venv（google-adk 2.13.0） | 下記。ADK は `uv.lock` に入っていないので、repo の環境には入れない |

```bash
# リポジトリの外（例：リポジトリの 1 つ上）で
uv venv envs/lec03-adk --python 3.12
VIRTUAL_ENV=envs/lec03-adk uv pip install google-adk
```

- どちらも `GEMINI_API_KEY` を読みます。ADK（google-genai）は `GOOGLE_API_KEY` を優先するので、両方を設定している場合はそちらが使われます
- Pydantic AI の起動時のバナーは、`PYDANTIC_AI_NO_BANNER=1` で消せます
- `lectures/03/homework/` のスクリプトはパスを指定して実行するので、スクリプトの先頭でリポジトリ直下を `sys.path` に足して、`app` パッケージを import できるようにしています。これが無いと `ModuleNotFoundError: No module named 'app'` になります

```python
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # lectures/03/homework/xxx.py から見たリポジトリ直下
from app import tools  # noqa: E402
```

---

## 1. 演習：`make_quiz` ツールを追加する

### `app/tools.py` に関数を足す

```python
import random

def make_quiz(lecture: int) -> str:
    """指定した回（1始まりの整数）の用語から1つを選び、「この用語の意味は？」という確認問題と答えを返す。

    「第2回の確認問題を出して」「LoRAの回の復習クイズがほしい」のように、
    学習者が理解度を確かめる問題を求めたときに使う。問題だけを先に見せ、
    answer（用語集の定義）は学習者が答えたあとに示すこと。
    """
    candidates = [e for e in load_glossary() if e["lecture"] == lecture]
    if not candidates:
        available = sorted({e["lecture"] for e in load_glossary()})
        return f"第{lecture}回の用語は用語集にありません。用語がある回: {', '.join(map(str, available))}"
    entry = random.choice(candidates)
    return json.dumps({"lecture": lecture, "question": f"「{entry['term']}」の意味は？",
                       "answer": entry["definition"]}, ensure_ascii=False)
```

- docstring の 1 段落目は「何をするツールか」、2 段落目は「いつ使うか」（利用者の言い方の例）と「結果をどう使うか」です。モデルはこれを読んでツールを選びます
- 用語が無い回を指定されたときも、例外ではなく、モデルが次の行動を決められる文字列を返します

### `app/agent.py` で登録する

`TODO(第3回 演習)` の行を、次の 1 行に置き換えます。

```python
agent.tool_plain(tools.make_quiz)  # 第3回 演習で追加
```

### 確かめ方

```bash
uv run python -m app.agent --list-tools                       # docstring がモデルに見えているか（API キー不要）
uv run python -m app.agent --trace "第2回の内容から確認問題を1問出して"
uv run python -m app.agent --trace "LoRAの回の復習クイズがほしい"   # 回の番号を言わない場合
uv run pytest -q
```

2 つ目の質問では、`search_glossary('LoRA')` で第2回だと調べてから `make_quiz({'lecture': 2})` を呼びます（`requests=3`）。

### テスト

```python
# tests/test_tools.py
def test_make_quiz_picks_a_term_of_the_lecture():
    terms_of_lecture2 = {e["term"]: e["definition"] for e in tools.load_glossary() if e["lecture"] == 2}
    for _ in range(20):  # 用語はランダムに選ばれるので、何度か試す
        quiz = json.loads(tools.make_quiz(2))
        term = quiz["question"].removeprefix("「").removesuffix("」の意味は？")
        assert term in terms_of_lecture2
        assert quiz["answer"] == terms_of_lecture2[term]

# tests/test_agent.py
def test_make_quiz_is_registered_and_returns_to_the_model():
    model = TestModel(call_tools=["make_quiz"])
    with agent.override(model=model):
        result = agent.run_sync("第2回の確認問題を出して")
    assert "make_quiz" in {t.name for t in model.last_model_request_parameters.function_tools}
    returns = _parts(result, ToolReturnPart)
    assert returns and returns[0].tool_name == "make_quiz"
```

`TestModel(call_tools=["make_quiz"])` は、指定したツールだけを呼ぶ偽モデルです。引数は型に合わせて適当な値（`lecture` なら整数）を作ります。

---

## 2. 基礎：INSTRUCTIONS とツールの docstring を書き換えて比べる

### 手で行う場合

課題文どおり、`app/agent.py` の `INSTRUCTIONS`、または `app/tools.py` の docstring を書き換えて、同じ質問を `--trace` で実行します。比べるときは、次の点をそろえて記録します。

- `[tool call]` の行：どのツールを、どの引数で、どの順に呼んだか（1 回の応答で並べて呼んだか、結果を見てから次を呼んだか）
- `[usage]` の `requests`（LLM を呼んだ回数）と `input_tokens`
- 回答の中身（指示に従ったか。例：最後に「関係する回」が付くか）

同じ版・同じ質問でも、実行ごとに少し揺れます。各 2 回以上試してください。

### 比較スクリプトでまとめて行う場合

ファイルを何度も書き換えずに済むよう、[homework/basic_compare.py](homework/basic_compare.py) で、版ごとにエージェントを組み立てて実行しました。

```bash
uv run python lectures/03/homework/basic_compare.py --out <出力ディレクトリ> --reps 2
uv run python lectures/03/homework/basic_compare.py --out <出力ディレクトリ> --variants V4_minimal_and_quiz_doc_without_hiding   # 指定した版だけを追加で実行
```

要所は、`Tool(関数, description=...)` で、関数はそのままに説明文だけを差し替えることです。

```python
from pydantic_ai import Agent, Tool

# 版の名前: (INSTRUCTIONS, {ツール関数: 説明文})。説明文を変えない版は元の docstring を使う
VARIANTS = {
    "V0_base": (INSTRUCTIONS, {}),
    "V1_minimal_instructions": (MINIMAL_INSTRUCTIONS, {}),
    "V2_narrow_glossary_doc": (INSTRUCTIONS, {tools.search_glossary: NARROW_GLOSSARY_DOC}),
    ...
}

def build_agent(instructions, descriptions):
    funcs = [tools.search_glossary, tools.get_lecture_summary, tools.make_quiz]
    return Agent(instructions=instructions,
                 tools=[Tool(f, description=inspect.cleandoc(descriptions.get(f, inspect.cleandoc(f.__doc__))))
                        for f in funcs])
```

結果は、ツール呼び出し・ツールの結果・`requests`・トークン数・回答を JSON（`basic_compare.json`）に保存します。レート制限（429）や混雑（503）のときは、30 秒待って 2 回まで再試行します。

### 版が意図どおりかを確かめる（監査）

比較の前提は「差し替えた箇所以外は、元のエージェントと同じ」であることです。TestModel を使えば、API を呼ばずに、モデルに渡るツール定義を比べられます。

```python
from pydantic_ai.models.test import TestModel
from app.agent import agent, INSTRUCTIONS

def seen(a):
    m = TestModel(call_tools=[])
    a.run_sync("x", model=m)
    return sorted((t.name, t.description) for t in m.last_model_request_parameters.function_tools)

real = seen(agent)
for name, (ins, docs) in VARIANTS.items():
    diff = [x[0] for x, y in zip(real, seen(build_agent(ins, docs))) if x != y]
    print(name, "INSTRUCTIONS 同じ" if ins == INSTRUCTIONS else "INSTRUCTIONS 変更", "説明文が違うツール:", diff)
```

### 結果の読み方の注意

- 予測と違う結果が出たら、その一文を消した版、指示を最小にした版などを足して切り分けます。今回は「docstring の『答えを伏せる』で答えを伏せた」と思っていましたが、INSTRUCTIONS と docstring の両方から伏せる指示を消した版（V4）でも伏せたので、モデルが元々そう振る舞うことがわかりました
- 入力トークンは、登録されているツールの数で変わります（ツールの説明文は、使わない回にも毎回送られる）。版どうしを比べるときは、ツールの数をそろえます

---

## 3. 実装：保存の前に利用者の確認を挟む `save_learning_log`

### `app/tools.py`：保存するツール

```python
import re
from datetime import datetime

LEARNING_LOG_DIR = Path(__file__).resolve().parent.parent / "learning_log"  # .gitignore 済み。テストでは差し替える

def save_learning_log(title: str, content: str, lecture: int | None = None) -> str:
    """学習の記録（学んだこと・疑問・次にやること）を learning_log/ に Markdown で保存する。

    「今日の学びを記録して」「この内容をメモに残して」のように、学習者が記録を頼んだときだけ使う。
    title は記録の見出し（短く）、content は本文、lecture は関係する回（分かるときだけ）。
    保存の前に利用者の確認が入るので、承認されなかったときは保存されなかったことを伝える。
    """
    now = datetime.now()
    slug = re.sub(r"[^0-9A-Za-zぁ-んァ-ヶ一-龠ー]+", "-", title).strip("-")[:40] or "log"  # ファイル名に使えない文字を除く
    LEARNING_LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LEARNING_LOG_DIR / f"{now:%Y-%m-%d_%H%M%S}_{slug}.md"
    header = f"# {title}\n\n- 日時: {now:%Y-%m-%d %H:%M}\n" + (f"- 関係する回: 第{lecture}回\n" if lecture else "")
    path.write_text(f"{header}\n{content}\n", encoding="utf-8")
    return f"保存しました: learning_log/{path.name}"
```

- **ファイル名はモデルが決めた見出しから作るので、`/` や `..` を必ず取り除きます。** そのままだと `learning_log/` の外に書き出せてしまいます
- 保存先をモジュール変数にしておくと、テストで `monkeypatch.setattr(tools, "LEARNING_LOG_DIR", tmp_path)` と差し替えられます
- `learning_log/` は、repo の `.gitignore` に最初から入っています（個人の学習ログは共有しない）

### `app/agent.py`：承認が必要なツールとして登録する

```python
from pydantic_ai import Agent, DeferredToolRequests, DeferredToolResults, ToolDenied

# output_type に DeferredToolRequests を含めると、承認が必要なツールが呼ばれたときに、
# 実行せずに「承認待ちの呼び出し」を出力として返して止まる
agent = Agent(instructions=INSTRUCTIONS, output_type=[str, DeferredToolRequests])
...
agent.tool_plain(tools.save_learning_log, requires_approval=True)
```

`requires_approval=True` だけでは足りません。`output_type` に `DeferredToolRequests` が無いと、承認待ちで止まったときに返す先がありません。

### 確認して続きを実行する

```python
def ask_approvals(requests: DeferredToolRequests, answer=input) -> DeferredToolResults:
    """承認待ちのツール呼び出しを1つずつ見せ、利用者に y/N で答えてもらう（Human-in-the-loop）。"""
    results = DeferredToolResults()
    for call in requests.approvals:
        print(f"\n[承認待ち] {call.tool_name}")
        for key, value in call.args_as_dict().items():
            print(f"  {key}: {value}")
        if answer("実行してよいですか？ [y/N] ").strip().lower() == "y":
            results.approvals[call.tool_call_id] = True
        else:
            results.approvals[call.tool_call_id] = ToolDenied("利用者が実行を許可しませんでした。")
    return results


def run_with_approval(target: Agent, question: str, model, answer=input):
    """承認待ちで止まったら利用者に確認し、その結果を渡して続きを実行する。最終回答が出るまで繰り返す。"""
    result = target.run_sync(question, model=model)
    while isinstance(result.output, DeferredToolRequests):
        result = target.run_sync(message_history=result.all_messages(), model=model,
                                 deferred_tool_results=ask_approvals(result.output, answer),
                                 usage=result.usage)  # 止まる前の実行の使用量も合算して表示する
    return result
```

`main()` の `target.run_sync(args.question, model=build_model())` を、`run_with_approval(target, args.question, build_model())` に置き換えます。

- `answer` を引数にしておくと、テストで `answer=lambda _: "y"` のように差し替えられます
- 拒否は `ToolDenied(メッセージ)` として渡します。そのメッセージがツールの結果としてモデルに戻るので、モデルは「保存されなかった」ことを踏まえて答えます
- **`usage=result.usage` を忘れないこと。** これが無いと、再開した実行の使用量しか残らず、`--trace` の `requests` が実際より少なく表示されます（最初の版ではこのバグがあり、`requests=1` と表示されました）

### 確かめ方

```bash
echo y | uv run python -m app.agent --trace "今日はLoRAとQLoRAの違いを学んだ。学習ログに保存して"
echo n | uv run python -m app.agent --trace "第3回でツールの説明文が大事だとわかった。記録しておいて"
uv run python -m app.agent --trace "PEFTとは？"     # 記録を頼まない質問では呼ばれないこと
```

確かめた後に `learning_log/` にできたファイルは、自分の学習ログでなければ消しておきます。

### テスト（TestModel、API キー不要）

```python
def _run_save_log(monkeypatch, tmp_path, reply):
    """TestModel に save_learning_log を呼ばせ、承認の問いに reply と答えたときの結果を返す。"""
    monkeypatch.setattr(tools, "LEARNING_LOG_DIR", tmp_path)
    with agent.override(model=TestModel(call_tools=["save_learning_log"])):
        first = agent.run_sync("今日の学びを記録して")
        assert isinstance(first.output, DeferredToolRequests)          # 実行されずに承認待ちで止まる
        assert list(tmp_path.iterdir()) == []                          # この時点ではまだ保存されていない
        results = ask_approvals(first.output, answer=lambda _: reply)
        return agent.run_sync(message_history=first.all_messages(), deferred_tool_results=results)

def test_save_learning_log_writes_only_after_approval(monkeypatch, tmp_path):
    result = _run_save_log(monkeypatch, tmp_path, "y")
    assert len(list(tmp_path.glob("*.md"))) == 1

def test_save_learning_log_is_not_written_when_denied(monkeypatch, tmp_path):
    result = _run_save_log(monkeypatch, tmp_path, "n")
    assert list(tmp_path.iterdir()) == []
    assert isinstance(result.output, str)                              # 拒否されても会話は続き、回答で終わる

def test_run_with_approval_counts_usage_of_both_runs(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "LEARNING_LOG_DIR", tmp_path)
    result = run_with_approval(agent, "今日の学びを記録して", TestModel(call_tools=["save_learning_log"]),
                               answer=lambda _: "y")
    assert result.usage.requests == 2                                  # 承認待ちで止まる前の 1 回 ＋ 再開後の 1 回
```

ツール単体のテスト（`tests/test_tools.py`）では、見出しに `"LoRA/../QLoRA"` を渡しても、保存先の外に書かないことを確かめます。

### 既存のテストの直し方

配布されているテスト `test_base_tools_are_registered_and_called` は、`TestModel()` が登録された全ツールを呼びます。承認が必要なツールは承認待ちで止まり、結果（`ToolReturnPart`）が戻らないので、「呼び出しの数 ＝ 結果の数」の判定が落ちます。テストの意図（呼ばれたツールの結果がモデルに戻る）は保ったまま、承認待ちの数を差し引いて比べます。

```python
from pydantic_ai import DeferredToolRequests

    # 承認が必要なツール（第3回 宿題の save_learning_log）は、承認されるまで実行されず結果も戻らない
    pending = result.output.approvals if isinstance(result.output, DeferredToolRequests) else []
    assert len(_parts(result, ToolReturnPart)) == len(_parts(result, ToolCallPart)) - len(pending)
```

### テストが本当に効いているかの確認（監査）

`requires_approval=True` を一時的に `False` にして `uv run pytest -q` を実行し、追加したテストが落ちることを確かめます（確かめたら元に戻す）。今回は 2 件が落ちました。

**注意：** この状態では、配布されているテストが TestModel 経由で本物の `learning_log/` に書き込みます。確かめた後に、できたファイルを消してください。

---

## 4. 発展（a）：同じエージェントを ADK で作り直す

### ファイルの配置

`adk web` / `adk run` は、指定したフォルダの下にあるパッケージの `agent.root_agent` を読みます。

```
lectures/03/homework/adk/
├── aie_agent/
│   ├── __init__.py      # from . import agent
│   └── agent.py         # root_agent を定義
└── adk_compare.py       # 比較用スクリプト
```

### `aie_agent/agent.py`

```python
import sys
from pathlib import Path

from google.adk.agents import Agent
from google.adk.tools import FunctionTool

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))  # リポジトリ直下（app パッケージ）を import できるようにする
from app import tools  # noqa: E402
from app.config import MODEL  # noqa: E402

INSTRUCTIONS = """\
...（app/agent.py の INSTRUCTIONS と同じ文面）...
"""

root_agent = Agent(
    name="aie_agent",
    model=MODEL,  # 文字列で渡すと Gemini（google-genai）が使われ、GEMINI_API_KEY を読む
    description="AIE2026 の学習支援エージェント（用語集の検索・回の要点・確認問題・学習ログ）",
    instruction=INSTRUCTIONS,
    tools=[
        tools.search_glossary,      # 関数をそのまま渡すと FunctionTool として包まれる
        tools.get_lecture_summary,
        tools.make_quiz,
        FunctionTool(tools.save_learning_log, require_confirmation=True),  # 実行前に利用者の確認を求める
    ],
)
```

- `app/tools.py` と `app/config.py` は標準ライブラリしか使わないので、ADK の環境からも import できます。`app/agent.py` は Pydantic AI を import するので、ADK の環境からは読めません。そのため INSTRUCTIONS は複製し、比較スクリプトで元の文面と一致するかを毎回確かめます
- ADK 2.x では、`Agent` は `LlmAgent` と同じものです。用語集にもあるとおり 2.0 で 1.x から破壊的変更が入っているので、古い記事のコードがそのまま動くとは限りません。使っている版のコードを確かめてください

### 起動

```bash
# リポジトリ直下で
../envs/lec03-adk/bin/adk web lectures/03/homework/adk --port 8765    # ブラウザで http://127.0.0.1:8765
../envs/lec03-adk/bin/adk run lectures/03/homework/adk/aie_agent       # ターミナルで対話
```

- `adk web` は、エージェントのフォルダに `.adk/session.db`（会話を保存する SQLite）を作ります。repo に入らないよう、`.gitignore` に `.adk/` を足しました
- サーバーを別のマシンで動かしている場合は、`ssh -L 8765:127.0.0.1:8765 <サーバー>` でポートを転送し、手元のブラウザで開きます

### 確認（Human-in-the-loop）をプログラムから扱う

`require_confirmation=True` のツールをモデルが呼ぶと、ADK はツールを実行せずに、`adk_request_confirmation` という関数呼び出しのイベントを出して止まります。続けるには、その呼び出しの id に対する関数の応答として `{"confirmed": True/False}` を送ります。

```python
from google.adk.runners import InMemoryRunner
from google.genai import types

CONFIRM = "adk_request_confirmation"

runner = InMemoryRunner(agent=root_agent, app_name="aie_agent")
session = await runner.session_service.create_session(app_name="aie_agent", user_id="u")
message = types.Content(role="user", parts=[types.Part(text=question)])
while message is not None:
    pending = None
    async for event in runner.run_async(user_id="u", session_id=session.id, new_message=message):
        for part in (event.content.parts if event.content else []):
            if part.function_call and part.function_call.name == CONFIRM:
                pending = part.function_call      # 確認の要求
    message = None
    if pending is not None:
        ok = input("実行してよいですか？ [y/N] ").strip().lower() == "y"
        message = types.Content(role="user", parts=[types.Part(function_response=types.FunctionResponse(
            id=pending.id, name=CONFIRM, response={"confirmed": ok}))])
```

- 承認すると元のツールが実行され、拒否するとツールの結果は `{'error': 'This tool call is rejected.'}` になります
- `adk web` では、この確認を UI が扱います

### イベントから使用量とツール呼び出しを読む

ADK には Pydantic AI の `result.usage` にあたるまとめが無いので、イベントから数えます。

```python
async for event in runner.run_async(...):
    if event.usage_metadata:                   # モデルの応答 1 回ごとに使用量が付く
        llm_responses += 1
        input_tokens += event.usage_metadata.prompt_token_count or 0
    for part in (event.content.parts if event.content else []):
        if part.function_call:  ...            # ツール呼び出し
        elif part.function_response:  ...      # ツールの結果
```

比較スクリプト [homework/adk/adk_compare.py](homework/adk/adk_compare.py) は、演習の質問と学習ログの保存（承認・拒否）を ADK 版に投げ、これらを JSON に保存します。

```bash
../envs/lec03-adk/bin/python lectures/03/homework/adk/adk_compare.py --out <出力ディレクトリ>
```

### モデルに実際に送られている内容を見る

フレームワークが自動で足すものは、`before_model_callback` で確かめられます。

```python
def show_request(callback_context, llm_request):
    print(llm_request.config.system_instruction)     # 送られるシステム指示
    print([d.name for d in llm_request.config.tools[0].function_declarations])
    return None                                      # None を返すと、そのままモデルを呼ぶ

root_agent.before_model_callback = show_request
```

ADK は、INSTRUCTIONS の後ろに「You are an agent. Your internal name is "aie_agent". The description about you is …」を足していました。

### `adk web` の画面が使う API

画面を開けない環境でも、同じ情報を API で取れます。

```bash
B=http://127.0.0.1:8765
S=$(curl -s -X POST $B/apps/aie_agent/users/u/sessions -H 'Content-Type: application/json' -d '{}' | jq -r .id)   # jq が無ければ python で id を取り出す
curl -s -X POST $B/run -H 'Content-Type: application/json' \
  -d "{\"appName\":\"aie_agent\",\"userId\":\"u\",\"sessionId\":\"$S\",\"newMessage\":{\"role\":\"user\",\"parts\":[{\"text\":\"LoRAとQLoRAの違いは？\"}]}}"   # イベントの一覧
curl -s $B/dev/apps/aie_agent/debug/trace/session/$S     # トレース（OpenTelemetry のスパン）
curl -s $B/dev/apps/aie_agent/graph                       # エージェントとツールのグラフ（Graphviz の dot）
curl -s $B/openapi.json                                   # 使える API の一覧
```

### Pydantic AI 版と比べるときの注意（監査）

- **ツールの数をそろえる。** ツールの説明文は毎回送られるので、ツールが 2 つのときの数字と 4 つのときの数字を比べると、差を大きく見誤ります。今回は最初にこの誤りをし（783 と 1,635 を比べて「約 2 倍」と判断）、測り直すと 1,381 と 1,635 で、差は約 250 でした
- **1 回ずつの実行で「フレームワークの差」と言わない。** 同じ質問でも、検索してから保存するか、すぐ保存するかは実行ごとに変わりました
- ツール宣言（名前・引数のスキーマ・説明文）が、どちらも同じ docstring と型ヒントから作られていることは、`FunctionTool(関数)._get_declaration()` で確かめられます

---

## 5. 結果ファイル

| 場所 | 内容 |
|---|---|
| `lectures/03/homework/results/basic_compare.json` | 基礎：6 つの版 × 質問ごとのツール呼び出し・ツールの結果・requests・トークン・回答 |
| `lectures/03/homework/results/adk_compare.json` | 発展：ADK 版の 5 つの例のイベント・LLM 呼び出し回数・トークン・保存されたファイル |

モデルの出力は実行ごとに揺れるので、同じ手順でも細部は変わることがあります。比べるときは、ツールの選び方の型（呼ぶ・呼ばない、並べて呼ぶ・順に呼ぶ）を見てください。
