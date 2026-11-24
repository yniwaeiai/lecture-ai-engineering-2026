# 第6回 解答

> **作業の分担。** この回の作業は、Claude Code（Claude Opus 5.5）に指示して行わせた。自分で決めたのは、上流の更新を取り込むこと、宿題を見直すこと、Omnicampus の記入案を作ること。実行・分析・文章は Claude Code が行った。
>
> **改訂前の版について。** 第6回の課題は、講義の前に「第5回」として公開されていた版で一度取り組んだ（PR #4）。講義日（2026-11-23）に課題が書き直されたので（`app/mcp_agent.py` を使う構成、STEP 4 の AWS Knowledge、宿題の実装・発展の変更）、新しい課題文で演習と宿題をやり直した。改訂前の解答は [old/answer.md](old/answer.md) に残した。再現の手順と、途中の誤りは [technical-memo.md](technical-memo.md) にある。
>
> 実行環境：ローカル（Ubuntu、Python 3.12、`uv sync --frozen`）。モデルは `gemini-3.5-flash-lite`。実行ログは `lectures/06/runs/`。

## 演習

- STEP 1 のツールの名前：`glossary_search_glossary`
  - `app.agent --list-tools` は `search_materials` の 1 個（第5回までの、関数を直接登録したエージェント）。`app.mcp_agent --list-tools` は、1 行目に `[server] glossary: コマンドで起動（uv run python -m app.mcp_server）` と出て、ツールは 1 個。説明文と引数の形は同じで、違うのは名前の前の `glossary_`（設定ファイルのサーバー名）だけ
- STEP 2 の [tool call]：`glossary_search_glossary({'query': '3レベル'})`
  - 入力 715 tokens / 出力 156 tokens / モデル応答 2 回。回答の最後に「関係する回：第1回」
- STEP 3 の [tool call]：`fetch_fetch({'url': 'https://modelcontextprotocol.io/'})`
  - 入力 2,179 tokens / モデル応答 2 回。fetch サーバーは `robots.txt` を確かめてから、リダイレクト先（`/docs/2026-07-28/getting-started/intro.md`）まで取得していた
- STEP 4 の [tool call]：`aws_aws___search_documentation({'topics': ['general'], 'search_phrase': 'Amazon S3 versioning overview'})`
  - `aws_` で始まるツールが 5 個増え、合計 7 個。入力 6,359 tokens / モデル応答 2 回。日本語の質問だったが、モデルは最初から英語で検索した
- 気づき・疑問：
  - **ツールを足すと、使わなくても毎回トークンがかかる。** STEP 2 と STEP 4 は質問が違うので、トークン数をそのまま比べられない。そこで STEP 2 の質問を、サーバー 1 つ（glossary）と 3 つ（＋fetch・aws）の設定で 3 回ずつ流した（`runs/tool_count_compare.txt`）。呼ばれたツールと引数は 6 回とも同じ（`glossary_search_glossary({'query': '3レベル'})`）で、入力は 715 → 5,383 tokens（3 回とも同じ値）。モデル応答 1 回あたり約 2,300 tokens が、使わないツールの説明文の分だった。`--list-tools` の表示も 2,003 → 9,214 文字に増えた
  - **INSTRUCTIONS の「必ず」は、ツールが増えると守られにくい。** STEP 3 の回答では、用語集を引かずに「関係する回：講座の用語集やカリキュラム内でMCP関連を扱う回」と書き、第6回と特定できなかった。INSTRUCTIONS には「必ず search_glossary で確認する」とあるが、URL の要約には fetch だけで足りると判断した
  - **設定 1 行で、外部に送るものが増える。** STEP 4 の質問は AWS のサーバーに送られた。STEP 3 の fetch も、URL を渡すと実際にそのサイトへアクセスする。設定ファイルの変更だけで、エージェントのコードを見ても分からない通信が増える
  - 疑問：説明文の長いツールが増えるほど入力が増える。講義のツール検索（必要なツールだけを読み込む）を、このエージェントで試すと、呼び分けの精度はどう変わるか

## 宿題

- 取り組んだレベル：基礎・実装・発展のすべて（基礎 → 実装 → 発展の順）

### 基礎：get_lecture_summary を公開する

