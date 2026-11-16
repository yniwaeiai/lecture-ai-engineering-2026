"""第5回 宿題で共通に使う部品：1 回の実行を記録する、結果を JSONL に追記する、集計する。

app.agent の main() と同じ経路（全文投入は run_full_context、それ以外は target.run_sync）で実行し、
回答・ツール呼び出し・時間・トークン数（キャッシュ読み出しを含む）・推定費用を 1 件の dict にまとめる。
"""

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from pydantic_ai.exceptions import ModelHTTPError  # noqa: E402
from pydantic_ai.messages import ToolCallPart, ToolReturnPart  # noqa: E402

from app.agent import FULL_CONTEXT_PROMPT, build_model  # noqa: E402
from app.config import MODEL  # noqa: E402
from app.retrieval import get_all_materials  # noqa: E402

RESULTS = ROOT / "lectures/05/homework/results"

QUESTIONS = {
    "Q1": "第2回の説明では、LoRAは何を固定し何を学習しますか？ QLoRAは何を加えますか？",
    "Q2": "第3回の例では、コンパクションとセッションをまたぐメモリはどう違いますか。日々のメモはすべて長期メモリに入りますか",
    "Q3": "今回作ったRAGの実測平均応答時間と正答率を教えてください",
    "Q4": "第2回のクイズ4で、Fine-Tuningが一番向いているのはどれですか？ その理由も教えてください",
    "Q5": "第2回のクイズ1〜4について、それぞれの問いと答えを教えてください",
    "Q6": "第3回の「Part 4 ツール」の章では、どんな話題をどの順で扱っていますか。ページ番号も付けてください",
    "Q7": "第3回の「Part 7 停止条件・失敗時の振る舞い」の章では、どんな話題をどの順で扱っていますか。ページ番号も付けてください",
}

# 章の構成を問う質問（Q6・Q7）の根拠：その章の全ページ。回答に出たページ番号で数える（chapter_coverage）
CHAPTER_PAGES = {"Q6": (3, range(22, 33)), "Q7": (3, range(42, 49))}

# 答えを支えるページ（先に原文で確かめた。technical-memo 1.2）。Q3 は資料に答えがない
EVIDENCE = {
    "Q1": ["lec02-main-p052"],
    "Q2": ["lec03-main-p013", "lec03-main-p039", "lec03-main-p040"],
    "Q3": [],
    "Q4": ["lec02-main-p056", "lec02-main-p057"],
    "Q5": ["lec02-main-p016", "lec02-main-p017", "lec02-main-p026", "lec02-main-p027",
           "lec02-main-p042", "lec02-main-p043", "lec02-main-p056", "lec02-main-p057"],
    "Q6": [f"lec03-main-p{n:03d}" for n in range(22, 33)],
    "Q7": [f"lec03-main-p{n:03d}" for n in range(42, 49)],
}
# Q5 は答えのページ（p.17・27・43・57）に問題文も載っているので、答えの 4 ページだけでも根拠はそろう（technical-memo 3.4）
SUFFICIENT = {"Q5": ["lec02-main-p017", "lec02-main-p027", "lec02-main-p043", "lec02-main-p057"],
              "Q4": ["lec02-main-p057"]}


def page_key(page_id: str) -> str:
    """lec02-main-p052 → L2p52（cited_pages と同じ形）"""
    m = re.match(r"lec(\d+)-main-p(\d+)", page_id)
    return f"L{int(m.group(1))}p{int(m.group(2))}"


def coverage(record: dict, qid: str) -> dict:
    """根拠ページのうち、取得できた数と、回答で引用した数。"""
    evidence = EVIDENCE[qid]
    got = {pid for r in record.get("tool_returns", []) for pid in r["page_ids"]}
    listed = {pid for r in record.get("tool_returns", []) for pid in r.get("listed_ids", [])}
    cited = set(record.get("cited", []))
    return {"retrieved": sum(pid in got for pid in evidence), "cited": sum(page_key(pid) in cited for pid in evidence),
            "listed_or_retrieved": sum(pid in got or pid in listed for pid in evidence),
            "of": len(evidence), "unique_pages_returned": len(got)}

# 入力単価（USD / 100 万 tokens）。キャッシュなしの費用を出し直すのに使う（genai-prices の値と、ログの費用から逆算した値が一致）
PRICE_INPUT, PRICE_OUTPUT = 0.30, 2.50

_model = None


def model():
    global _model
    if _model is None:
        _model = build_model()
    return _model


