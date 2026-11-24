# 第6回 技術メモ：改訂された課題での演習と宿題を再現する手順

[answer.md](answer.md) の結果を再現するための手順と、途中で予測が外れた点・確かめた点をまとめる。改訂前の課題（`app.agent --mcp` を使う版）の技術メモは [old/technical-memo.md](old/technical-memo.md)。

## 0. 上流の取り込み（2026-11-24）

上流は講義日に第6回を書き直した（`c8fcd69` MCP エージェントを `app/mcp_agent.py` に分ける、`4155b64` 演習・宿題を準備と STEP 1〜5 の構成に書き直す、`b15dcf5` 表記の統一）。fork の main には改訂前の解答があるので、次の 3 ファイルが衝突した。

| ファイル | 衝突の中身 | 採った方 |
|---|---|---|
| `app/mcp_server.py` | 改訂前の宿題で足した `get_lecture_summary`・`make_quiz`（`ToolError` に変える版） | 上流（配布の開始状態。宿題は `lec06` で作り直す） |
| `tests/test_mcp_server.py` | 改訂前の宿題のテスト（`app.agent` の `build_mcp_agent` を使う） | 上流（新しいテストは `app.mcp_agent` を使う） |
| `lectures/06/answer.md` | 改訂前の解答と、新しい空の雛形 | 上流の雛形。改訂前の解答は `lectures/06/old/answer.md` に移した |

- 改訂前の `technical-memo.md` と `homework/` も `lectures/06/old/` に移した（スクリプト中のパスは移動前のまま）
- `app/mcp_servers.json` も上流の版（glossary だけ）に戻した。main に fetch を足した設定が残っていたため。演習は glossary だけの状態から始める
- `app/agent.py` の `--mcp` は上流でも残っている（第5回までのエージェントと、第6回のエージェントが並ぶ）
- 取り込み後の main で `uv run pytest -q` は 48 passed。main を push してから `lec06` を切った

```bash
git fetch upstream && git switch main && git merge --ff-only origin/main
git merge --no-ff upstream/main          # 衝突 3 件
git checkout --theirs app/mcp_server.py tests/test_mcp_server.py lectures/06/answer.md   # answer.md は先に old/ へ退避
git checkout upstream/main -- app/mcp_servers.json
```

## 1. 演習（STEP 1〜4）

実行ログはすべて `lectures/06/runs/` にある。バナーを消すため `PYDANTIC_AI_NO_BANNER=1` を付けた。

```bash
uv run python -m app.agent --list-tools        > runs/step1_agent_list_tools.txt
uv run python -m app.mcp_agent --list-tools    > runs/step1_mcp_list_tools.txt
uv run python -m app.mcp_agent --trace "AIE2026の講座の宿題にある「3レベル」とは何ですか？"   > runs/step2_trace.txt
# app/mcp_servers.json に fetch を足す（課題文のとおり mcp-server-fetch==2026.11.11 --no-readability-js）
uv run python -m app.mcp_agent --trace "https://modelcontextprotocol.io/ の冒頭を日本語で3行に要約して"   > runs/step3_trace.txt
# aws を足す
uv run python -m app.mcp_agent --trace "AWSのドキュメントを検索して、Amazon S3 のバージョニングを2行で説明して"   > runs/step4_trace.txt
```

- このマシンの Node は v18。改訂前の課題では fetch サーバーの本文抽出（readability、Node 22 以上が必要）を避ける工夫が要った。新しい課題文は `--no-readability-js` で Python だけで抽出するので、何もせずに動いた
- ツールの数とトークン：STEP 2 の質問を、glossary だけの設定（commit 済みの版）と 3 サーバーの設定で、交互に 3 回ずつ流した（`runs/tool_count_compare.txt`）。呼び出しは 6 回とも同じで、入力は 715 と 5,383 tokens（各 3 回とも同じ値）。差 4,668 tokens をモデル応答 2 回で割ると、1 回あたり約 2,334 tokens がツールの説明文の分

## 2. 宿題（基礎）

```bash
# app/mcp_server.py の TODO の下に server.tool()(tools.get_lecture_summary) を足す
git status                                      # runs/basic_git_status.txt（変更は app/mcp_server.py だけ）
uv run python -m app.mcp_agent --list-tools     # runs/basic_list_tools.txt
uv run python -m app.mcp_agent --trace "第2回では何を学びますか？"   # 3 回：runs/basic_trace_r{1,2,3}.txt
uv run pytest -q                                # runs/basic_pytest.txt（48 passed）
```

`git status` には、まだ commit していないログのファイル（`??`）と、第4回で手元に置いているファイルも出るが、変更（`M`）は `app/mcp_server.py` だけ。

## 3. 宿題（実装）

### 3.1 提出版

`app/mcp_server.py` の `make_quiz` は、`tools.make_quiz` を呼び、`ValueError`（範囲外）を受けたら `out_of_range_message()` を return する。`tools.make_quiz` を変えないのは、`app/agent.py`（第3回のエージェント）がこの `ValueError` を `ModelRetry` として使い、テストもあるため。

### 3.2 比較の仕組み

