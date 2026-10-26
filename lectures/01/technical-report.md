# 第1回 技術解説レポート：トークン数表示・会話履歴・回答比較

このレポートでは、第1回の演習で `app/ask.py` に加えた技術的な変更と、宿題の基礎で行った temperature の比較を、実際のコードに沿って説明します。会話履歴を保って続けて質問できるようにした実装課題についても解説します。

## 1. 変更の目的

LLM に質問を送ると、モデルは回答だけでなく、その呼び出しでどれだけの文章を処理したかという使用量情報も返します。そこで、質問（入力）と回答（出力）のトークン数をターミナルに表示できるようにしました。

トークンは、モデルが文章を処理するときに使う単位です。単語や文字と必ずしも一対一には対応しません。日本語では、文章を複数の小さな単位に分けて数えることがあります。そのため「7トークン」は「7文字」という意味ではありません。

## 2. トークン数を取得して表示する流れ

`app/ask.py` は Google GenAI SDK のクライアントを作り、Chat セッション経由で質問を Gemini API に送ります。現在の実装では、`ask` 関数と対話ループの両方がこの共通処理を利用します。

```python
chat = client.chats.create(model=MODEL)
response = chat.send_message(question)
```

`response` は SDK の応答オブジェクトです。`usage_metadata` に使用量情報が含まれる場合、入力と出力の数はそれぞれ次のフィールドから読み取ります。

| フィールド | 意味 |
|---|---|
| `prompt_token_count` | モデルに送った質問など、入力側のトークン数 |
| `candidates_token_count` | モデルが生成した回答側のトークン数 |

実装では、まず `usage_metadata` を取り出し、各フィールドの値を読みます。

```python
usage = response.usage_metadata
input_tokens = usage.prompt_token_count if usage is not None else None
output_tokens = usage.candidates_token_count if usage is not None else None
```

API 応答に使用量情報が含まれない場合もあります。`usage` が `None` のときに属性を読もうとするとエラーになるため、先に存在を確認しています。また、メタデータがあっても各トークン数が未設定の場合に備え、値が `None` なら「不明」と表示します。

```python
input_display = input_tokens if input_tokens is not None else "不明"
output_display = output_tokens if output_tokens is not None else "不明"
print(f"[トークン] 入力: {input_display}, 出力: {output_display}")
```

これにより、通常は例えば次のように表示されます。

```text
[トークン] 入力: 7, 出力: 296
```

メタデータ自体が返らなかった場合は、次の表示になります。

```text
[トークン] 入力: 不明, 出力: 不明
```

トークン数の表示は回答本文の出力より前に行います。`_ask_in_chat` は従来どおり `response.text`（回答本文）を返し、コマンドライン側がその本文を表示します。つまり、トークン数を追加しても、呼び出し元が受け取る回答の形式は変わりません。

## 3. テストで確認したこと

追加した `tests/test_ask.py` は、実際の Gemini API を呼ばずに表示の動作を確認します。テストでは API クライアントを簡単な偽物に置き換え、既知のトークン数を含む応答を返すようにしています。

確認するケースは2つです。

1. 入力が `12`、出力が `7` の応答なら、`[トークン] 入力: 12, 出力: 7` と表示され、回答本文も返る。
2. 使用量メタデータがない応答なら、入力・出力とも「不明」と表示され、エラーにならない。

このようなテストにより、ネットワーク接続や API キーを使わず、表示の形式とメタデータ未取得時の処理を繰り返し確認できます。テストを実行するには、リポジトリのルートで次を実行します。

```bash
uv run pytest -q tests/test_ask.py
```

## 4. 基礎課題：temperature を変えた比較

宿題では、質問を「LoRAとは何ですか？」に固定し、モデル `gemini-3.5-flash-lite` も固定して、temperature を `0.0`、`0.7`、`1.2` に変えて1回ずつ実行しました。これは**ソースコードの `app/ask.py` に temperature の設定機能を追加したという意味ではありません**。比較のための実行時設定を変えて、同じ質問への応答を観察したものです。

