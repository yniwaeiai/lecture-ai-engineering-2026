# 第5回 解答

## 演習

- `--list-tools` で見えたツール名と、第3回（`--mcp` なし）との違い：
  - `--mcp` なし：`search_glossary`・`get_lecture_summary`・`make_quiz`・`save_learning_log` の 4 個（第3回で関数を直接登録したもの）
  - `--mcp`（演習前）：`glossary_search_glossary` の 1 個だけ。設定ファイルのサーバー名 `glossary` が前に付く
  - 説明文と引数は、どちらも `app/tools.py` の docstring と型ヒントから作られていて、中身は同じだった。モデルから見ると、関数ツールと MCP のツールの違いは名前の接頭辞だけ
- `--mcp --trace` で見えたツール呼び出し（ツール名と引数）と、`requests` の回数：
  - 「AIE2026の講座の宿題にある「3レベル」とは何ですか？」（`gemini-3.5-flash-lite`）
    - `--mcp`：`glossary_search_glossary({'query': '3レベル'})`、`requests=2`、入力 651 トークン
    - `--mcp` なし：`search_glossary({'query': '3レベル'})`、`requests=2`、入力 1,381 トークン
  - 回答はどちらも用語集どおり（基礎・実装・発展の 3 段階で、どれか 1 つで完了）で、引数も呼び出し回数も同じ。入力トークンの差は、MCP 版はツールが 1 個、直接登録版は 4 個で、送るツールの説明文の量が違うため。経路（MCP か関数か）ではなく、渡すツールの数でトークンが決まる
- MCP サーバーに公開したツールと、その説明文：
  - `app/mcp_server.py` の TODO の場所に `server.tool()(tools.get_lecture_summary)` を足した。第3回の `make_quiz` も `server.tool()(tools.make_quiz)` で公開した。説明文は `app/tools.py` の docstring がそのまま使われる（例：`get_lecture_summary` は「指定した回（1始まりの整数）の講義の要点を返す。『第3回では何を学ぶ？』のように、回の内容や関係を聞かれたときに使う。」）
  - `save_learning_log` は公開しなかった。保存前の承認（`requires_approval=True`）は Pydantic AI のエージェント側の仕組みなので、MCP サーバーのツールにすると承認なしで書き込めてしまう
  - `--mcp --list-tools` は `glossary_search_glossary`・`glossary_get_lecture_summary`・`glossary_make_quiz` の 3 個になった。「第2回では何を学びますか？」では `glossary_get_lecture_summary({'lecture': 2})` を 1 回呼んだ（`requests=2`）。`uv run pytest -q`：23 passed
- fetch サーバーを足したときのツール呼び出し（ツール名と引数）：
  - `app/mcp_servers.json` に `"fetch": {"command": "uvx", "args": ["mcp-server-fetch"]}` を足すと、`--list-tools` に `fetch_fetch`（引数 `url`・`max_length`・`start_index`・`raw`）が増えて 4 個になった。起動は約 6 秒
  - 「https://modelcontextprotocol.io/ の冒頭を日本語で3行に要約して」：`fetch_fetch({'url': 'https://modelcontextprotocol.io/'})` を 1 回呼び（`requests=2`、入力 2,055 トークン）、「MCP は AI アプリと外部システムをつなぐオープンな標準規格」「AI のための USB-C ポートのようなもの」などの 3 行に要約した。INSTRUCTIONS は用語集を前提にしているが、URL が明示されていたので、INSTRUCTIONS に 1 行足さなくても fetch を選んだ。fetch サーバーは robots.txt を確認してから、リダイレクト先（`/docs/.../getting-started/intro`）まで実際にアクセスしていた
  - 回答の最後に「関連する回については、講座の用語集に登録されていないため記載していません」と付いた。INSTRUCTIONS の「回答の最後に、関係する回を示す」が、講座と関係の無い質問にも効いている
  - **つまずいたこと（ローカル環境）：** Codespaces ではなくローカルの Linux で実行したところ、最初は fetch が失敗した。fetch サーバーは本文の抜き出しに `readabilipy` を使い、Node があると JavaScript 版（jsdom）を初回に `npm install` して使う。このマシンの Node は v18 で、jsdom 30 の要件（Node 22 以上）を満たさず、抜き出しで例外になった。Codespaces の devcontainer は Node の LTS を入れるので、課題が想定する環境では起きないと考えられる。ローカルでは、fetch サーバーにだけ Node を見せない一時的な設定（`env` の `PATH` から Node を外す。repo には入れていない）で、Python だけの処理に切り替えて動かした。外部の MCP サーバーは、実行時に別のパッケージを取得して動くこともあるので、「何を足したか」だけでなく「何が実行されるか」も把握が要る
  - このとき、MCP のツールのエラーは `ModelRetry`（再試行の指示）としてモデルに返り、再試行の上限（1 回）を超えると `UnexpectedModelBehavior` の例外になって、`app.agent` がトレースバックを出して止まった（`main()` は `ModelHTTPError` しか捕まえていない）