- `homework/quiz_server.py <mode> [norange]`：渡し方だけを変えたサーバー。`return`（提出版を呼ぶ）、`value`（同じ文面で `raise ValueError`）、`toolerror`（同じ文面で `raise ToolError`）。`functools.wraps` で名前・説明文・引数を提出版とそろえる。`norange` は説明文から範囲の一文を除く（除いたことを assert で確かめる）
- `homework/quiz_error_compare.py`：版ごとに、そのサーバーだけを起動する設定ファイルを一時ディレクトリに作り、`app.mcp_agent.build_mcp_agent` で同じ質問をする。版は交互に流す。`capture_run_messages` で、モデルに渡った `ToolReturnPart` の中身と、`RetryPromptPart.model_response()`（Pydantic AI が足す「Fix the errors and try again.」を含む、モデルが実際に読む文面）を記録する

```bash
uv run python lectures/06/homework/quiz_error_compare.py --reps 3                                       # 第99回・提出版の説明文
uv run python lectures/06/homework/quiz_error_compare.py --reps 3 --norange                             # 第99回・範囲なし
uv run python lectures/06/homework/quiz_error_compare.py --reps 3 --norange --question "第14回のクイズを作って"
uv run python lectures/06/homework/quiz_error_compare.py --reps 3 --question "第14回のクイズを作って"
uv run python lectures/06/homework/quiz_error_compare.py --report [--norange] [--question ...]          # 集計（API 不要）
```

生データは `homework/results/quiz_error_runs.jsonl`（36 件）、集計は `homework/results/quiz_error_report.txt`。

### 3.3 予測が外れたことと、そのあとにしたこと

1. **第99回では、return の版が 1 回もツールを呼ばなかった。** 予測は「return のメッセージが届いて説明する」だったが、比べる前提（ツールが呼ばれること）が成り立たなかった。コードの誤りを疑ったが、呼ばれなかった回は 1 回目の応答でツールを呼ばずに回答しており（モデル応答 1 回、入力は ValueError の版の呼ばなかった回と同じ 534 tokens）、呼ばれた版（ValueError・ToolError）では文面がそのまま渡っていた。サーバーではなくモデルの判断で、99 は明らかに範囲外なので呼ばずに答えていた
2. **説明文の範囲の一文を除いても、9 回とも呼ばれなかった。** 次に、ありえそうな値（第14回）にした。このとき予測を `runs/00_predictions.md` に書き足してから流した
3. **第14回の ValueError の版は、別のツールを呼んで調べた。** 予測は「回数を推測で答える」だったが、実際は `get_lecture_summary(14)` を呼んで「要点はまだありません」を得て、「まだ用意されていない」と答えた。推測より、手元のツールで調べる方を選んだ

### 3.4 テスト

`tests/test_mcp_server.py` に 5 件足した（合計 53 passed）。
- 公開されたツール（`search_glossary`・`get_lecture_summary`・`make_quiz`）
- 第2回で問題が返ること
- 範囲外（0・14・99）が `ToolReturnPart` で戻り、`RetryPromptPart` にならないこと

モデルは `FunctionModel` で、1 回目に決まった引数でツールを呼び、2 回目で回答させる（TestModel は引数を選べない）。`except ValueError` を `except KeyError` に変えて return の経路を壊すと、範囲外の 3 件が fail になることを確かめた。

## 4. 宿題（発展）

- 公式ドキュメント（https://code.claude.com/docs/en/mcp 、2026-11-24 に参照）で、スコープごとの保存場所、`claude mcp add` の書式、`.mcp.json` の形式、スコープの優先順位、project スコープの承認、環境変数の展開を確かめた
- 手元の確認は、作業用の一時ディレクトリ（確認後に削除）で行った。`--scope project` は、そのディレクトリの `.mcp.json` にだけ書く。`~/.claude.json` に書く local・user スコープは使っていない（自分の設定を変えないため）

```bash
# 演習の設定をそのまま .mcp.json にする（glossary は --directory でリポジトリを指す）
claude mcp list        # aws だけ「url but no type」で Skipped

# CLI で登録する
claude mcp add --scope project glossary -- uv run --directory <リポジトリ直下> python -m app.mcp_server
claude mcp add --scope project fetch -- uvx mcp-server-fetch==2026.11.11 --no-readability-js
claude mcp add --scope project --transport http aws https://knowledge-mcp.global.api.aws
claude mcp list        # 3 つとも Pending approval
```

- 結果のファイル：`homework/results/claude_code/`。`mcp.json.copied_as_is`・`mcp.json.from_cli_add`・`claude_mcp_list.txt`。パスは `<リポジトリ直下>` などに置き換えた。claude.ai のコネクタの行は除いた
- 逆向き：`build_mcp_agent(Path(".../.mcp.json"))` と `print_tools` で、Claude Code が書いた設定を演習のエージェントで読み、3 サーバー・9 ツールが出た
- 確かめていないこと：Claude Code の対話画面で承認したあと、実際にツールを呼ぶところ。承認は自分の設定の変更にあたるので行っていない

### 手元の資料との食い違い

講座の資料（受講生向けの要約・模範解答のメモ）の発展の記入例には、「演習の設定をそのまま `.mcp.json` にコピーすれば Claude Code から同じツール群を呼び出せる」という趣旨の記述があった。手元の確認では、`url` だけの `aws` は読み飛ばされ、そのままでは使えなかった（Claude Code 2.1.327）。公式ドキュメントにも同じ注意がある。資料の版の違いによる可能性もあるが、answer.md には自分で確かめた結果だけを書いた。

## 5. このあと気をつけること

- 比べる実験では、まず比べる前提が成り立っているか（今回はツールが呼ばれるか）を 1 回流して確かめてから、回数を重ねる
- 「同じ形式」と書かれていても、クライアント側で全項目が読み込まれたかを一覧で確かめる