Gemini SDK では、生成時の設定を `config` 引数で渡せます。今回の比較では、概念的には次のように設定しました。

```python
from google.genai import types

response = client.models.generate_content(
    model=MODEL,
    contents="LoRAとは何ですか？",
    config=types.GenerateContentConfig(
        temperature=0.7,
        max_output_tokens=300,
    ),
)
```

`temperature` は、モデルが次の語句を選ぶときのばらつきに関わる設定です。一般に低い値では比較的決まった候補を選びやすく、高い値では表現や展開に違いが出やすくなります。ただし、値を変えれば必ず大きく違う回答になる、という保証ではありません。モデルや質問、実行時の条件にも左右されるため、今回のように実際の回答を比べます。

`max_output_tokens=300` は、生成する回答の長さに上限を設ける設定です。今回の3回は、いずれも出力が296トークンで終わり、回答の最後まで生成されていませんでした。したがって、これは回答が内容を説明し終えたことを意味せず、設定した上限に近づいて途中で止まった可能性を考慮して比較する必要があります。

実行結果では、temperature が異なっても、3回とも LoRA を「Low-Rank Adaptation（低ランク適応）」と説明し、元のモデルを固定し、追加した小さなパラメータを学習するという中心的な説明は共通していました。一方で、たとえ（付箋・メモ）、説明の順番、背景や細部には違いがありました。

この比較から分かるのは、temperature を変えると回答の表現や展開が変わることがある一方、必ずしも回答の主題まで変わるわけではないということです。また、比較では質問・モデル・出力上限などをなるべく固定し、変えた条件を記録すると、何が違いに影響したかを考えやすくなります。

## 5. 変更したファイル

- [`app/ask.py`](../../app/ask.py)：入力・出力トークン数の表示と、会話履歴を保つ対話型の質問ループを実装。
- [`tests/test_ask.py`](../../tests/test_ask.py)：トークン数表示、使用量情報がない場合の表示、複数ターンの質問と終了操作をテスト。
- [`lectures/01/answer.md`](./answer.md)：基礎課題と実装課題の条件、結果、気づきを記録。

## 6. 実装課題：会話履歴を保った質問

### 1回ずつ送る呼び出しと会話セッションの違い

1回だけの質問なら、その質問をモデルに送って回答を受け取れば完了です。しかし、次の質問で「さっきの説明を短くして」のように尋ねるには、モデル側に前のやり取りも伝える必要があります。別々の単発リクエストとして質問を送るだけでは、2回目のリクエストは1回目の質問や回答を自動では知りません。

Google GenAI SDK には、このやり取りを管理する Chat セッションがあります。今回の実装では、最初に Chat を作ります。

```python
client = genai.Client(api_key=get_api_key())
chat = client.chats.create(model=MODEL)
```

続く質問は、同じ `chat` に送ります。

```python
response = chat.send_message(question)
```

SDK の `Chat.send_message` は、現在までの会話履歴に新しい質問を加えてモデルへ送ります。回答を受け取った後も履歴は Chat オブジェクトに記録されるため、同じオブジェクトを再利用すると次のターンでも前のやり取りを踏まえられます。大切なのは、質問ごとに新しい Chat を作るのではなく、会話の間は同じ Chat を使い続けることです。

### コマンドラインでの会話の流れ

`main` は起動時に Chat を1つ作成します。コマンドライン引数に質問があればそれを最初の質問として使い、質問が省略された場合は既定の質問から始めます。回答を表示した後は、追加の質問を入力できる状態になります。

```text
[質問] LoRAとは何ですか？

（モデルの回答）

続けて質問できます（終了するには /exit）: さっきの説明を短くしてください
```

`/exit`、`exit`、`quit` のいずれかを入力すると終了します。入力の終わり（EOF）になった場合も、ループを抜けてプログラムを終了します。空の入力はモデルへ送らず、次の入力を待ちます。

トークン数表示は会話中も各応答で維持されます。Chat の各ターンでは、それまでの履歴も含めてモデルに送るため、入力トークン数は**直前に入力した質問だけの数ではなく、そのターンでモデルに渡された会話全体の入力量**を反映します。会話が長くなるほど、入力トークン数が増えることがあります。

