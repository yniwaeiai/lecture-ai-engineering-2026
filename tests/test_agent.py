"""エージェントの配線テスト。

TestModel は実際のLLMを呼ばない偽モデルで、登録されたツールを全部呼んでから
ダミーの回答を返す。APIキーも利用枠も使わずに、
「ツールが登録され、呼ばれ、結果がモデルに戻るか」を確かめられる。
"""

from pydantic_ai import DeferredToolRequests
from pydantic_ai.messages import ToolCallPart, ToolReturnPart
from pydantic_ai.models.test import TestModel

from app import tools
from app.agent import agent, ask_approvals, run_with_approval

BASE_TOOLS = {"search_glossary", "get_lecture_summary"}


def _parts(result, kind):
    return [p for m in result.all_messages() for p in m.parts if isinstance(p, kind)]


def test_base_tools_are_registered_and_called():
    model = TestModel()
    with agent.override(model=model):
        result = agent.run_sync("LoRAとは？")

    offered = {t.name for t in model.last_model_request_parameters.function_tools}
    assert BASE_TOOLS <= offered  # 演習でツールを足しても壊れないよう「含む」で判定

    called = {p.tool_name for p in _parts(result, ToolCallPart)}
    assert BASE_TOOLS <= called
    # 承認が必要なツール（第3回 宿題の save_learning_log）は、承認されるまで実行されず結果も戻らない
    pending = result.output.approvals if isinstance(result.output, DeferredToolRequests) else []
    assert len(_parts(result, ToolReturnPart)) == len(_parts(result, ToolCallPart)) - len(pending)
    assert result.output


def test_glossary_result_reaches_the_model():
    model = TestModel(call_tools=["search_glossary"])
    with agent.override(model=model):
        result = agent.run_sync("RAGとは？")
    returns = _parts(result, ToolReturnPart)
    assert returns and returns[0].tool_name == "search_glossary"


def test_make_quiz_is_registered_and_returns_to_the_model():
    model = TestModel(call_tools=["make_quiz"])
    with agent.override(model=model):
        result = agent.run_sync("第2回の確認問題を出して")
    assert "make_quiz" in {t.name for t in model.last_model_request_parameters.function_tools}
    returns = _parts(result, ToolReturnPart)
    assert returns and returns[0].tool_name == "make_quiz"


def _run_save_log(monkeypatch, tmp_path, reply):
    """TestModel に save_learning_log を呼ばせ、承認の問いに reply と答えたときの結果を返す。"""
    monkeypatch.setattr(tools, "LEARNING_LOG_DIR", tmp_path)
    with agent.override(model=TestModel(call_tools=["save_learning_log"])):
        first = agent.run_sync("今日の学びを記録して")
        assert isinstance(first.output, DeferredToolRequests)          # 実行されずに承認待ちで止まる
        assert [c.tool_name for c in first.output.approvals] == ["save_learning_log"]
        assert list(tmp_path.iterdir()) == []                          # この時点ではまだ保存されていない
        results = ask_approvals(first.output, answer=lambda _: reply)
        return agent.run_sync(message_history=first.all_messages(), deferred_tool_results=results)


def test_run_with_approval_counts_usage_of_both_runs(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "LEARNING_LOG_DIR", tmp_path)
    model = TestModel(call_tools=["save_learning_log"])
    result = run_with_approval(agent, "今日の学びを記録して", model, answer=lambda _: "y")
    assert isinstance(result.output, str)
    assert result.usage.requests == 2                                  # 承認待ちで止まる前の 1 回 ＋ 再開後の 1 回


def test_save_learning_log_writes_only_after_approval(monkeypatch, tmp_path):
    result = _run_save_log(monkeypatch, tmp_path, "y")
    assert len(list(tmp_path.glob("*.md"))) == 1
    returns = [p for p in _parts(result, ToolReturnPart) if p.tool_name == "save_learning_log"]
    assert returns and "保存しました" in returns[0].content


def test_save_learning_log_is_not_written_when_denied(monkeypatch, tmp_path):
    result = _run_save_log(monkeypatch, tmp_path, "n")
    assert list(tmp_path.iterdir()) == []
    assert isinstance(result.output, str)                              # 拒否されても会話は続き、回答で終わる