## 宿題

- 取り組んだレベル：基礎・実装・発展を順に実施。再現手順は [technical-memo.md](technical-memo.md) にまとめた

### 基礎：stdio と Streamable HTTP の比較、docstring を書き換えたときの変化

- やったこと：
  - 同じ用語集サーバーを、stdio（設定 `{"command": "uv", "args": ["run", "python", "-m", "app.mcp_server"]}`）と Streamable HTTP（`uv run python -m app.mcp_server --http` で起動し、設定は `{"url": "http://127.0.0.1:8000/mcp"}`）の 2 通りでつなぎ、同じ質問をした。比較用の設定ファイルは `lectures/05/homework/` に置き、repo の `app/mcp_servers.json` は演習の形のままにした
  - 起動の仕方・プロセス・ポートは、エージェントが接続している最中のプロセスの親子関係（`ps`）と、待ち受けポート（`ss -ltnp`）で調べた
  - `search_glossary` の docstring を一時的に「講座に固有の言葉を調べるときだけ使う。RAG や LLM のような一般的な AI の用語には使わず、自分の知識で答えること。」に書き換え、`--list-tools` に出る説明文と、「RAGとは何ですか？」での呼ばれ方を比べた（比べた後に元に戻した）
- 結果：

  | 項目 | stdio | Streamable HTTP |
  |---|---|---|
  | サーバーを起動するのは | クライアント（エージェント）。接続するときに `uv run python -m app.mcp_server` を子プロセスとして起動する | 利用者が別に起動しておく（`--http`）。サーバーは独立したプロセス |
  | プロセス | エージェントの子孫に `uv run …` → `python -m app.mcp_server` が現れる | エージェントの子孫には現れない。サーバーの親はシェル |
  | ポート | 開かない（標準入出力でやり取り） | `127.0.0.1:8000` で待ち受ける |
  | サーバーが終わるとき | エージェントのプロセスが終わるとき（下の注を参照） | 止めるまで動き続ける。エージェントが終わっても待ち受けたまま |
  | 1 回の質問でのやり取り | 標準入出力のメッセージ（外からは見えない） | サーバーのログに `POST /mcp`（セッション開始・ツール一覧・呼び出し）と `DELETE /mcp`（セッション終了）が残る |
  | 「3レベル」の質問 | `glossary_search_glossary({'query': '3レベル'})`、`requests=2` | 同じ呼び出し、`requests=2`、回答も同じ |

  - 注：stdio のサーバーは、`async with agent:` を抜けて接続を閉じた後もプロセスが残っていた。予測（接続を閉じるとサーバーも終わる）と違ったのでコードを確かめると、`app/agent.py` が使う fastmcp の `StdioTransport` は `keep_alive` が既定で `True` で、同じプロセスの中で次に接続するときのために子プロセスを残す仕様だった。エージェントのプロセスが終わると、サーバーのプロセスも残らなかった
  - docstring を書き換えたとき：

    | 状態 | `--list-tools` の説明文 | 「RAGとは何ですか？」での呼び出し |
    |---|---|---|
    | 変更前（stdio） | 元の文面 | `glossary_search_glossary('RAG')` を 2 回、`requests=3`（2 回とも同じ） |
    | 変更後（stdio） | **すぐ新しい文面になる** | **呼ばない**、`requests=1`（2 回とも同じ） |
    | 変更後（HTTP、サーバーを再起動する前） | **古い文面のまま** | `RAG`・`Retrieval-Augmented Generation`・`外部知識` で 3 回検索、`requests=4` |
    | 変更後（HTTP、サーバーを再起動した後） | 新しい文面 | 呼ばない、`requests=1` |

