from types import SimpleNamespace

from app import ask


def _mock_client(monkeypatch, chat):
    def create(*, model):
        assert model == ask.MODEL
        return chat

    def create_client(*, api_key):
        assert api_key == "test-api-key"
        return client

    chats = SimpleNamespace(create=create)
    client = SimpleNamespace(chats=chats)
    monkeypatch.setattr(ask.genai, "Client", create_client)
    monkeypatch.setattr(ask, "get_api_key", lambda: "test-api-key")


def test_ask_displays_input_and_output_token_counts(monkeypatch, capsys):
    def send_message(question):
        return SimpleNamespace(
            text=f"{question}への回答",
            usage_metadata=SimpleNamespace(prompt_token_count=12, candidates_token_count=7),
        )

    chat = SimpleNamespace(send_message=send_message)
    _mock_client(monkeypatch, chat)

    assert ask.ask("テスト質問") == "テスト質問への回答"
    assert "[トークン] 入力: 12, 出力: 7" in capsys.readouterr().out


def test_ask_displays_unknown_when_usage_metadata_is_missing(monkeypatch, capsys):
    def send_message(question):
        return SimpleNamespace(
            text=f"{question}への回答",
            usage_metadata=None,
        )

    chat = SimpleNamespace(send_message=send_message)
    _mock_client(monkeypatch, chat)

    ask.ask("テスト質問")

    assert "[トークン] 入力: 不明, 出力: 不明" in capsys.readouterr().out


def test_ask_displays_response_time(monkeypatch, capsys):
    def send_message(question):
        return SimpleNamespace(
            text=f"{question}への回答",
            usage_metadata=SimpleNamespace(prompt_token_count=12, candidates_token_count=7),
        )

    chat = SimpleNamespace(send_message=send_message)
    _mock_client(monkeypatch, chat)
    clock = iter([10.0, 12.345])
    monkeypatch.setattr(ask.time, "perf_counter", lambda: next(clock))

    ask.ask("テスト質問")

    assert "[応答時間] 2.35秒" in capsys.readouterr().out


def test_main_keeps_chat_history_for_follow_up_questions(monkeypatch, capsys):
    sent_messages = []

    def send_message(question):
        sent_messages.append(question)
        previous = " / ".join(sent_messages[:-1]) or "なし"
        return SimpleNamespace(
            text=f"前の質問: {previous}",
            usage_metadata=SimpleNamespace(prompt_token_count=5, candidates_token_count=4),
        )

    chat = SimpleNamespace(send_message=send_message)
    _mock_client(monkeypatch, chat)
    monkeypatch.setattr("sys.argv", ["app.ask", "最初の質問"])
    inputs = iter(["続きの質問", "/exit"])

    def read_input(prompt):
        assert "/exit" in prompt
        return next(inputs)

    monkeypatch.setattr("builtins.input", read_input)

    ask.main()

    output = capsys.readouterr().out
    assert sent_messages == ["最初の質問", "続きの質問"]
    assert "前の質問: なし" in output
    assert "前の質問: 最初の質問" in output


def test_main_does_not_send_empty_input(monkeypatch, capsys):
    sent_messages = []

    def send_message(question):
        sent_messages.append(question)
        return SimpleNamespace(text="回答", usage_metadata=None)

    _mock_client(monkeypatch, SimpleNamespace(send_message=send_message))
    monkeypatch.setattr("sys.argv", ["app.ask", "最初の質問"])
    inputs = iter(["", "   ", "続きの質問", "/exit"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))

    ask.main()

    assert sent_messages == ["最初の質問", "続きの質問"]
