"""第2回 宿題（発展）: 講座の用語集で LoRA 学習し、学習前・学習後・用語集検索（RAG）の 3 方式を比べる。

使い方（リポジトリ直下で。ノートブックの PINS と同じ版の transformers / peft / trl / datasets が入った環境）:
    python lectures/02/homework/advanced_glossary.py --out <出力ディレクトリ>

Colab では、このファイルをアップロードして `!python advanced_glossary.py --out /content/glossary_lab` で動く
（data/glossary.json・scripts/make_sft_dataset.py・app/tools.py を同じ相対位置に置く）。

学習データ:
    scripts/make_sft_dataset.py の出力（58 語 × 2 テンプレート = 116 件）に、
    用語集に無い語への「載っていません」応答（10 語 × 2 テンプレート = 20 件）を足す
評価（EVAL）:
    seen       … 用語集にある語を、学習と同じテンプレートで聞く（覚えたかの確認）
    paraphrase … 用語集にある語を、別の言い回し・別名で聞く（言い換えへの汎化）
    absent     … 用語集に無い語を聞く（正解は「用語集に載っていません」）
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTConfig, SFTTrainer

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from app.tools import search_glossary  # noqa: E402  第3回のツール。検索方式の比較に使う
from scripts.make_sft_dataset import TEMPLATES  # noqa: E402

CONFIG = {
    "base_model": "Qwen/Qwen3.5-0.8B",
    "revision": "2fc06364715b967f1860aea9cf38778875588b17",
    "seed": 42,
    "num_train_epochs": 10,  # 136 件 × 10 周。1 周 17 ステップなので合計 170 ステップ
    "warmup_steps": 6,
    "lr": 2e-4,
    "lora_r": 16,
    "lora_alpha": 32,
    "max_seq_len": 512,
    "max_new_tokens": 160,
    "gen": {"do_sample": False},
}

ABSENT_ANSWER = "「{term}」は講座の用語集に載っていません。"
ABSENT_MARK = "用語集に載っていません"
# 「用語集に無い」と答えたとみなす表現。検索ツールの「見つかりませんでした」をそのまま返す答えも正しい振る舞いとして数える
ABSENT_PATTERNS = (ABSENT_MARK, "見つかりませんでした")
# 学習用の「用語集に無い語」（評価用の absent とは重ねない）
ABSENT_TRAIN = ["LangChain", "ベクトルデータベース", "DPO", "Docker", "強化学習",
                "トランスフォーマー", "lecNN-end タグ", "提出ボーナス", "Kubernetes", "埋め込み"]

# (種別, 質問, 検索方式で search_glossary に渡す語, 正解の answer に含まれるべき語)。absent の must_include は ABSENT_MARK
EVAL = [
    ("seen", "「Pi」とは何ですか？", "Pi", ["MIT"]),
    ("seen", "「既定モデル」とは何ですか？", "既定モデル", ["gemini-3.5-flash-lite"]),
    ("seen", "「宿題の3レベル」とは何ですか？", "宿題の3レベル", ["基礎", "実装", "発展"]),
    ("seen", "「lecNN-start タグ」とは何ですか？", "lecNN-start タグ", ["演習開始"]),
    ("seen", "「TestModel」とは何ですか？", "TestModel", ["Pydantic AI"]),
    ("seen", "「ハーネス」とは何ですか？", "ハーネス", ["Claude Code"]),
    ("seen", "「LoRA」とは何ですか？", "LoRA", ["低ランク"]),
    ("seen", "「エポック」とは何ですか？", "エポック", ["1周"]),
    ("seen", "「answer.md」とは何ですか？", "answer.md", ["lectures/"]),
    ("seen", "「Codespaces secret」とは何ですか？", "Codespaces secret", ["環境変数"]),
    ("paraphrase", "Low-Rank Adaptation ってどういう仕組みですか？", "Low-Rank Adaptation", ["低ランク"]),
    ("paraphrase", "AIE2026 で標準に使うモデルは何ですか？", "既定モデル", ["gemini-3.5-flash-lite"]),
    ("paraphrase", "宿題はいくつのレベルに分かれていて、何をすれば完了ですか？", "宿題レベル", ["1つ"]),
    ("paraphrase", "Pi というコーディングエージェントの特徴を教えてください。", "Pi", ["MIT"]),
    ("paraphrase", "lec03-start というタグは何のためにありますか？", "lec03-start", ["演習開始"]),
    ("paraphrase", "HITL を使うのはどんなときですか？", "HITL", ["承認"]),
    ("paraphrase", "429 エラーが出るのはなぜですか？", "429エラー", ["上限"]),
    ("paraphrase", "テスト用モデルを使うと何ができますか？", "テスト用モデル", ["呼ばず"]),
    ("paraphrase", "mcp_servers.json には何を書きますか？", "mcp_servers.json", ["起動コマンド"]),
    ("paraphrase", "ツール名のプレフィックスは何のために付けますか？", "ツール名のプレフィックス", ["区別"]),
    ("paraphrase", "過学習に気づくにはどうすればいいですか？", "過学習", ["検証データ"]),
    ("paraphrase", "QLoRA は LoRA と何が違いますか？", "QLoRA", ["量子化"]),
    ("absent", "「プロンプトインジェクション」とは何ですか？", "プロンプトインジェクション", None),
    ("absent", "「蒸留」とは何ですか？", "蒸留", None),
    ("absent", "「RLHF」とは何ですか？", "RLHF", None),
    ("absent", "「lec03-end タグ」とは何ですか？", "lec03-end タグ", None),
    ("absent", "Chain-of-Thought について簡単に説明してください。", "Chain-of-Thought", None),
    ("absent", "MoE（Mixture of Experts）ってどういう意味ですか？", "MoE（Mixture of Experts）", None),
    ("absent", "この講座の期末レポートについて教えてください。", "期末レポート", None),
    ("absent", "ベンチマークとは何のことですか？", "ベンチマーク", None),
]

RAG_SYSTEM = ("あなたは講座の用語集に基づいて答えるアシスタントです。与えられた検索結果だけを根拠に、簡潔に答えてください。"
              f"検索結果に質問の語が無いときは「{ABSENT_MARK}」とだけ答えてください。")


def make_train_records() -> list[dict]:
    # 配布スクリプトをそのまま実行し、出力（messages 形式の JSONL）を読む
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "make_sft_dataset.py")],
                         capture_output=True, text=True, check=True).stdout
    records = [json.loads(line) for line in out.splitlines() if line.strip()]
    for term in ABSENT_TRAIN:
        for template in TEMPLATES:
            records.append({"messages": [{"role": "user", "content": template.format(term=term)},
                                         {"role": "assistant", "content": ABSENT_ANSWER.format(term=term)}]})
    return records


def _norm(text: str) -> str:
    return text.replace(" ", "").replace("　", "")   # 「1 つ」と「1つ」のような空白の違いで落とさない


def score(kind: str, must_include, raw: str) -> bool:
    said_absent = any(p in raw for p in ABSENT_PATTERNS)
    if kind == "absent":
        return said_absent
    return not said_absent and all(_norm(w) in _norm(raw) for w in must_include)


def rescore(out: Path) -> None:
    """保存済みの eval_*.json を、いまの score() で採点し直す（生成はやり直さない）"""
    must = {q: m for _, q, _, m in EVAL}
    summary = {}
    for label in ["before", "rag", "after"]:
        rows = json.loads((out / f"eval_{label}.json").read_text(encoding="utf-8"))
        for r in rows:
            r["ok"] = score(r["kind"], must[r["question"]], r["raw"])
        (out / f"eval_{label}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        summary[label] = summarize(rows)
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    result["summary"] = summary
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--rescore", action="store_true", help="学習・生成をせず、保存済みの出力を採点し直す")
    args = ap.parse_args()
    out = Path(args.out)
    if args.rescore:
        return rescore(out)
    out.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(CONFIG["seed"])

    train = make_train_records()
    (out / "glossary_sft.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in train), encoding="utf-8")
    train_questions = {r["messages"][0]["content"] for r in train}
    assert all((q in train_questions) == (kind == "seen") for kind, q, _, _ in EVAL), "seen 以外の評価質問が学習データに入っています"
    print(f"train={len(train)} eval={len(EVAL)}")

    tok = AutoTokenizer.from_pretrained(CONFIG["base_model"], revision=CONFIG["revision"])
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(CONFIG["base_model"], revision=CONFIG["revision"], dtype=torch.float32).to("cuda")

    def generate(m, messages) -> str:
        prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
        inputs = tok(prompt, return_tensors="pt").to(m.device)
        with torch.no_grad():
            o = m.generate(**inputs, max_new_tokens=CONFIG["max_new_tokens"], pad_token_id=tok.pad_token_id, **CONFIG["gen"])
        return tok.decode(o[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()

    def evaluate(label: str, build) -> list[dict]:
        rows, t0 = [], time.time()
        for kind, q, query, must in EVAL:
            raw = generate(model, build(q, query))
            rows.append({"kind": kind, "question": q, "raw": raw, "ok": score(kind, must, raw)})
        print(label, f"{time.time() - t0:.0f}s", summarize(rows))
        (out / f"eval_{label}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        return rows

    plain = lambda q, query: [{"role": "user", "content": q}]  # noqa: E731  学習データと同じ形（system なし）
    rag = lambda q, query: [{"role": "system", "content": RAG_SYSTEM},  # noqa: E731
                            {"role": "user", "content": f"検索結果:\n{search_glossary(query)}\n\n質問: {q}"}]

    results = {"before": evaluate("before", plain), "rag": evaluate("rag", rag)}

    lora = LoraConfig(r=CONFIG["lora_r"], lora_alpha=CONFIG["lora_alpha"], lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
                      target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"])
    sft = SFTConfig(output_dir=str(out / "ckpt"), num_train_epochs=CONFIG["num_train_epochs"], per_device_train_batch_size=4,
                    gradient_accumulation_steps=2, learning_rate=CONFIG["lr"], lr_scheduler_type="cosine",
                    warmup_steps=CONFIG["warmup_steps"], logging_steps=10, save_strategy="no", max_length=CONFIG["max_seq_len"],
                    packing=False, report_to="none", seed=CONFIG["seed"])
    model.config.use_cache = False
    trainer = SFTTrainer(model=model, args=sft, train_dataset=Dataset.from_list(train), peft_config=lora, processing_class=tok)
    trainer.model.print_trainable_parameters()
    t0 = time.time()
    trainer.train()
    train_seconds = round(time.time() - t0, 1)
    model = trainer.model
    model.config.use_cache = True
    model.eval()
    model.save_pretrained(out / "adapter")
    results["after"] = evaluate("after", plain)

    losses = [{"step": h["step"], "loss": round(h["loss"], 4)} for h in trainer.state.log_history if "loss" in h]
    result = {"config": CONFIG, "n_train": len(train), "train_seconds": train_seconds, "losses": losses,
              "summary": {k: summarize(v) for k, v in results.items()}}
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


def summarize(rows: list[dict]) -> dict:
    kinds = ["seen", "paraphrase", "absent"]
    return {k: f"{sum(r['ok'] for r in rows if r['kind'] == k)}/{sum(r['kind'] == k for r in rows)}" for k in kinds}


if __name__ == "__main__":
    main()