- 気づき・疑問：
  - **stdio は「クライアントがサーバーを起動する」、HTTP は「サーバーは先に動いていて、クライアントが接続する」。** stdio はポートを開かないので、同じマシンの中で手軽かつ外から触られない。HTTP はネットワーク越しに複数のクライアントから使える代わりに、どこから接続できるか（今回は `127.0.0.1` だけ）と認証を考える必要がある
  - **HTTP では、サーバーのコードを変えても、再起動するまで反映されない。** stdio は毎回（プロセスごとに）サーバーを起動し直すので、docstring の変更がすぐ効く。HTTP のサーバーを動かしたまま docstring を直して「効かない」と悩むのは、ありそうな落とし穴だと思う。逆に言えば、HTTP なら運用中のサーバーを入れ替えるまで、クライアントに見える説明文が変わらない
  - **docstring は、MCP 越しでもツールの選び方を変える。** 説明文で「一般的な用語には使わない」と書くと、RAG の質問では検索しなくなり、`requests` が 3 から 1 に減った。INSTRUCTIONS には「用語や講座に固有のことを答える前に、必ず search_glossary で確認する」と書いたままなのに、説明文に従った。第3回の基礎（関数ツールでの比較）と同じ結果で、説明文はモデルへの指示そのものだと言える
  - 疑問：HTTP のサーバーを動かしたまま説明文を変えたいとき、MCP にはツール一覧が変わったことをクライアントに知らせる仕組み（`notifications/tools/list_changed`）があるが、Pydantic AI のクライアントはそれを受けて一覧を取り直すのか

### 実装：`make_quiz` を MCP で公開し、範囲チェックとテストを足す

- やったこと：
  - `make_quiz` は演習で MCP サーバーに公開済み（`server.tool()(...)`）。そこに引数の範囲チェックを足した
    - `app/tools.py`：AIE2026 は全13回なので、`lecture` が 1〜13 の外なら `ValueError("lecture は 1〜13 の整数で指定してください（AIE2026 は全13回）。指定された値: 99")` にした。範囲内でも用語集に用語がない回（例：第4回）は、今までどおり「用語集にありません。用語がある回: …」というふつうの結果を返す。docstring にも「lecture は 1〜13。範囲外ならエラーになる」を足した
    - `app/tools.py` は、MCP サーバー・Pydantic AI のエージェント・第3回の ADK 版から共通で使うので、どのフレームワークにも依存させず、ふつうの `ValueError` を投げるだけにした。各フレームワークへの変換は、それぞれの側の小さなラッパーで行う
      - MCP サーバー（`app/mcp_server.py`）：`ValueError` → `ToolError`
      - Pydantic AI のエージェント（`app/agent.py`、`--mcp` なし）：`ValueError` → `ModelRetry`
      - ADK 版（`lectures/03/homework/adk/aie_agent/agent.py`）：`ValueError` → 結果 `{"error": ...}`。範囲外で例外がそのまま上がり、止まるおそれがあったため
  - `--trace` に、ツールのエラーでモデルに戻る再試行の指示（`RetryPromptPart`）を `[tool retry]` として表示するようにした。それまでの `--trace` は、ツールの呼び出しは表示しても、エラーの戻りを表示していなかった
  - テスト（`uv run pytest -q`：28 passed）：
    - `tests/test_mcp_server.py`：(1) TestModel で `glossary_make_quiz` と `glossary_get_lecture_summary` が公開され、説明文に範囲（1〜13）が含まれること。(2) MCP 越しに第2回を指定すると問題が返ること（TestModel は引数を選べないので、引数を指定できる `FunctionModel` を使った）。(3) TestModel は `lecture=0` を渡すので、範囲外のエラーが再試行の指示としてモデルに戻り、その文に「1〜13」が含まれること
    - `tests/test_tools.py`：範囲外（0・14・99・-1）は `ValueError`、範囲内で用語のない第4回はメッセージを返すこと
    - `tests/test_agent.py`：範囲外で呼ぶとエラー文が再試行の指示として戻り、モデルが正しい回で呼び直せること
  - テストが効いているかの確認：MCP サーバーの `ToolError` への変換を一時的に外すと、(3) のテストだけが落ちた（元に戻すと全部通る）
  - 配布されたテスト `test_base_tools_are_registered_and_called` を、第3回に続いてもう 1 か所直した。TestModel は `make_quiz` に `lecture=0` を渡すので、結果の代わりに再試行の指示が戻る。テストの意図（呼ばれたツールの応答がモデルに戻る）は保ったまま、再試行の指示も「戻った応答」として数えるようにした