def cited_pages(text: str) -> list[str]:
    """回答に出てくる「第N回・PDF p.N」などの引用を、(回, ページ) の形に正規化して返す（重複なし・出現順）。"""
    found = []
    # 「第2回・PDF p.51, p.52」「第3回・PDF p.13、39、40」のような並びにも対応する
    for m in re.finditer(r"第\s*(\d+)\s*回[^第\n]{0,12}?p\.\s*([\d,、・\s〜\-p.]+)", text):
        lec = m.group(1)
        for n in re.findall(r"\d+", m.group(2)):
            key = f"L{lec}p{int(n)}"
            if key not in found:
                found.append(key)
    return found


def returned_pages(tool: str, content: str) -> tuple[list[str], list[str]]:
    """ツール結果から、本文（全文）を受け取ったページと、タイトルなどだけ受け取ったページを分けて返す。

    search_materials・search_graph は全件が本文つき。browse_tree はページを指定したときの node だけが全文で、
    children は先頭文だけ。search_outline は results が本文つき、outlines はタイトルだけ。
    """
    try:
        data = json.loads(content)
    except ValueError:
        return re.findall(r'"page_id": "([^"]+)"', content), []
    if tool == "browse_tree":
        node = data.get("node", {})
        full = [node["id"]] if node.get("kind") == "page" else []
        return full, [c["id"] for c in data.get("children", []) if c.get("kind") == "page"]
    if tool == "read_pages":
        return [p["page_id"] for p in data.get("pages", [])], []
    if tool in ("search_outline", "search_chapters"):
        return ([r["page_id"] for r in data.get("results", [])],
                [p["page_id"] for o in data.get("outlines", []) for p in o["pages"]])
    if tool == "search_graph":
        return [r["page_id"] for r in data.get("seeds", []) + data.get("expanded", [])], []
    return [r["page_id"] for r in data.get("results", [])], []


def mentioned_page_numbers(text: str) -> set[int]:
    """回答に出てくる「p.24」「p.25〜26」「p.25, 26」などのページ番号。

    範囲（p.22〜32）は両端だけを数え、間は含めない。最初の版は間も含めていたため、「この章（PDF p.22〜32 付近）」
    と書いただけの回答が 11 ページすべて挙げたことになっていた（technical-memo 4.4）。
    """
    numbers = set()
    for m in re.finditer(r"p\.\s*(\d+)((?:\s*[,、・]\s*(?:p\.\s*)?\d+)*)(?:\s*[〜~\-–]\s*(?:p\.\s*)?(\d+))?", text):
        start = int(m.group(1))
        numbers.add(start)
        numbers.update(int(n) for n in re.findall(r"\d+", m.group(2) or ""))
        if m.group(3):
            numbers.add(int(m.group(3)))
    return numbers


def chapter_coverage(record: dict, qid: str) -> int:
    """章の構成を問う質問で、章のページのうち回答にページ番号が出た数。"""
    _, pages = CHAPTER_PAGES[qid]
    return len(mentioned_page_numbers(record.get("answer", "")) & set(pages))


def run_once(target, question: str, *, full_context_instructions: str | None = None) -> dict:
    """1 回実行して記録を返す。full_context_instructions を渡すと全文投入で実行する。"""
    started = time.perf_counter()
    try:
        if full_context_instructions is not None:
            prompt = FULL_CONTEXT_PROMPT.format(materials=get_all_materials(), question=question)
            with target.override(tools=[], instructions=full_context_instructions):
                result = target.run_sync(prompt, model=model())
        else:
            result = target.run_sync(question, model=model())
    except ModelHTTPError as e:
        return {"error": f"HTTP {e.status_code}", "elapsed": time.perf_counter() - started}
    elapsed = time.perf_counter() - started
    u = result.usage
    calls, returns = [], []
    for message in result.all_messages():
        for part in message.parts:
            if isinstance(part, ToolCallPart):
                calls.append({"tool": part.tool_name, "args": part.args_as_dict()})
            elif isinstance(part, ToolReturnPart):
                full, listed = returned_pages(part.tool_name, str(part.content))
                returns.append({"tool": part.tool_name, "chars": len(str(part.content)),
                                "page_ids": full, "listed_ids": listed})
    answer = str(result.output)
    uncached = (u.input_tokens * PRICE_INPUT + u.output_tokens * PRICE_OUTPUT) / 1e6
    return {
        "model": MODEL, "answer": answer, "cited": cited_pages(answer),
        "tool_calls": calls, "tool_returns": returns,
        "elapsed": round(elapsed, 2), "input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
        "cache_read_tokens": u.cache_read_tokens, "requests": u.requests,
        "cost": float(u.cost) if u.cost is not None else None, "cost_uncached": round(uncached, 6),
    }


def load_runs(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_run(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None
