# 第3回 解答

## 演習

- 第1回（素のLLM）とエージェントの回答の違い：
  - 質問「AIE2026の講座で使う「lecNN-start タグ」とは何ですか？」（モデルはどちらも `gemini-3.5-flash-lite`）
  - `app.ask`（素の LLM）：「講義資料やソースコードの中で、特定のセクションの開始位置を指定するための目印」と、もっともらしい一般論で答えた。講座 repo の Git タグであること、前の回が終わっていなくてもそこからブランチを作れることには触れず、内容は誤り。講座に固有のことは知らないので、推測で埋めている
  - `app.agent`：`search_glossary` で用語集を引き、「各回の演習を開始する時点のコードに付けられている Git タグ（例: `lec03-start`）。前の回が終わっていなくても、このタグからブランチを作れば演習を始められる」と、用語集の定義どおりに答えた。INSTRUCTIONS の指示どおり、最後に「関係する回：第1回」が付いた
- `--trace` で見えたツール呼び出し（ツール名と引数）：
  - 「lecNN-start タグ」の質問：`search_glossary({'query': 'lecNN-start タグ'})` を 1 回
  - 「LoRAとQLoRAの違いは？」：`search_glossary({'query': 'LoRA'})` と `search_glossary({'query': 'QLoRA'})`。2 つを 1 回のモデル応答の中で並べて呼んだ（並列のツール呼び出し）。比較の質問を、モデル自身が 2 つの検索に分けている
- 1つの質問での LLM 呼び出し回数（`requests`）：
  - どちらも `requests=2`（1 回目：ツール呼び出しを返す → ツールを実行 → 2 回目：結果を見て回答）。LoRA / QLoRA は `tool_calls=2` だが、並列に呼んだので `requests` は増えなかった
  - 入力トークンは 783（lecNN-start）と 1196（LoRA / QLoRA）。2 回目の呼び出しには、1 回目の会話とツールの結果が全部入るので、素の LLM の 1 回の呼び出しより入力が多い
  - 追加した `make_quiz` では、「LoRAの回の復習クイズがほしい」と回の番号を言わずに頼むと、`search_glossary('LoRA')` で第2回だと調べてから `make_quiz({'lecture': 2})` を呼び、`requests=3`・`tool_calls=2` になった。ツールの結果を見て次のツールを決める、というループがそのまま見えた
- 追加したツールと、docstring に書いた説明：
  - `make_quiz(lecture: int) -> str`（`app/tools.py`）：指定した回の用語から 1 つをランダムに選び、`{"lecture", "question": "「〇〇」の意味は？", "answer": 用語集の定義}` の JSON を返す。用語が無い回には、用語がある回の一覧を返す。`app/agent.py` の TODO の場所で `agent.tool_plain(tools.make_quiz)` として登録した
  - docstring：「指定した回（1始まりの整数）の用語から1つを選び、確認問題と答えを返す。『第2回の確認問題を出して』『LoRAの回の復習クイズがほしい』のように、学習者が理解度を確かめる問題を求めたときに使う。問題だけを先に見せ、answer（用語集の定義）は学習者が答えたあとに示すこと。」
    - 「いつ使うか」は利用者の言い方の例で示した。「答えを先に見せない」は、ツールの結果をどう使うかの指示として書いた
  - 「第2回の内容から確認問題を1問出して」で 2 回試すと、2 回とも `make_quiz({'lecture': 2})` を 1 回呼び（`requests=2`）、問題だけを出して答えは伏せた。出た用語は「Hugging Face Hub」と「エポック」で、毎回変わる
  - ただし、答えを伏せたのが docstring の「問題だけを先に見せ」の効果かどうかは、この演習だけではわからない。宿題の基礎で、INSTRUCTIONS と docstring のどちらからも伏せる指示を消して試すと、それでも答えを伏せた（V4）。モデルがもともと、クイズでは答えを伏せる振る舞いをしていると考えられる
  - テスト（`uv run pytest -q`：14 passed）：
    - `tests/test_tools.py`：第2回の用語から選ばれ、answer がその用語の定義と一致すること（ランダムなので 20 回試す）。用語が無い回への応答
    - `tests/test_agent.py`：TestModel で `make_quiz` がモデルに渡され、呼ばれて結果が戻ること
  - 気づき：`app.agent` は 1 回の質問で終わるので、学習者が答えを返しても続きの会話にならず、答え合わせができない。答え合わせまでするには、第1回の対話モードのように会話履歴（`message_history`）を引き継ぐ必要がある

