# 第5回 技術メモ：演習と宿題（基礎・実装・発展）を再現するためのコード変更

このメモでは、第5回の演習と宿題の 3 レベルを他の人が再現できるように、`app/` と `tests/` に加えた変更と、そのまま使えるテンプレートを説明します。結果と考察は [answer.md](answer.md) にあります。

## 0. 共通：前提と実行環境

- 第1回〜第3回の PR を fork の `main` にマージしてから、`main` から `lec05` を作りました（第3回の `make_quiz` と、承認待ちのツールを含む `app/agent.py` が前提）
- `uv sync --frozen` の後、`uv run pytest -q` が通ることを確かめてから始めます
- `lectures/05/homework/` のスクリプトはパスを指定して実行するので、先頭でリポジトリ直下を `sys.path` に足しています（無いと `ModuleNotFoundError: No module named 'app'`）

```python
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # lectures/05/homework/xxx.py から見たリポジトリ直下
from app.agent import build_mcp_agent  # noqa: E402
```

---

## 1. 演習

### ツールを MCP で公開する（`app/mcp_server.py`）

`TODO(第5回 演習)` の場所に 1 行ずつ足します。関数の docstring と型ヒントが、そのまま MCP のツールの説明文と引数になります。

```python
server.tool()(tools.search_glossary)          # もとからある
server.tool()(tools.get_lecture_summary)      # 第5回 演習で追加
server.tool()(tool_error_on_value_error(tools.make_quiz))  # 第3回のツール（範囲チェックは「3. 実装」）
# save_learning_log は公開しない。承認（requires_approval）は Pydantic AI 側の仕組みで、MCP 越しには付かないため
```

`save_learning_log` のように、エージェント側で承認を挟んでいたツールを MCP サーバーに出すと、どのクライアントからも承認なしで呼べてしまいます。公開するツールは選びます。

### 既製の fetch サーバーを設定だけで足す（`app/mcp_servers.json`）

```json
{
  "mcpServers": {
    "glossary": {"command": "uv", "args": ["run", "python", "-m", "app.mcp_server"]},
    "fetch":    {"command": "uvx", "args": ["mcp-server-fetch"]}
  }
}
```

### 確かめ方

```bash
uv run python -m app.agent --list-tools          # 関数ツール（第3回）：4 個
uv run python -m app.agent --mcp --list-tools    # MCP のツール：glossary_ が 3 個 ＋ fetch_fetch
uv run python -m app.agent --mcp --trace "AIE2026の講座の宿題にある「3レベル」とは何ですか？"
uv run python -m app.agent --mcp --trace "第2回では何を学びますか？"
uv run python -m app.agent --mcp --trace "https://modelcontextprotocol.io/ の冒頭を日本語で3行に要約して"
```

入力トークンは、渡すツールの数で変わります（ツールの説明文が毎回送られるため）。MCP 経由か直接登録かを比べるときは、ツールの数をそろえます。

### ローカル（Codespaces 以外）で fetch が失敗する場合

fetch サーバーは本文の抜き出しに `readabilipy` を使います。`readabilipy` は Node があると JavaScript 版（jsdom）を初回に `npm install` して使います。jsdom の新しい版は Node 22 以上が必要なので、Node が古いマシン（例：v18）では本文の抜き出しで例外になります。Codespaces の devcontainer は Node の LTS を入れるので、この問題は起きません。

ローカルで試すだけなら、**repo に入れない**設定ファイルで、fetch サーバーにだけ Node を見せないようにすると、Python だけの処理に切り替わります。起動スクリプトが `realpath` と `dirname` を使うので、それだけをリンクしたフォルダを `PATH` に入れます。

```bash
mkdir -p ~/nonode-bin && ln -sf /usr/bin/realpath /usr/bin/dirname ~/nonode-bin/
```

```json
"fetch": {"command": "uvx", "args": ["mcp-server-fetch"],
          "env": {"PATH": "/home/<user>/.local/bin:/home/<user>/nonode-bin", "HOME": "/home/<user>"}}
```