- やったこと：
  - `app/mcp_server.py` の `TODO(宿題・基礎)` の下に `server.tool()(tools.get_lecture_summary)` の 1 行を足した。`app/mcp_servers.json` と `app/mcp_agent.py` は変えていない
  - `git status` で、変更したファイルが `app/mcp_server.py` だけであることを確かめた（演習の変更は先に commit した）
  - 予測（実行前に書いた）：エージェント側を変えずに一覧が増え、「第2回では何を学びますか？」で `lecture=2` で呼ばれる
- 結果：
  - `--list-tools` に `[glossary_get_lecture_summary]`（引数 `{"lecture": {"title": "Lecture", "type": "integer"}}`）が増えた。演習で fetch と aws を足した設定のままなので、全体は 7 → 8 個
  - 「第2回では何を学びますか？」を 3 回流し、3 回とも `[tool call] glossary_get_lecture_summary({'lecture': 2})` だった。入力 5,942 tokens / モデル応答 2 回
  - `uv run pytest -q`：48 passed
- 気づき・疑問：
  - 第3回は、ツールを増やすたびにエージェント側（`agent.py`）に登録を書き足した。MCP では、エージェントが起動するたびにサーバーへツールの一覧を問い合わせるので、サーバー側の 1 行だけで済む。逆に言えば、サーバーを更新した人が、エージェントの使えるツールを変えられる。第三者のサーバーを足すときに、提供元を確かめる理由がここにある

### 実装：make_quiz を公開し、範囲外のメッセージの伝わり方を比べる

- やったこと：
  - `app/mcp_server.py` に `make_quiz` を `@server.tool()` で追加した。中身は第3回の `tools.make_quiz` を呼び、範囲外（1〜13 以外）で出る `ValueError` を受けて、次のメッセージを **return** する

    > 第99回はありません。AIE2026 は全13回なので、lecture は 1〜13 の整数で指定してください。用語集に用語がある回: 1, 2, 3, 4, 6

    `tools.make_quiz` は変えていない（`app/agent.py` では `ValueError` を `ModelRetry` として使っているため）
  - 比べるため、渡し方だけを変えた比較用のサーバーを作った（`lectures/06/homework/quiz_server.py`）。3 つの版は、名前・説明文・引数・メッセージの文面が同じで、違うのは渡し方だけ
    - `return`：提出版と同じ
    - `raise ValueError`
    - `raise ToolError`（MCP の SDK の「想定したツールの失敗」）
  - `lectures/06/homework/quiz_error_compare.py` で、版ごとに同じ質問を 3 回ずつ、版を交互に流した。記録したのは、モデルに渡った `[tool return]`・`[tool error]` の文面と回答（`homework/results/quiz_error_report.txt`）
  - 予測：`return` はメッセージが届き、モデルは呼び直さずに利用者に説明する。`raise ValueError` は、MCP の SDK がメッセージをサーバーの外に出さないので、「1〜13」が届かない
  - テストを足した（`tests/test_mcp_server.py`）。範囲外（0・14・99）が `ToolReturnPart` で戻り、再試行の指示にならないこと。わざと `return` の経路を壊すと 3 件が fail になることも確かめた