## 宿題

- 取り組んだレベル：基礎・実装・発展（a：ADK）を順に実施。再現手順は [technical-memo.md](technical-memo.md) にまとめた

### 基礎：INSTRUCTIONS とツールの docstring を書き換えて比べる

- やったこと：
  - `app/agent.py` と同じツール関数・同じモデル（`gemini-3.5-flash-lite`）で、INSTRUCTIONS と docstring（ツールの説明文）だけを差し替えた 6 つの版を作り、同じ質問を各 2 回投げて、ツール呼び出し・`requests`・入力トークン・回答を記録した。ファイルを書き換えて `--trace` を何度も実行する代わりに、比較スクリプト（`lectures/03/homework/basic_compare.py`）でまとめて実行した。差し替えた箇所以外が元のエージェントと同じことは、TestModel でモデルに渡るツール定義を比べて確かめた
  - 版：

    | 版 | INSTRUCTIONS | docstring |
    |---|---|---|
    | V0 | 元のまま | 元のまま（make_quiz は演習で書いたもの） |
    | V1 | 役割の 1 行だけ（ツールの使い方の指示を全部消す） | 元のまま |
    | V2 | 元のまま | `search_glossary` を「講座に固有の言葉を調べるときだけ使う。LoRA や LLM のような一般的な AI 用語には使わず、自分の知識で答える」に変更 |
    | V3 | 元のまま | `make_quiz` から「問題だけを先に見せ、answer は学習者が答えたあとに示す」を削除 |
    | V4 | 役割の 1 行だけ | V3 と同じ（V3 の結果を切り分けるために追加） |
    | V5 | 役割の 1 行だけ | V2 と同じ（V2 の結果を切り分けるために追加） |

  - 質問：Q1「LoRAとQLoRAの違いは？」、Q2「第3回では何を学ぶ？」、Q3「RAGとは何ですか？」（用語集の見出しには無いが、「ファインチューニング」の定義文に出てくる）、Q4「第2回の内容から確認問題を1問出して」、Q5「Pythonでリストを逆順にするには？」（講座と関係の無い質問）
- 結果：

  | 質問 | V0（元） | V1（指示を最小に） | V2（検索の説明を限定） | V5（指示を最小 ＋ 検索の説明を限定） |
  |---|---|---|---|---|
  | Q1 LoRA/QLoRA | 検索 LoRA・QLoRA（req 2） | 同左（req 2） | 同左（req 2） | **呼ばない**（req 1） |
  | Q2 第3回 | `get_lecture_summary(3)`（req 2） | 同左 | 同左 | – |
  | Q3 RAG | 検索 RAG を 2 回続けて（req 3） | 検索 RAG を 2 回、または RAG・Retrieval-Augmented Generation・検索拡張生成の 3 語（req 3〜4） | **呼ばない**（req 1） | **呼ばない**（req 1） |
  | Q4 クイズ | `make_quiz(2)`、答えは伏せる | 同左 | 同左 | – |
  | Q5 Python | **検索「リスト」**（req 2） | 呼ばない（req 1） | 呼ばない（req 1） | 呼ばない（req 1） |

  - V3・V4（`make_quiz` から「答えを伏せる」指示を削除）：どちらも 2 回とも `make_quiz(2)` を呼び、**答えを伏せたまま**問題だけを出した
  - 入力トークン（1 つの質問の合計）：ツールを使わなければ 346〜469、使うと 734〜1,498、RAG で検索を繰り返すと 1,437〜1,936。INSTRUCTIONS を最小にすると、同じ質問で約 200 減った（例：Q1 は V0 の 1,454 に対し V1 は 1,252）
  - 回答の最後の「関係する回：第N回」は、V0・V2 ではほとんどの回答に付いたが、V1 では一度も付かなかった
  - 同じ版・同じ質問の 2 回は、ツール呼び出しがほぼ同じだった（違ったのは V1 の Q3 だけ）