この設定ファイルは `build_mcp_agent(Path("…/mcp_servers.local.json"))` に渡して使います（`--mcp` は `app/mcp_servers.json` を読むため）。

---

## 2. 基礎：stdio と Streamable HTTP、docstring の書き換え

### 2 つのつなぎ方の設定

比較用の設定ファイルを `lectures/05/homework/` に置きました。repo の `app/mcp_servers.json` は演習の形のままにしています。

```jsonc
// mcp_servers.stdio.json：クライアントがサーバーを子プロセスとして起動する
{"mcpServers": {"glossary": {"command": "uv", "args": ["run", "python", "-m", "app.mcp_server"]}}}

// mcp_servers.http.json：起動済みのサーバーに URL で接続する
{"mcpServers": {"glossary": {"url": "http://127.0.0.1:8000/mcp"}}}
```

```bash
uv run python -m app.mcp_server --http      # 別のターミナルで起動しておく（127.0.0.1:8000）
uv run python lectures/05/homework/ask_via.py lectures/05/homework/mcp_servers.http.json "AIE2026の講座の宿題にある「3レベル」とは何ですか？" http
```

### プロセスとポートを調べる

接続している最中のプロセスの親子関係と、待ち受けポートを見ます。stdio のサーバーは、エージェントの子孫として現れ、ポートを開きません。

```python
import asyncio, os, subprocess
from pathlib import Path
from pydantic_ai.models.test import TestModel
from app.agent import build_mcp_agent

def descendants(root):
    """ps の一覧から、root の子孫プロセスを (深さ, pid, コマンド) でたどる。"""
    rows = [l.split(None, 2) for l in subprocess.run(["ps", "-eo", "pid=,ppid=,args="],
                                                    capture_output=True, text=True).stdout.splitlines()]
    kids, cmd = {}, {}
    for pid, ppid, *args in rows:
        kids.setdefault(int(ppid), []).append(int(pid)); cmd[int(pid)] = args[0] if args else ""
    out, stack = [], [(root, 0)]
    while stack:
        pid, depth = stack.pop()
        if pid != root:
            out.append((depth, pid, cmd.get(pid, "")))
        stack += [(c, depth + 1) for c in kids.get(pid, [])]
    return out

async def main():
    agent = build_mcp_agent(Path("lectures/05/homework/mcp_servers.stdio.json"))
    async with agent:                      # この間はサーバーにつながっている
        for depth, pid, c in descendants(os.getpid()):
            print("  " * depth, pid, c[:90])
        await agent.run("LoRAとは？", model=TestModel(call_tools=["glossary_search_glossary"]))

asyncio.run(main())
```

```bash
ss -ltnp | grep :8000      # HTTP のサーバーが待ち受けているか
```

- `ps -g` のようなオプションでは、プロセスグループやセッションの指定がずれて何も取れないことがあります。親子関係（ppid）をたどる方が確実です
- `pgrep -f app.mcp_server` は、そのコマンドを実行しているシェル自身にも一致します。「残っているか」を調べるときは注意します
- stdio のサーバーは、`async with agent:` を抜けても子プロセスが残ります。fastmcp の `StdioTransport` は `keep_alive` が既定で `True` で、同じプロセスの中で再接続するためにサーバーを残します。エージェントのプロセスが終わると、サーバーも終わります

### docstring を書き換えて比べる

`app/tools.py` の `search_glossary` の docstring を一時的に書き換え（比べ終わったら元に戻します）、説明文と呼ばれ方を比べます。

```bash
uv run python lectures/05/homework/show_desc.py lectures/05/homework/mcp_servers.stdio.json stdio   # 説明文（API キー不要）
uv run python lectures/05/homework/show_desc.py lectures/05/homework/mcp_servers.http.json  http
uv run python lectures/05/homework/ask_via.py   lectures/05/homework/mcp_servers.stdio.json "RAGとは何ですか？" stdio
```

- stdio は、プロセスごとにサーバーを起動し直すので、docstring の変更がすぐ反映されます
- **HTTP は、サーバーを再起動するまで古い説明文のままです。** 動かしたまま docstring を直しても効かないので、比べるときは HTTP のサーバーを止めて起動し直します

