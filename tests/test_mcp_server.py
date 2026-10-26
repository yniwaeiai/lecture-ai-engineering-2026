"""第5回: MCP サーバーとクライアントの配線テスト（LLM も API キーも使わない）。

app/mcp_servers.json の glossary サーバーを実際に起動し（stdio）、TestModel で
「ツールが MCP 経由で公開され、呼ばれ、結果が戻るか」を確かめる。
"""

import json

import pytest
from pydantic_ai import capture_run_messages
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, RetryPromptPart, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from app.agent import MCP_CONFIG, build_mcp_agent

GLOSSARY_TOOL = "glossary_search_glossary"  # 設定ファイルのサーバー名 "glossary" が前に付く
QUIZ_TOOL = "glossary_make_quiz"  # 第5回 宿題で公開した make_quiz


def _glossary_only_config(tmp_path):
    """設定のうち glossary サーバーだけを使う（演習で足した fetch などの外部サーバーは起動しない）。"""
    config = json.loads(MCP_CONFIG.read_text(encoding="utf-8"))
    assert "glossary" in config["mcpServers"], "app/mcp_servers.json に glossary サーバーが必要"
    path = tmp_path / "mcp_servers.json"
    path.write_text(
        json.dumps({"mcpServers": {"glossary": config["mcpServers"]["glossary"]}}), encoding="utf-8"
    )
    return path


def _parts(result, kind):
    return [p for m in result.all_messages() for p in m.parts if isinstance(p, kind)]


def test_glossary_server_exposes_search_tool(tmp_path):
    model = TestModel(call_tools=[])
    build_mcp_agent(_glossary_only_config(tmp_path)).run_sync("ツール一覧", model=model)

    offered = {t.name for t in model.last_model_request_parameters.function_tools}
    assert GLOSSARY_TOOL in offered  # 演習でツールを足しても壊れないよう「含む」で判定


def test_glossary_result_comes_back_through_mcp(tmp_path):
    model = TestModel(call_tools=[GLOSSARY_TOOL])
    result = build_mcp_agent(_glossary_only_config(tmp_path)).run_sync("LoRAとは？", model=model)

    assert [p.tool_name for p in _parts(result, ToolCallPart)] == [GLOSSARY_TOOL]
    returns = _parts(result, ToolReturnPart)
    assert returns and returns[0].tool_name == GLOSSARY_TOOL
    assert str(returns[0].content).strip()  # 検索結果（または「見つかりませんでした」）が戻っている
    assert result.output


def test_quiz_and_summary_tools_are_exposed(tmp_path):
    model = TestModel(call_tools=[])
    build_mcp_agent(_glossary_only_config(tmp_path)).run_sync("ツール一覧", model=model)

    offered = {t.name: t for t in model.last_model_request_parameters.function_tools}
    assert {QUIZ_TOOL, "glossary_get_lecture_summary"} <= offered.keys()
    assert "1〜13" in offered[QUIZ_TOOL].description  # docstring の範囲の説明が、MCP 越しにも見える


def test_quiz_through_mcp_returns_a_question(tmp_path):
    def respond(messages, info):  # 1 回目は第2回で make_quiz を呼び、2 回目で回答する（TestModel は引数を選べない）
        if not any(isinstance(m, ModelResponse) for m in messages):
            return ModelResponse(parts=[ToolCallPart(QUIZ_TOOL, {"lecture": 2})])
        return ModelResponse(parts=[TextPart("回答")])

    result = build_mcp_agent(_glossary_only_config(tmp_path)).run_sync("第2回の確認問題", model=FunctionModel(respond))
    returns = [p for p in _parts(result, ToolReturnPart) if p.tool_name == QUIZ_TOOL]
    assert returns and "の意味は？" in str(returns[0].content)


def test_out_of_range_error_reaches_the_model_through_mcp(tmp_path):
    # TestModel は lecture=0 で呼び、エラーを受けても同じ引数で呼び直すので、再試行の上限を超えて止まる
    with capture_run_messages() as messages:
        with pytest.raises(UnexpectedModelBehavior):
            build_mcp_agent(_glossary_only_config(tmp_path)).run_sync("確認問題", model=TestModel(call_tools=[QUIZ_TOOL]))

    retries = [p for m in messages for p in m.parts if isinstance(p, RetryPromptPart)]
    assert retries, "MCP のツールのエラーは、再試行の指示としてモデルに戻る"
    # ToolError に変えているので、範囲の説明（「1〜13」）がモデルまで届く（ValueError のままだと届かない）
    assert "1〜13" in retries[0].model_response()