- 気づき・疑問：
  - **INSTRUCTIONS の「必ず」は強い。** V0 では、講座と関係の無い Python の質問でも `search_glossary('リスト')` を呼び、「用語集には「リスト」の定義はありませんでしたが…」と前置きしてから答えた。1 回分のリクエストと、約 470 の入力トークンが無駄になる（INSTRUCTIONS が同じで検索しなかった V2 の 469 に対し、V0 は 938）。V1 で指示を消すと呼ばなくなった
  - **INSTRUCTIONS と docstring が食い違うと、INSTRUCTIONS が勝つことがある。** V2 では、docstring で「LoRA のような一般的な用語には使わない」と書いたのに、Q1 では LoRA・QLoRA を検索した（INSTRUCTIONS の「用語を答える前に、必ず search_glossary で確認する」に従った）。V5 で INSTRUCTIONS の指示を消すと、docstring どおり検索しなくなった。一方、V2 の Q3（RAG）・Q5 では docstring に従って検索しなかったので、どちらが勝つかは質問によって変わった。説明文と指示は矛盾しないように書く必要がある
  - **ツールの説明文だけでも、モデルはツールを使う。** V1 は INSTRUCTIONS からツールの指示を全部消したが、Q1・Q2・Q4 では V0 と同じツールを呼んだ。docstring の「いつ使うか」が、ツールを選ぶ手がかりとして十分に働いている
  - **用語集に無い語の扱いは不安定。** Q3（RAG）は、検索が「ファインチューニング」の定義の中の一致を返す。V0 では同じ検索をもう一度繰り返し（req 3）、V1 では別名で検索し直した（req 4）。回答は「用語集には登録されていない」と断ったうえで一般知識で説明しており、INSTRUCTIONS の「推測で断定せず『用語集にはない』と伝える」をおおむね守った。ただ、同じ検索を繰り返すのは無駄で、「見つからないときは別名で 1 回だけ探す」のような指示があるとよい
  - **予測が外れたこと：** `make_quiz` の docstring から「答えを伏せる」を消せば答えも出すと予測したが、V3 でも V4（INSTRUCTIONS の「宿題の答えは書かない」も無い版）でも答えを伏せた。演習で答えを伏せたのは docstring の効果ではなく、モデルがもともとクイズでは答えを伏せていたためと考えられる。docstring に書いたことが効いたかどうかは、その一文を消した版と比べないとわからない
  - 疑問：Q3 で同じ引数の検索を繰り返したのは、結果が質問の語と合わなかったから再確認したのか。ツールの結果に「見出しとしては見つからず、定義文の中で一致した」と明示すれば、繰り返さなくなるか

### 実装：`save_learning_log` ツール（保存前に利用者の確認を挟む）

