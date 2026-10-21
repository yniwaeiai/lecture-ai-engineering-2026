from types import SimpleNamespace

from app import ask


def _mock_client(monkeypatch, response):
    models = SimpleNamespace(generate_content=lambda **kwargs: response)
    client = SimpleNamespace(models=models)
    monkeypatch.setattr(ask.genai, "Client", lambda **kwargs: client)
    monkeypatch.setattr(ask, "get_api_key", lambda: "test-api-key")


def test_ask_displays_input_and_output_token_counts(monkeypatch, capsys):
    _mock_client(
        monkeypatch,
        SimpleNamespace(
            text="テスト回答",
            usage_metadata=SimpleNamespace(prompt_token_count=12, candidates_token_count=7),
        ),
    )

    assert ask.ask("テスト質問") == "テスト回答"
    assert "[トークン] 入力: 12, 出力: 7" in capsys.readouterr().out


def test_ask_displays_unknown_when_usage_metadata_is_missing(monkeypatch, capsys):
    _mock_client(monkeypatch, SimpleNamespace(text="テスト回答", usage_metadata=None))

    ask.ask("テスト質問")

    assert "[トークン] 入力: 不明, 出力: 不明" in capsys.readouterr().out
