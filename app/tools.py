"""第3回: エージェントに持たせるツール。

ここに書いた関数の docstring と型ヒントが、そのままモデルへの「ツールの説明文」になる。
説明文を書き換えると、モデルがツールを使うかどうか・どんな引数で呼ぶかが変わる。
"""

import json
import random
import re
from datetime import datetime
from functools import cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LEARNING_LOG_DIR = Path(__file__).resolve().parent.parent / "learning_log"  # .gitignore 済み。テストでは差し替える
MAX_RESULTS = 3
NUM_LECTURES = 13  # AIE2026 は全13回


@cache
def load_glossary() -> list[dict]:
    with open(DATA_DIR / "glossary.json", encoding="utf-8") as f:
        return json.load(f)["terms"]


def _normalize(text: str) -> str:
    return text.casefold().replace(" ", "").replace("　", "")


def _names(entry: dict) -> list[str]:
    return [_normalize(entry["term"]), _normalize(entry["id"])] + [
        _normalize(a) for a in entry["aliases"]
    ]


def search_glossary(query: str) -> str:
    """講座の用語集から用語を検索し、定義と、どの回で扱うかを返す。

    AIエンジニアリングの用語や、この講座（AIE2026）に固有の言葉について
    答える前に使うこと。query には調べたい用語を1つだけ入れる（例: "LoRA"）。
    """
    q = _normalize(query)
    if not q:
        return "検索語が空です。調べたい用語を1つ指定してください。"
    glossary = load_glossary()

    exact = [e for e in glossary if q in _names(e)]
    # 「r」のような短い別名が何にでも当たらないよう、名前側が短いものは除く
    partial = [
        e for e in glossary
        if e not in exact and any(q in n or (len(n) >= 3 and n in q) for n in _names(e))
    ]
    in_definition = [
        e for e in glossary
        if e not in exact and e not in partial and q in _normalize(e["definition"])
    ]
    hits = (exact + partial + in_definition)[:MAX_RESULTS]

    if not hits:
        return f"用語集に「{query}」は見つかりませんでした。"
    return json.dumps(
        [
            {
                "term": e["term"],
                "lecture": e["lecture"],
                "definition": e["definition"],
                "related": e["related"],
            }
            for e in hits
        ],
        ensure_ascii=False,
    )


def get_lecture_summary(lecture: int) -> str:
    """指定した回（1始まりの整数）の講義の要点を返す。

    「第3回では何を学ぶ？」のように、回の内容や関係を聞かれたときに使う。
    """
    path = DATA_DIR / "lectures" / f"{lecture:02d}.md"
    if not path.exists():
        available = sorted(p.stem for p in (DATA_DIR / "lectures").glob("*.md"))
        return f"第{lecture}回の要点はまだありません。用意されている回: {', '.join(available)}"
    return path.read_text(encoding="utf-8")


def make_quiz(lecture: int) -> str:
    """指定した回（1始まりの整数）の用語から1つを選び、「この用語の意味は？」という確認問題と答えを返す。

    「第2回の確認問題を出して」「LoRAの回の復習クイズがほしい」のように、
    学習者が理解度を確かめる問題を求めたときに使う。問題だけを先に見せ、
    answer（用語集の定義）は学習者が答えたあとに示すこと。
    lecture は 1〜13（AIE2026 は全13回）。範囲外ならエラーになる。
    """
    if not 1 <= lecture <= NUM_LECTURES:
        # 存在しない回はツールの使い方の誤りなので、例外にしてモデルに引数を直させる（第5回 宿題）
        raise ValueError(f"lecture は 1〜{NUM_LECTURES} の整数で指定してください（AIE2026 は全{NUM_LECTURES}回）。指定された値: {lecture}")
    candidates = [e for e in load_glossary() if e["lecture"] == lecture]
    if not candidates:
        available = sorted({e["lecture"] for e in load_glossary()})
        return f"第{lecture}回の用語は用語集にありません。用語がある回: {', '.join(map(str, available))}"
    entry = random.choice(candidates)
    return json.dumps(
        {
            "lecture": lecture,
            "question": f"「{entry['term']}」の意味は？",
            "answer": entry["definition"],
        },
        ensure_ascii=False,
    )


def save_learning_log(title: str, content: str, lecture: int | None = None) -> str:
    """学習の記録（学んだこと・疑問・次にやること）を learning_log/ に Markdown で保存する。

    「今日の学びを記録して」「この内容をメモに残して」のように、学習者が記録を頼んだときだけ使う。
    title は記録の見出し（短く）、content は本文、lecture は関係する回（分かるときだけ）。
    保存の前に利用者の確認が入るので、承認されなかったときは保存されなかったことを伝える。
    """
    now = datetime.now()
    slug = re.sub(r"[^0-9A-Za-zぁ-んァ-ヶ一-龠ー]+", "-", title).strip("-")[:40] or "log"  # ファイル名に使えない文字を除く
    LEARNING_LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LEARNING_LOG_DIR / f"{now:%Y-%m-%d_%H%M%S}_{slug}.md"
    header = f"# {title}\n\n- 日時: {now:%Y-%m-%d %H:%M}\n" + (f"- 関係する回: 第{lecture}回\n" if lecture else "")
    path.write_text(f"{header}\n{content}\n", encoding="utf-8")
    return f"保存しました: learning_log/{path.name}"