---

## 3. 実装：範囲チェックと、MCP 越しのエラーの伝え方

### ツール本体：ふつうの `ValueError` を投げる（`app/tools.py`）

```python
NUM_LECTURES = 13  # AIE2026 は全13回

def make_quiz(lecture: int) -> str:
    """…（第3回の説明文）…
    lecture は 1〜13（AIE2026 は全13回）。範囲外ならエラーになる。
    """
    if not 1 <= lecture <= NUM_LECTURES:
        raise ValueError(f"lecture は 1〜{NUM_LECTURES} の整数で指定してください（AIE2026 は全{NUM_LECTURES}回）。指定された値: {lecture}")
    candidates = [e for e in load_glossary() if e["lecture"] == lecture]
    if not candidates:   # 範囲内だが用語がない回は、エラーではなくふつうの結果
        ...
```

`app/tools.py` は MCP サーバー・Pydantic AI・ADK から共通で使うので、どのフレームワークの例外にも依存させません。各フレームワークへの変換は、使う側の薄いラッパーで行います。

### MCP サーバー：`ValueError` を `ToolError` に変える（`app/mcp_server.py`）

```python
import functools
from mcp.server.mcpserver.exceptions import ToolError

def tool_error_on_value_error(func):
    @functools.wraps(func)  # 名前・docstring・引数の型をそのまま引き継ぐ（ツールの説明文が変わらない）
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValueError as e:
            raise ToolError(str(e)) from e
    return wrapper

server.tool()(tool_error_on_value_error(tools.make_quiz))
```

**これが無いと、エラー文はモデルに届きません。** MCP の Python SDK は、ツールの例外を 2 種類に分けて扱います。

| 例外 | クライアント（モデル）に届く文 |
|---|---|
| `ToolError`（想定した失敗） | `Error executing tool make_quiz: lecture は 1〜13 の整数で指定してください…` |
| それ以外（`ValueError` など、想定外のクラッシュ扱い） | `Error executing tool make_quiz` だけ（メッセージはサーバーの中に留まる） |

`functools.wraps` を付けると、`inspect.signature` が元の関数をたどるので、ツールの引数のスキーマと説明文は変わりません（`--list-tools` で確かめられます）。

### Pydantic AI のエージェント：`ValueError` を `ModelRetry` に変える（`app/agent.py`）

```python
import functools
from pydantic_ai import ModelRetry

def retry_on_value_error(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValueError as e:
            raise ModelRetry(str(e)) from e
    return wrapper

agent.tool_plain(retry_on_value_error(tools.make_quiz))
```

Pydantic AI では、ツールの中のふつうの例外はそのまま上がって実行が止まります。`ModelRetry` にすると、メッセージが再試行の指示（`RetryPromptPart`）としてモデルに戻ります。再試行の上限は既定で 1 回で、超えると `UnexpectedModelBehavior` になります。MCP のツールのエラーも、Pydantic AI のクライアントの中で同じく `ModelRetry` として扱われます。

### ADK 版：`ValueError` を結果の辞書にする（`lectures/03/homework/adk/aie_agent/agent.py`）

```python
def error_as_result(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValueError as e:
            return {"error": str(e)}
    return wrapper

tools=[..., error_as_result(tools.make_quiz), ...]
```

ADK では、ツールの例外がそのまま上がります。第3回の ADK 版が範囲外の回で止まらないよう、エラー文を結果として返します。

### `--trace` にエラーの戻りを表示する（`app/agent.py` の `print_trace`）

```python
from pydantic_ai.messages import RetryPromptPart

            elif isinstance(part, RetryPromptPart) and part.tool_name:
                print(f"[tool retry]  {part.tool_name} -> {part.model_response().splitlines()[0][:120]}")
```

元の `print_trace` は、ツールの呼び出しと結果だけを表示していて、エラーの戻りは表示されませんでした。`model_response()` は、モデルに実際に渡る文（エラー文 ＋「Fix the errors and try again.」）を返します。

