"""第3回 宿題（発展 a）: app/agent.py の学習支援エージェントを Google ADK で作り直したもの。

ツール関数は app/tools.py をそのまま使い、INSTRUCTIONS も同じ文面にしている（違いはフレームワークだけ）。
使い方（リポジトリ直下で。google-adk を入れた別の環境。要 GEMINI_API_KEY）:
    adk web lectures/03/homework/adk          # ブラウザの開発 UI
    adk run lectures/03/homework/adk/aie_agent   # ターミナルで対話
"""

import sys
from pathlib import Path

from google.adk.agents import Agent
from google.adk.tools import FunctionTool

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))  # リポジトリ直下（app パッケージ）を import できるようにする
from app import tools  # noqa: E402
from app.config import MODEL  # noqa: E402

# app/agent.py の INSTRUCTIONS と同じ文面（pydantic_ai を import しないよう複製している。比較スクリプトで一致を確かめる）
INSTRUCTIONS = """\
あなたはAIエンジニアリング講座（AIE2026）の学習支援エージェントです。
- 用語や講座に固有のことを答える前に、必ず search_glossary で用語集を確認する。
- 回の内容を聞かれたら get_lecture_summary を使う。
- 用語集に見つからないことは、推測で断定せず「用語集にはない」と伝える。
- 回答の最後に、関係する回（第N回）を示す。
- 宿題の答えそのものは書かず、考え方のヒントで導く。
"""

root_agent = Agent(
    name="aie_agent",
    model=MODEL,  # 文字列で渡すと Gemini（google-genai）が使われ、GEMINI_API_KEY を読む
    description="AIE2026 の学習支援エージェント（用語集の検索・回の要点・確認問題・学習ログ）",
    instruction=INSTRUCTIONS,
    tools=[
        tools.search_glossary,      # 関数をそのまま渡すと FunctionTool として包まれる
        tools.get_lecture_summary,
        tools.make_quiz,
        FunctionTool(tools.save_learning_log, require_confirmation=True),  # 実行前に利用者の確認を求める
    ],
)