- 結果：
  1. **課題の質問「第99回のクイズを作って」では、ツールがほとんど呼ばれなかった（予測が外れた）。**

     | 説明文 | return | raise ValueError | raise ToolError |
     |---|---|---|---|
     | 提出版（範囲の一文あり） | 0/3 | 2/3 | 3/3 |
     | 範囲の一文を除いた版 | 0/3 | 0/3 | 0/3 |

     - 呼ばれなかった回は、モデルがツールを呼ばずに「第99回はない」と答えた。99 は明らかに範囲外だからで、`app.mcp_agent --trace` で流した回も呼び出しは 0 回（`runs/impl_cli_99.txt`）
     - 範囲を知らないまま答えた回では、「第1回から第10回までの構成」と誤った回数を書いたものがあった
     - 提出版で 0/3 と 3/3 に分かれたが、モデルが最初に受け取る入力は 3 つの版で同じ。3 回ずつでは、版の差ではなく揺れと見るべき
  2. **ありえそうな「第14回」では、どの版でもツールが呼ばれ、渡し方の違いがはっきり出た**（範囲の一文を除いた版、各 3 回。3 回とも同じ振る舞い）

     | 版 | モデルに渡った内容 | モデルの振る舞い |
     |---|---|---|
     | return | `[tool return]` に上のメッセージがそのまま | 応答 2 回。「全13回のため第14回は存在しません。第1〜13回から指定して」 |
     | raise ToolError | `[tool error]` に `Error executing tool make_quiz: 第14回はありません。…` ＋ `Fix the errors and try again.` | 応答 2 回。呼び直さずに、全13回と、用語がある回を案内 |
     | raise ValueError | `[tool error]` に `Error executing tool make_quiz` ＋ `Fix the errors and try again.` だけ。メッセージは届かない | 応答 3 回。理由が分からないので `get_lecture_summary(14)` を呼んで調べ、「第14回はまだ用意されていない」と、今後追加されるかのように誤って答えた |

     - 提出版の説明文（範囲あり）でも、第14回では 9 回中 8 回ツールが呼ばれた。この場合は ValueError の版も、3 回とも「全13回なので第14回は存在しない」と正しく答えた（呼ばなかった 1 回を含む）。届かなかったメッセージの代わりに、説明文の「1〜13」が手がかりになった
     - `app.mcp_agent --trace "第14回のクイズを作って"`（演習の設定のまま、提出版）：`[tool call] glossary_make_quiz({'lecture': 14})` → `[tool return] glossary_make_quiz -> 第14回はありません。…`、モデル応答 2 回
     - 正常系「第3回のクイズを作って」：`glossary_make_quiz({'lecture': 3})` で問題が返り、モデルは答え（定義）を伏せて問題だけを出した
- 気づき・疑問：
  - **`raise` するなら、例外の種類で届く内容が変わる。** MCP の Python SDK は、`ToolError` は想定した失敗としてメッセージを返す。それ以外の例外は想定外のクラッシュとして扱い、メッセージをサーバーの中に留める（内部の情報を漏らさないため。サーバーのログにはトレースバックが出ていた）。普通の `ValueError` で丁寧に書いたメッセージは、モデルに 1 文字も届かなかった
  - **メッセージが届かないと、モデルは自分で調べ、もっともらしく誤る。** ValueError の版では、別のツールで調べた「要点はまだありません」を手がかりに、「まだ用意されていない」と答えた。全13回の講座に第14回が無いことは、言えなかった
  - **return と ToolError の違いは、今回は出なかった。** ToolError には「Fix the errors and try again.」が付くが、モデルは同じ引数で呼び直さなかった。違いが出るのは、モデルが自分で直せる誤り（形式の誤りなど）だと考える。利用者の指定そのものが誤りのときは、return で「該当なし＋有効な値」を返す方が、再試行を促さない分だけ素直
  - **説明文の範囲は、呼ぶかどうかを左右する。** 改訂前の課題では、説明文に範囲を書くと呼ばれにくくなった（[old/answer.md](old/answer.md)）。今回、範囲が無い方が第99回で呼ばれなかったのは、「範囲外ならメッセージを返す」という一文が、呼んで確かめることを促した可能性がある。3 回ずつなので、確かめるには回数が足りない
  - 疑問：利用者の誤り（第99回）と、モデルの引数の誤り（`lecture="第2回"` のような型の誤り）を、同じツールの中で return と raise に分けるべきか

### 発展：Claude Code の MCP 設定を調べ、演習の設定と比べる

- やったこと：
  - 普段使っている Claude Code を選び、公式ドキュメントで MCP サーバーの設定方法を調べた
    - 調べた日付：2026-11-24
    - 参照した公式ドキュメント：https://code.claude.com/docs/en/mcp
    - 使った版：Claude Code 2.1.327
  - 調べた内容を、手元で確かめた。作業用のディレクトリで、次の 2 通りで `.mcp.json` を作り、`claude mcp list` で読み込み結果を見た（`homework/results/claude_code/`）
    - 演習の `app/mcp_servers.json` を、そのまま `.mcp.json` にした（`mcp.json.copied_as_is`）
    - `claude mcp add --scope project` の 3 回で同じサーバーを登録した（`mcp.json.from_cli_add`）
  - 確かめたのは、ファイルの形式と読み込みまで。project スコープのサーバーは、使う前に対話画面での承認が要る。承認は自分の設定を変える操作なので、行っていない。接続しての呼び出しは確かめていない
  - 逆向きに、Claude Code が書いた `.mcp.json` を演習のエージェント（`build_mcp_agent`）で読み込み、ツールの一覧を出した