```bash
uv run python -m app.agent --mcp --trace "第99回の確認問題を出して"
# [tool call]   glossary_make_quiz({'lecture': 99})
# [tool retry]  glossary_make_quiz -> Error executing tool make_quiz: lecture は 1〜13 の整数で指定してください（AIE2026 は全13回）。指定された値: 99
```

### テスト（`tests/test_mcp_server.py` ほか）

TestModel は引数を選べず、整数には 0 を入れます。エラーを受けても同じ引数で呼び直すので、範囲外のエラーを起こすのに使えます。正しい引数で呼ばせたいときは `FunctionModel` を使います。

```python
from pydantic_ai import capture_run_messages
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, RetryPromptPart, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

def test_out_of_range_error_reaches_the_model_through_mcp(tmp_path):
    # TestModel は lecture=0 で呼び、エラーを受けても同じ引数で呼び直すので、再試行の上限を超えて止まる
    with capture_run_messages() as messages:
        with pytest.raises(UnexpectedModelBehavior):
            build_mcp_agent(_glossary_only_config(tmp_path)).run_sync("確認問題", model=TestModel(call_tools=[QUIZ_TOOL]))
    retries = [p for m in messages for p in m.parts if isinstance(p, RetryPromptPart)]
    assert "1〜13" in retries[0].model_response()   # ToolError に変えているので、範囲の説明がモデルまで届く

def test_quiz_through_mcp_returns_a_question(tmp_path):
    def respond(messages, info):  # 1 回目は第2回で make_quiz を呼び、2 回目で回答する
        if not any(isinstance(m, ModelResponse) for m in messages):
            return ModelResponse(parts=[ToolCallPart(QUIZ_TOOL, {"lecture": 2})])
        return ModelResponse(parts=[TextPart("回答")])
    result = build_mcp_agent(_glossary_only_config(tmp_path)).run_sync("第2回の確認問題", model=FunctionModel(respond))
    ...
```

- `capture_run_messages()` を使うと、例外で止まった実行でも、それまでのメッセージを取り出せます
- `_glossary_only_config(tmp_path)` は配布されたテストの補助関数で、fetch など外部のサーバーを起動しないよう、glossary サーバーだけの設定ファイルを作ります

配布されたテスト `test_base_tools_are_registered_and_called` は、TestModel が `make_quiz(0)` を呼ぶため、結果の代わりに再試行の指示が戻ります。意図を保ったまま、再試行の指示も「戻った応答」として数えるように直しました。

```python
    answered = len(_parts(result, ToolReturnPart)) + len(_parts(result, RetryPromptPart))
    assert answered == len(_parts(result, ToolCallPart)) - len(pending)
```

### 効いているかの確認（監査）

- MCP サーバーの `tool_error_on_value_error` を一時的に外して `uv run pytest -q tests/test_mcp_server.py` を実行し、エラー文のテストだけが落ちることを確かめる（確かめたら元に戻す）
- 実際のモデルで比べるときは、docstring に範囲を書いた版と消した版の両方で試す。docstring に範囲があると、エラー文が届かなくてもモデルは範囲を知っているので、差が見えにくくなる

---

## 4. 発展：Copilot Chat から同じサーバーを使う

（Copilot Chat での確認の後に記入）

---

## 5. 結果ファイルと補助スクリプト

| 場所 | 内容 |
|---|---|
| `lectures/05/homework/mcp_servers.stdio.json` | 基礎：stdio で glossary サーバーだけにつなぐ設定 |
| `lectures/05/homework/mcp_servers.http.json` | 基礎：Streamable HTTP（`127.0.0.1:8000`）につなぐ設定 |
| `lectures/05/homework/show_desc.py` | 基礎：MCP 経由で見える `search_glossary` の説明文を表示する |
| `lectures/05/homework/ask_via.py` | 基礎：設定ファイルを指定して質問し、ツール呼び出しと requests を表示する |
| `.vscode/mcp.json` | 発展：Copilot Chat（VS Code）から使う設定 |