### 既存の `ask` 関数との関係

`ask(question)` は引き続き質問を1回だけ処理し、回答文字列を返します。内部では Chat を作り、共通の `_ask_in_chat` 関数に質問を渡します。対話型の `main` は同じ `_ask_in_chat` に同じ Chat を繰り返し渡します。これにより、回答本文を返す既存の関数の使い方を保ちつつ、コマンドラインでは会話を続けられます。

### テストで確認したこと

会話のテストでは、本物の API の代わりに、送られた質問を記録する偽の Chat を使います。最初の質問を送った後に続きの質問を送ると、偽の2回目の回答が「前の質問」を含むこと、また `/exit` で入力ループが終了することを確かめます。実際の API キーや通信を使わず、アプリケーションが同じ Chat セッションを使う配線をテストしています。

全テストは次のコマンドで実行できます。

```bash
uv run pytest -q
```

今回のテストで確認できるのは、アプリ側が同じ Chat オブジェクトへ順番に質問を送ることです。実際のモデルが履歴をどう使って回答するかは API の統合テストで確認する範囲であり、ここでは無料枠や API キーを消費しないよう実通信を行っていません。

## 7. 発展課題：応答時間とトークン数の計測

### 応答時間の計測方法

モデルに質問を送ってから回答を受け取るまでの時間を知るため、`app/ask.py` では `time.perf_counter()` を使います。この関数は、処理にかかった時間を測るのに適した単調増加の時計です。

```python
started_at = time.perf_counter()
response = chat.send_message(question)
elapsed_seconds = time.perf_counter() - started_at
```

送信直前の時刻と、応答が戻った直後の時刻の差を秒数にします。システム時刻の変更などで時刻が前後しても測定が狂わないよう、日時を返す時計ではなく経過時間測定用の時計を使っています。コマンドラインには小数点以下2桁で表示します。

```text
[応答時間] 34.49秒
```

この時間には、API通信中のネットワーク待ちやモデル側の処理・混雑も含まれます。一方、Chat の作成、モデルの初期化、利用者が次の質問を入力する待ち時間は計測していません。したがって、表示値は「質問を送ってからその応答を受け取るまで」の時間であり、モデル単体の計算時間ではありません。

### 実測結果

比較では、temperature を `0.2`、出力上限を120トークンにそろえ、「LoRAとは何ですか？一文で説明してください。」と「RAGとは何ですか？一文で説明してください。」を使いました。各条件を1回だけ実行した結果です。

| モデル | 質問 | 応答時間 | 入力トークン | 出力トークン | 結果 |
|---|---|---:|---:|---:|---|
| `gemini-3.5-flash-lite` | LoRA | 34.49秒 | 13 | 58 | 説明が返った |
| `gemini-3.5-flash-lite` | RAG | 26.91秒 | 13 | 42 | 説明が返った |
| `gemini-3.8-flash` | LoRA | 49.42秒 | 13 | 3 | 回答が `**LoRA` で途切れた |

同じモデルでも質問により応答時間と出力トークン数が異なりました。入力トークン数は今回の二つの質問で同じでしたが、回答の長さやサーバーの状態は同じとは限りません。`gemini-3.8-flash` の出力は途中で途切れているので、応答時間とトークン数は記録できますが、回答品質の比較には適していません。

### モデルエラーと無料枠のレート制限

別モデルも試したところ、`gemini-3.1-flash-lite` は503（サーバーが混雑中）、`gemini-2.5-flash` は404（新規利用者には提供終了）を返しました。これらは429のレート制限エラーとは別の問題です。今回の少数の実行では429は発生していません。

無料枠には、一定時間あたりのリクエスト数や1日あたりの利用量などに上限があります。短時間に多くのモデルや質問を試すと上限に達して429になる可能性があります。また、上限内でもサービスが混雑して503になることがあります。つまり、**429は利用枠・頻度の制限、503は一時的なサービス混雑**として区別し、API が示したエラーに応じて待つ・モデルを変えるなど対応します。404の場合は利用回数を増やしても直らないため、利用可能なモデル名を確認します。