- やったこと：
  - `app/tools.py` に `save_learning_log(title: str, content: str, lecture: int | None = None) -> str` を追加した。`learning_log/YYYY-MM-DD_HHMMSS_<見出し>.md` に、見出し・日時・関係する回・本文を Markdown で書き、保存したファイル名を返す。`learning_log/` は `.gitignore` 済みで、保存先はモジュール変数 `LEARNING_LOG_DIR` にしてテストで差し替えられるようにした。見出しの `/` や `..` などはファイル名から取り除き、`learning_log/` の外には書き出さない
  - docstring：「学習の記録（学んだこと・疑問・次にやること）を learning_log/ に Markdown で保存する。『今日の学びを記録して』『この内容をメモに残して』のように、学習者が記録を頼んだときだけ使う。…保存の前に利用者の確認が入るので、承認されなかったときは保存されなかったことを伝える。」
  - `app/agent.py`：
    - `agent.tool_plain(tools.save_learning_log, requires_approval=True)` で登録した
    - エージェントの `output_type` を `[str, DeferredToolRequests]` にした。承認が必要なツールが呼ばれると、ツールは実行されず、承認待ちの呼び出し（`DeferredToolRequests`）を出力として返して止まる
    - `ask_approvals()`：承認待ちの呼び出しのツール名と引数を表示し、`y/N` で答えてもらう。`y` なら `True`、それ以外は `ToolDenied("利用者が実行を許可しませんでした。")` を `DeferredToolResults` に入れる
    - `run_with_approval()`：止まったら利用者に確認し、`message_history` と `deferred_tool_results` を渡して続きを実行する。最終回答（`str`）が出るまで繰り返す。`main()` はこれを使う
  - テスト（TestModel、API キー不要。`uv run pytest -q`：18 passed）：
    - 承認すると保存され、ツールの結果に「保存しました」が戻ること
    - 拒否すると何も保存されず、会話は回答で終わること
    - 承認待ちで止まった時点では、まだ保存されていないこと
    - 止まる前と再開後の使用量が合算されること（`requests == 2`）
    - ツール単体で、見出しに `/../` があっても保存先の外に書かないこと
  - 既存のテスト `test_base_tools_are_registered_and_called` の修正：TestModel は登録された全ツールを呼ぶので、`save_learning_log` は承認待ちで止まり、結果（`ToolReturnPart`）が戻らない。そのため「呼び出しの数 ＝ 結果の数」の判定が 4 対 3 で落ちた。テストの意図（呼ばれたツールの結果がモデルに戻る）は保ったまま、承認待ちの呼び出しを差し引いて比べるように直した
  - テストが本当に承認の仕組みを確かめているかを、わざと `requires_approval=False` にして確認した。追加したテストが 2 件落ちた（元に戻すと全部通る）
- 結果（実際のモデル `gemini-3.5-flash-lite`）：
  - 「今日はLoRAとQLoRAの違いを学んだ。…学習ログに保存して」→ `[承認待ち] save_learning_log` で止まり、見出しと本文が表示された。`y` で保存され、「学習ログを保存しました！」と答えた
  - 「第3回でツールの説明文が大事だとわかった。記録しておいて」→ 承認待ちで `n` → 保存されず、「利用者の許可が得られなかったためキャンセルされました」と答えた
  - 「PEFTとは？」（記録を頼まない質問）→ `search_glossary` だけで、`save_learning_log` は呼ばなかった
- 気づき・疑問：
  - **保存の引数は、検索結果を見る前に決まることがある。** 最初の例では、`search_glossary('LoRA')`・`search_glossary('QLoRA')`・`save_learning_log(...)` の 3 つを 1 回の応答で並列に呼んだため、検索結果（第2回）を見ないまま `lecture: None` で保存した。別の言い方（「第2回でLoRAのランクrは…」）では、検索してから保存する順に呼び、`lecture: 2` が入った。承認画面で引数を見せるのは、こうした抜けや誤りを人が見つけるためにも役立つ
  - **自分のコードのバグを 1 つ直した。** 最初の版では、`--trace` の `[usage]` が `requests=1` と表示された。承認待ちで止まるまでと、再開後の 2 回の実行があるのに、再開後の使用量しか表示していなかった。`run_sync(..., usage=result.usage)` で前の実行の使用量を引き継ぐように直すと、`requests=3` と正しく表示された（テストも追加）
  - 拒否は `ToolDenied` のメッセージとしてモデルに返るので、モデルは「保存されなかった」ことを知ったうえで会話を続けられる。単に例外で止めるより、利用者への説明が自然になる
  - 疑問：承認画面で「内容を直してから保存する」ができると便利。`DeferredToolResults` で、引数を書き換えて承認できるか