- 結果：
  - **MCP 越しのエラーの見え方（予測と違ったこと）：** 最初は `make_quiz` が `ValueError` を投げるだけにしていた。この状態でモデルに戻ったのは、「Error executing tool make_quiz」と「Fix the errors and try again.」だけで、`ValueError` に書いた「1〜13 で指定してください」は届いていなかった。MCP の Python SDK は、`ToolError` を「想定したツールの失敗」としてメッセージをそのまま返し、それ以外の例外は「想定外のクラッシュ」として、メッセージをサーバーの中に留める（内部の情報を外に漏らさないため）。MCP サーバー側で `ToolError` に変えると、「Error executing tool make_quiz: lecture は 1〜13 の整数で指定してください…」がモデルに届いた
  - 「第99回の確認問題を出して」（`--mcp --trace`、実際のモデル）：

    | 条件 | 結果 |
    |---|---|
    | 完成版（docstring に範囲あり ＋ `ToolError`）3 回 | 2 回はツールを呼ばずに「全13回なので第99回は存在しない」と答えた（`requests=1`）。1 回は `glossary_make_quiz({'lecture': 99})` → `[tool retry] … 1〜13 の整数で指定してください…` → 同じ説明（`requests=2`） |
    | docstring に範囲あり ＋ `ValueError` のまま 4 回 | 2 回はツールを呼ばずに説明。2 回は呼んで `[tool retry] Error executing tool make_quiz` だけを受けたが、docstring に範囲が書いてあるので「全13回」と正しく説明した |
    | docstring に範囲なし ＋ `ToolError` 2 回 | 呼んだ回は、エラー文から「全13回なので第99回は存在しない、第1〜13回で指定して」と答えた。もう 1 回は `get_lecture_summary(99)` で確かめ、用意されている回（1・2・3・5）を示した |
    | docstring に範囲なし ＋ `ValueError` のまま 2 回 | 呼んだ回は「Error executing tool make_quiz」しか受け取らず、「第99回は存在しないようです（現在の講座はそこまで多くありません）」と、回数を言えない曖昧な答えになった |

  - TestModel は、エラーを受けても同じ引数（`lecture=0`）で呼び直すので、再試行の上限（1 回）を超えて `UnexpectedModelBehavior` で止まる。実際のモデルは、エラーを受けて呼び直さずに利用者へ説明した
- 気づき・疑問：
  - **ツールのエラーは「誰に何を伝えるか」を決めて投げ分ける必要がある。** MCP では、ふつうの例外のメッセージはクライアントに届かない。モデルに直してほしい引数の誤りは `ToolError` で理由を伝え、内部の失敗（ファイルが読めないなど）は詳細を出さない、という使い分けが SDK の設計に組み込まれている
  - **docstring の説明とエラー文は、役割が重なる。** docstring に範囲を書くと、モデルは 3 回中 2 回、呼ぶ前に誤りに気づいて呼ばなかった（無駄な呼び出しが減る）。エラー文は、それでも呼んでしまったときの最後の手がかりになる。docstring に範囲がない場合は、エラー文が届くかどうかで、答えの正確さがはっきり変わった
  - **同じツール関数でも、フレームワークごとにエラーの返し方が違う。** Pydantic AI は `ModelRetry`、MCP は `ToolError`、ADK は結果の辞書。ツール本体はふつうの `ValueError` にして、変換は各フレームワークの側の薄いラッパーで行うと、ツール本体を共有したまま、どこから使ってもエラー文がモデルに届く
  - **`--trace` に出ないものは、無かったことにされやすい。** 元の `print_trace` はエラーの戻りを表示しないので、エラー文が届いていないことに気づけなかった。観察の道具が何を表示しないかも、確かめる必要がある
  - 疑問：再試行の上限（既定 1 回）は、範囲外のように「何度やっても直らない」誤りには十分だが、モデルが引数を直せる誤りには少ないかもしれない。ツールごとに `max_retries` を変えると、どう変わるか

### 発展

（実施中）