### 結果を比べるときの注意点

今回の各条件は1回ずつの測定なので、これだけでどのモデルが常に速いとは言えません。応答時間はネットワーク、サーバーの混雑、質問内容、回答の長さなどで変わります。より公平に比較するには、同じ質問・同じ生成設定で複数回測り、平均や中央値を比べるとよいでしょう。無料枠を使うため、回数を増やす前に上限を確認し、必要最小限の試行にします。

トークン数も利用量の目安になります。会話型の質問では、前の会話履歴も入力としてモデルに送られるため、会話を続けると入力トークン数が増えることがあります。モデルや質問を比較するときは、質問だけでなく履歴・回答上限・生成設定も揃えて記録してください。

## 8. 機能をコードで再現するための変更箇所

ここでは、上記の機能を自分のプログラムへ移すときに、どの import、インスタンス、API、メソッドを使うかを、実装順にまとめます。コード例は `app/ask.py` の構成に対応した抜粋です。

### A. API クライアントと Chat セッションを作る

まず Google GenAI SDK の `genai.Client` を作成します。API キーはソースコードに直接書かず、既存の `get_api_key()` のように環境変数から読み込む関数を使います。次に `client.chats.create(model=...)` を一度呼び出して Chat セッションを作ります。

```python
import time

from google import genai
from google.genai.chats import Chat

from app.config import MODEL, get_api_key

client = genai.Client(api_key=get_api_key())
chat: Chat = client.chats.create(model=MODEL)
```

ここで使っている主なオブジェクトは次のとおりです。

| コード | 役割 |
|---|---|
| `genai.Client(...)` | Gemini API を呼び出すクライアントを作る |
| `client.chats.create(model=MODEL)` | 指定モデルとの会話セッションを開始する |
| `Chat` | セッションの型。会話中は同じインスタンスを使い続ける |
| `MODEL` | `app.config` から読み込むモデル名。環境変数 `AIE_MODEL` で切り替えられる |
| `get_api_key()` | `GEMINI_API_KEY` から API キーを取得する。キーをコードに埋め込まないための既存関数 |

既存の `ask(question)` のように一度だけ質問する処理では、関数内で Chat を作っても構いません。複数ターンの会話では、Chat の作成を入力ループの外側に置き、ループ内で新しい Chat を作らないことが重要です。

### B. 同じ Chat に質問し、トークン数と応答時間を表示する

質問を実際に送る共通関数は、Chat と質問文を受け取り、`chat.send_message(question)` を呼びます。送信直前と応答直後に `time.perf_counter()` を呼ぶことで、API 応答を待った時間を測ります。

```python
def ask_in_chat(chat: Chat, question: str) -> str:
    started_at = time.perf_counter()
    response = chat.send_message(question)
    elapsed_seconds = time.perf_counter() - started_at

    usage = response.usage_metadata
    input_tokens = usage.prompt_token_count if usage is not None else None
    output_tokens = usage.candidates_token_count if usage is not None else None
    input_display = input_tokens if input_tokens is not None else "不明"
    output_display = output_tokens if output_tokens is not None else "不明"

    print(f"[トークン] 入力: {input_display}, 出力: {output_display}")
    print(f"[応答時間] {elapsed_seconds:.2f}秒")
    return response.text
```

この処理で重要な API と値は以下のとおりです。

1. `chat.send_message(question)` は質問を SDK の Chat セッションに送信し、`GenerateContentResponse` を返します。同じ Chat に繰り返し送ると SDK が履歴を含めて次のターンを処理します。
2. `response.usage_metadata` は使用量情報です。Google GenAI SDK の応答では未設定（`None`）の場合があるため、その場合にそのまま属性を読まず、存在を確認します。
3. `usage.prompt_token_count` は入力側、`usage.candidates_token_count` は生成された候補回答側のトークン数です。値が未設定の場合もあるので、画面表示では `None` を「不明」に置き換えます。
4. `response.text` は生成された回答本文です。表示用の情報を追加しても、関数からはこれまでどおり本文を返します。
5. `time.perf_counter()` は経過時間の計測に使います。壁時計の日時ではなく、開始時と終了時の差を取ります。API 呼び出し前後に置くことで、通信と応答待ちを含む時間になります。