### 発展（a）：同じエージェントを ADK で作り直す

- やったこと：
  - `app/agent.py` の学習支援エージェントを、Google ADK（`google-adk` 2.13.0）で作り直した（`lectures/03/homework/adk/aie_agent/agent.py`）。ツール関数は `app/tools.py` をそのまま使い、INSTRUCTIONS も同じ文面にして、フレームワークだけを変えた。モデルも同じ `gemini-3.5-flash-lite`。ADK は repo の `uv.lock` に入っていないので、repo の外に別の venv を作って入れた（`uv.lock` は変えていない）
  - INSTRUCTIONS は、`app/agent.py` を import すると Pydantic AI が必要になるので、文字列を複製した。複製が元と一致することは、比較スクリプトが毎回確かめる
  - 演習と同じ質問と、学習ログの保存（承認・拒否）を ADK 版にプログラムから投げ、イベントの流れを記録した（`lectures/03/homework/adk/adk_compare.py`）
  - `adk web` を起動し、開発 UI が使う API（セッション・イベント・トレース・グラフ）で、画面に何が出るかを確かめた。ブラウザで画面を開こうとしたが、ブラウザが別のマシンで動いていて、このマシンの `127.0.0.1` に届かなかった。そのため、画面そのものは見ていない
- 結果：
  - 書き方の比較：

    | 項目 | Pydantic AI（`app/agent.py`） | ADK（`aie_agent/agent.py`） |
    |---|---|---|
    | エージェントの定義 | `Agent(instructions=...)` を作り、`agent.tool_plain(関数)` で 1 つずつ登録 | `Agent(name=, model=, instruction=, description=, tools=[関数, ...])` にまとめて渡す |
    | モデル | 実行時に `run_sync(..., model=...)` で渡す（テストでは TestModel に差し替える） | 定義時に `model="gemini-3.5-flash-lite"` と文字列で書く。API キーは google-genai が `GEMINI_API_KEY` から自動で読む |
    | ツールの説明文 | 関数の docstring と型ヒントから作る | 同じ（`lecture: int \| None` も同じように `anyOf [integer, null]` になった） |
    | 実行 | `agent.run_sync(質問)` が最終結果を返す | `Runner` がセッションを持ち、`run_async` が途中経過を `Event` として 1 つずつ流す |
    | 保存前の確認 | `requires_approval=True` で登録し、`output_type` に `DeferredToolRequests` を足す。止まったら呼び出し側で確認し、`DeferredToolResults` を渡して再実行するループを自分で書く | `FunctionTool(関数, require_confirmation=True)` と書くだけ。ADK が `adk_request_confirmation` という関数呼び出しを出して止まり、利用者がそれに `{"confirmed": true/false}` を関数の応答として返すと続きを実行する。`adk web` ではこの確認を UI が扱う |
    | 開発時に中身を見る方法 | `--trace` で自分で表示する（`result.all_messages()` を読む） | `adk web` の UI。イベントの一覧、OpenTelemetry のトレース、エージェントとツールのグラフが最初から見られる |
    | テスト | TestModel で API を呼ばずに配線を確かめられる | 今回は試していない（ADK にも `adk eval` などの評価の仕組みがある） |

  - 同じ質問への振る舞い：

    | 質問 | Pydantic AI | ADK |
    |---|---|---|
    | lecNN-start タグとは | `search_glossary('lecNN-start タグ')`、2 回、入力 1,381 | 同じツール呼び出し、2 回、入力 1,635 |
    | LoRA と QLoRA の違い | `search_glossary` を LoRA・QLoRA で並列に、2 回、1,794 | 同じ、2 回、2,046 |
    | 第2回の確認問題 | `make_quiz(2)`、答えを伏せる、2 回、1,323 | 同じ、2 回、1,578 |
    | 学習ログを保存（承認） | `search_glossary('LoRA')` → 承認待ちで止まる → `y` → 保存（3 回） | `adk_request_confirmation` で止まる → `confirmed: true` → 保存（2 回） |
    | 学習ログを保存（拒否） | `ToolDenied` → 保存せず「キャンセルされました」 | `This tool call is rejected.` → 保存せず「保存されませんでした」 |

    回数は LLM の呼び出し回数、入力はその合計の入力トークン。どちらもツールが 4 つ登録された状態で測った
  - `adk web` で見られる情報（API で確認）：
    - 「LoRAとQLoRAの違いは？」の 1 回の質問は、3 つのイベント（2 つの関数呼び出しを含むモデルの応答 → 2 つのツールの結果 → 最終回答）になった。各イベントには id・author・使用量・長時間ツールの id などが付く
    - トレースは `invoke_workflow` › `invoke_agent` › `generate_content` ／ `execute_tool` の階層のスパン（10 個）で、ツールの説明文や呼び出し id も属性として残る
    - グラフは、エージェント（🤖 aie_agent）から 4 つのツール（🔧）へ線を引いた図
  - `adk web` は、エージェントのフォルダに `.adk/session.db`（会話を保存する SQLite）を作る。repo に入らないよう `.gitignore` に `.adk/` を足した
