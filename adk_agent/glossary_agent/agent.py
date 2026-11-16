"""第3回 宿題（発展 a）: 改訂された課題文（2026-10-31）どおりの形で、演習のエージェントを ADK で組み立てる。

動かす（リポジトリ直下で。要 GEMINI_API_KEY）:
    PYTHONPATH=. uv run --with google-adk adk run adk_agent/glossary_agent
"""

from google.adk.agents import Agent

from app import tools
from app.agent import GLOSSARY_INSTRUCTIONS as INSTRUCTIONS  # 第5回で既定の INSTRUCTIONS が検索用に変わったので、用語集版を使う

root_agent = Agent(
    model="gemini-3.5-flash-lite",
    name="glossary_agent",
    instruction=INSTRUCTIONS,
    tools=[tools.search_glossary, tools.get_lecture_summary, tools.make_quiz],
)
