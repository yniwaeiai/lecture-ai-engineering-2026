"""第1回 宿題（基礎・発展）の計測をやり直すスクリプト。

使い方（リポジトリ直下で。要 GEMINI_API_KEY）:
    uv run python lectures/01/homework/measure.py basic    --out <出力ディレクトリ>
    uv run python lectures/01/homework/measure.py advanced --out <出力ディレクトリ>
    uv run python lectures/01/homework/measure.py advanced-long --out <出力ディレクトリ>

basic   : 同じ質問を temperature 0.0 / 0.7 / 1.2 で各 3 回（課題の「3回ずつ」）
advanced: 2 つの質問 × 2 つのモデルを各 3 回。応答時間とトークン数（思考トークンを含む）を記録する（出力上限 120）
advanced-long: advanced と同じで、出力上限を 1024 にしたもの

1 回ずつ新しい会話（generate_content）で送るので、前の質問の履歴は入らない。
"""

import argparse
import json
import sys
import time
from pathlib import Path

from google import genai
from google.genai import errors, types

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # リポジトリ直下（app パッケージ）を import できるようにする
from app.config import get_api_key  # noqa: E402

BASIC = {
    "models": ["gemini-3.5-flash-lite"],
    "questions": ["LoRAとは何ですか？"],
    "temperatures": [0.0, 0.7, 1.2],
    "max_output_tokens": 300,
}
ADVANCED = {
    "models": ["gemini-3.5-flash-lite", "gemini-3.8-flash"],
    "questions": ["LoRAとは何ですか？一文で説明してください。", "RAGとは何ですか？一文で説明してください。"],
    "temperatures": [0.2],
    "max_output_tokens": 120,
}
# 出力上限 120 では gemini-3.8-flash が思考だけで上限を使い切るので、上限を上げて最後まで答えさせた版
ADVANCED_LONG = {**ADVANCED, "max_output_tokens": 1024}
REPS = 3


def measure(client: genai.Client, model: str, question: str, temperature: float, max_output_tokens: int) -> dict:
    config = types.GenerateContentConfig(temperature=temperature, max_output_tokens=max_output_tokens)
    started_at = time.perf_counter()
    try:
        response = client.models.generate_content(model=model, contents=question, config=config)
    except errors.APIError as e:
        return {"error": f"{e.code} {e.message}"[:200], "seconds": round(time.perf_counter() - started_at, 2)}
    seconds = time.perf_counter() - started_at
    u = response.usage_metadata
    candidate = response.candidates[0] if response.candidates else None
    return {
        "seconds": round(seconds, 2),
        "input_tokens": u.prompt_token_count if u else None,
        "output_tokens": u.candidates_token_count if u else None,    # 回答本文のトークン数
        "thoughts_tokens": u.thoughts_token_count if u else None,    # 思考（thinking）に使ったトークン数
        "finish_reason": str(candidate.finish_reason) if candidate else None,
        "text": response.text,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["basic", "advanced", "advanced-long"])
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    plan = {"basic": BASIC, "advanced": ADVANCED, "advanced-long": ADVANCED_LONG}[args.mode]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    client = genai.Client(api_key=get_api_key())
    records = []
    for model in plan["models"]:
        for question in plan["questions"]:
            for temperature in plan["temperatures"]:
                for rep in range(REPS):
                    r = measure(client, model, question, temperature, plan["max_output_tokens"])
                    records.append({"model": model, "question": question, "temperature": temperature, "rep": rep, **r})
                    head = (r.get("text") or r.get("error") or "").replace("\n", " ")[:50]
                    print(f"{model:22s} T={temperature} #{rep} {r['seconds']:6.2f}s in={r.get('input_tokens')} "
                          f"out={r.get('output_tokens')} think={r.get('thoughts_tokens')} {r.get('finish_reason')} | {head}",
                          flush=True)
                    time.sleep(2)
    (out / f"{args.mode}.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