この抜粋を `app/ask.py` に入れる場合、ファイル先頭に `import time` と `from google.genai.chats import Chat` を加え、従来の `generate_content(...)` を使っていた質問処理を `chat.send_message(...)` に置き換えます。時間測定の開始は API 呼び出しの直前、終了は応答を受け取った直後に置いてください。

### C. 会話ループを作る

会話ループでは、最初に Chat を一つ作り、その同じ Chat をすべての質問に使います。次は `main()` に置く処理の要点です。

```python
chat = client.chats.create(model=MODEL)
question = args.question or DEFAULT_QUESTION

while True:
    print(f"[質問] {question}\n")
    print(ask_in_chat(chat, question))

    question = ""
    while not question:  # 空の入力は送らず、もう一度尋ねる
        try:
            question = input("\n続けて質問できます（終了するには /exit）: ").strip()
        except EOFError:
            question = "/exit"

    if question.lower() in {"/exit", "exit", "quit"}:
        break
```

`input()` は利用者が入力するまで待ち、入力された文字列を返します。`.strip()` は先頭・末尾の空白や改行を取り除きます。終了語を調べるときに `.lower()` を使うことで、大文字小文字が違っても終了できます。空文字列のあいだは内側の `while` で尋ね直すので、空の質問を API に送りません。`EOFError` は、パイプ入力の終了や入力ストリームの終端を意味するため、終了語と同じ扱いにして対話ループを正常に終了させます。

> 修正（2026-10-26）：最初の版は、空文字列のときに `continue` で外側のループの先頭へ戻していました。外側のループの先頭は「質問を表示して送信する」処理なので、空の質問をそのまま API に送っていました。内側のループで尋ね直す形に直し、`tests/test_ask.py` に空の入力が送られないことのテストを追加しました。

コマンドライン引数は `argparse` で任意にし、入力がなければ既定質問を使います。

```python
parser.add_argument("question", nargs="?")
args = parser.parse_args()
question = args.question or DEFAULT_QUESTION
```

`nargs="?"` は位置引数を0個または1個受け付ける指定です。利用例は `python -m app.ask "LoRAとは何ですか？"` です。質問を省略すると `DEFAULT_QUESTION` が使われます。

### D. Temperature などの生成設定を変える

回答の多様さや出力上限を実験で揃える場合、`google.genai.types.GenerateContentConfig` を使い、生成設定を `client.chats.create` に渡せます。

```python
from google.genai import types

chat = client.chats.create(
    model=MODEL,
    config=types.GenerateContentConfig(
        temperature=0.7,
        max_output_tokens=300,
    ),
)
response = chat.send_message("LoRAとは何ですか？")
```

`temperature` と `max_output_tokens` は `GenerateContentConfig` の設定項目です。比較実験では質問やモデルなどを固定し、これらのうち比較したい条件だけを変えます。なお、現在の `app/ask.py` はこの値を利用者が指定するオプションを設けていません。上のコードは実験時に設定を渡す方法の例であり、既存 CLI に temperature オプションを実装したという意味ではありません。

### E. API 通信をせずにテストする

テストでは Gemini API に接続せず、`monkeypatch` で `genai.Client` を偽物に置き換えます。偽の Chat は `send_message` が呼び出されたとき、テストが用意した応答オブジェクトを返します。例えばトークン数表示の確認では、次のような応答を作ります。

```python
from types import SimpleNamespace

response = SimpleNamespace(
    text="テスト回答",
    usage_metadata=SimpleNamespace(
        prompt_token_count=12,
        candidates_token_count=7,
    ),
)
```