- 結果（演習の `app/mcp_servers.json` との比較）：

  | 調べること | 演習（`app/mcp_servers.json`） | Claude Code |
  |---|---|---|
  | 設定を書く場所 | `app/mcp_servers.json` の 1 つ。`app/mcp_agent.py` が決まった場所から読む | スコープで場所が変わる。project は、プロジェクト直下の `.mcp.json`。local と user は `~/.claude.json`（local はその中のプロジェクトごとの欄）。手で書くほか、`claude mcp add` / `add-json` で登録できる |
  | コマンドで起動する書き方 | `"command"` と `"args"`（`"env"` も可） | 同じ `"command"`・`"args"`・`"env"` に、`"type": "stdio"` が付く。CLI では `claude mcp add <名前> -- <コマンド> <引数…>`（`--` のあとがサーバーのコマンド） |
  | URL で接続する書き方 | `"url"` だけ | `"type": "http"` と `"url"`（`"headers"` も可）。CLI では `claude mcp add --transport http <名前> <URL>`。SSE は非推奨 |
  | 有効になる範囲 | `app.mcp_agent` を実行したときだけ（このリポジトリのこのエージェント） | local（既定。自分だけ・このプロジェクトだけ）、project（`.mcp.json` を commit すれば共有）、user（自分のすべてのプロジェクト）。同じ名前があれば local → project → user の順で 1 つだけ使い、項目は混ぜない |

  - **演習の設定をそのままコピーすると、`aws` だけが読み飛ばされた。** `claude mcp list` の警告は `[aws] mcpServers.aws: Skipped — MCP server "aws" has a "url" but no "type"; add "type": "http" …`。公式ドキュメントにも、`type` の無い項目は stdio と見なすので、`url` だけの項目は設定の誤りになる、とある。glossary と fetch は読み込まれた
  - `claude mcp add` で登録すると、3 つとも `"type"` 付きで書かれた（stdio には `"env": {}` も付く）。`claude mcp list` では 3 つとも「Pending approval」になった。project スコープのサーバーは、対話画面で承認するまで使われない
  - 逆向きは読めた。Claude Code が書いた `.mcp.json`（`type` 付き）を演習のエージェントで読むと、3 サーバー・9 ツールが一覧に出た。`app/mcp_agent.py` は `url` があるかどうかで接続方法を決め、`type` は見ないため
  - ツール名の付け方も違う。演習は `glossary_search_glossary`（サーバー名＋`_`）、Claude Code は `mcp__glossary__search_glossary`（`mcp__`＋サーバー名＋`__`）
- 気づき・疑問：
  - **同じ `"mcpServers"` 形式でも、方言がある。** ルートのキーと `command`・`args` は共通で、stdio のサーバーはそのまま移せる。ところが、URL のサーバーを `type` で明示するかどうかが違い、演習の書き方は Claude Code では警告とともに無視された。「同じ形式だからコピーすれば使える」と考えると、URL のサーバーだけが黙って消える。移すときは、クライアント側の一覧（`claude mcp list`）で、全部読み込まれたかを確かめる
  - **Claude Code は、共有された設定を無条件には使わない。** `.mcp.json` は commit して共有できるが、そこに書かれたサーバーは、利用者が承認するまで起動しない。演習のエージェントは、設定ファイルにあれば何でも起動する。リポジトリを clone しただけで、知らないコマンドが動くのを防ぐ仕組みで、講義の「出所の分からないサーバーは設定に書かない」をクライアント側で強制している
  - **鍵の書き方も、クライアントの仕事になる。** Claude Code の `.mcp.json` は `${VAR}` や `${VAR:-既定値}` で環境変数を展開でき、鍵を共有ファイルに書かずに済む。演習の設定には、この仕組みが無い
  - 疑問：VS Code（`"servers"`）や Codex（TOML）など、クライアントごとに書き方が違う。同じサーバーを複数のクライアントで使うとき、設定をどこで一元管理するのがよいか