- 気づき・疑問：
  - **同じモデル・同じ指示・同じ説明文なら、フレームワークを変えてもツールの選び方はほぼ変わらなかった。** 質問に答える 3 つの例では、呼んだツールと引数、LLM の呼び出し回数が一致した。学習ログの保存（承認）では、同じ質問に Pydantic AI は `search_glossary('LoRA')` で回を確かめてから保存し（3 回）、ADK は保存だけをした（2 回）。保存の内容はどちらも第2回で同じだった。この違いは 1 回ずつの実行なので、フレームワークの差というより、実行ごとの揺れの範囲と考える。振る舞いを決めているのは主にモデルと文面で、フレームワークはそれを運ぶ部分だと言える
  - **入力トークンは ADK の方が 1 回の呼び出しあたり約 125 多い。** ADK は、システム指示の最後に「You are an agent. Your internal name is "aie_agent". The description about you is …」を自動で足す。ほかに、ツールの引数のスキーマに `title` などの項目が付き、ツールの結果を `{'result': ...}` で包んでいた
  - **比べ方の誤りに気づいて直した。** 最初、ADK の 1,635 を演習のときの Pydantic AI の 783 と比べて「約 2 倍」だと思った。しかし 783 は、ツールが 2 つしか登録されていなかったときの値だった。ツールを 4 つにした今の Pydantic AI で測り直すと 1,381 で、差は約 250 だった。この測り直しから、**ツールを 2 つ足すだけで、1 回の呼び出しあたり約 300 トークン増える**こともわかった。ツールの説明文は、使われない回にも毎回送られる
  - **確認（Human-in-the-loop）は ADK の方が簡単に書ける。** Pydantic AI では、止まる → 確認する → 結果を渡して再実行する、を呼び出し側で書く必要があった（実装レベルではここで使用量の合算を忘れるバグも入れた）。ADK は `require_confirmation=True` だけで、UI も確認を扱う。その代わり、確認の要求が `adk_request_confirmation` という特別な関数呼び出しとして会話に入り、ツールの結果にも「This tool call requires confirmation」という仮の応答が残る。何が起きているかは、イベントを読まないとわかりにくい
  - **見え方の違い。** Pydantic AI は最小限で、何を見るかを自分で決めて書く（`print_trace`）。ADK は最初からイベント・トレース・グラフを UI で見せ、セッションも保存する。学習や開発の初期には ADK の UI が便利だが、何が送られているかを正確に知るには、どちらでも、モデルに渡る実際のリクエストを見る必要があった（ADK では `before_model_callback` で、システム指示に自動で足された文を見つけた）
  - 疑問：`adk web` の画面は、ブラウザが別のマシンにあるため見られなかった。SSH のポートフォワード（`ssh -L 8765:127.0.0.1:8765`）で開けば、画面での確認ボタンの見え方まで比べられる