この `response` を返す偽の `send_message` を用意し、`ask_in_chat` の出力に `入力: 12, 出力: 7` が含まれることを `capsys.readouterr().out` で確認します。`usage_metadata=None` の応答も別に用意すれば、「不明」の表示を検証できます。

時間計測のテストでは、実際に秒数を待つ必要はありません。`monkeypatch.setattr` で `time.perf_counter` を固定値を順に返す関数に差し替え、例えば `10.0` と `12.345` を返すようにします。実装は差の `2.345` 秒を小数第2位に丸めて表示するので、テストでは `[応答時間] 2.35秒` を確認できます。

会話履歴のテストでは、偽 Chat の `send_message` が質問をリストに記録するようにします。`main()` の入力も `monkeypatch` で「最初の質問」「続きの質問」「/exit」と順に返す関数に置き換えます。2つの質問が同じ偽 Chat に送られたこと、終了語の後に3つ目の質問が送られないことを検証すれば、会話ループの制御を確認できます。

これらのテストは、表示・時間差の計算・会話セッションの再利用という**アプリケーション側の接続**を確かめます。モデルの実際の回答品質やネットワーク速度をテストするものではありません。全テストはリポジトリのルートで次のように実行します。

```bash
uv run pytest -q tests/test_ask.py
```

## 9. 提出後の見直し（2026-10-26、締切後に追記）

結果の詳細は [answer.md の「提出後の見直し」](./answer.md#提出後の見直し2026-10-26締切後に追記) にあります。ここでは、再計測に使ったコードの要点だけを説明します。計測スクリプトは [homework/measure.py](./homework/measure.py) です。

```bash
uv run python lectures/01/homework/measure.py basic         --out <出力ディレクトリ>   # temperature 0.0/0.7/1.2 × 各3回
uv run python lectures/01/homework/measure.py advanced      --out <出力ディレクトリ>   # 2モデル × 2質問 × 各3回（出力上限120）
uv run python lectures/01/homework/measure.py advanced-long --out <出力ディレクトリ>   # 同じく出力上限1024
```

### 打ち切りと思考トークンを記録する

```python
response = client.models.generate_content(model=model, contents=question, config=config)
u = response.usage_metadata
record = {
    "input_tokens": u.prompt_token_count,
    "output_tokens": u.candidates_token_count,     # 回答本文のトークン数
    "thoughts_tokens": u.thoughts_token_count,     # 思考（thinking）に使ったトークン数。思考しないモデルでは None
    "finish_reason": str(response.candidates[0].finish_reason),   # STOP なら最後まで、MAX_TOKENS なら上限で打ち切り
}
```

- `max_output_tokens` には、思考のトークンも含まれます。`gemini-3.8-flash` に出力上限 120 を指定すると、思考に 111〜115 トークンを使い、本文は 1〜5 トークンで打ち切られました。提出時に「回答が `**LoRA` で途切れた」のはこのためです
- 回答の長さを比べるときは、`finish_reason` を必ず記録します。`candidates_token_count` だけでは、回答が短いのか、上限で切れたのかを区別できません

### temperature が届いているかを確かめる

temperature 0.0 でも毎回違う回答が出たので、設定が API に届いているかを、範囲外の値で確かめました。

```python
types.GenerateContentConfig(temperature=5.0)
# → 400: temperature must be in the range [0.0, 2.0].（値は届いている）
```

`gemini-3.5-flash-lite` では、temperature 0.0 だけでは出力が 1 つに決まらず、`top_k=1` と `seed=1` を加えると同じ回答になりました。

```python
types.GenerateContentConfig(temperature=0.0, top_k=1, seed=1, max_output_tokens=40)
```

### 記録の訂正

- 「7. 発展課題」の質問は「LoRAとは何ですか？一文で説明してください。」です（この節の記録どおり）。answer.md では「一文で説明してください。」を書き落としていたので、直しました
- 「7. 発展課題」の応答時間（26〜49 秒）は、同じ条件で測り直すと `gemini-3.5-flash-lite` で 0.66〜1.24 秒でした。1 回だけの測定では外れ値を見分けられないので、複数回の中央値で比べてください
