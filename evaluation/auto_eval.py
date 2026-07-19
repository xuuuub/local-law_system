"""
自动评估脚本 —— 用 LLM 对比 expected_answer 和 model_output 生成 evaluation_note

用法：
    python evaluation/auto_eval.py
    python evaluation/auto_eval.py --model qwen2.5:14b
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import argparse
from datetime import datetime

EVAL_PROMPT = """你是一个法律问答评估专家。请对比"标准答案"和"模型回答"，给出一句简短评价（20字以内）。

评价标准：
- 核心结论是否正确
- 是否引用了具体的法条编号
- 是否有明显错误或遗漏
- 是否冗余或含糊

只返回评价文本，不要加任何前缀。

标准答案：{expected}
模型回答：{model_output}

评价："""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen2.5:3b")
    parser.add_argument("--input", default="evaluation/test_results.json")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=None)
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = Path(__file__).resolve().parent.parent / args.input

    with open(input_path, "r", encoding="utf-8") as f:
        results = json.load(f)

    end = min(args.end or len(results), len(results))
    results = results[args.start:end]
    total = len(results)

    print(f"自动评估: 模型={args.model}, 范围=[{args.start}:{end}], 共 {total} 条")
    print(f"开始: {datetime.now().strftime('%H:%M:%S')}")

    from ollama import chat

    success = 0
    for i, item in enumerate(results):
        if item.get("evaluation_note"):
            continue  # 已评估跳过

        expected = item.get("expected_answer", "")
        model_output = item.get("model_output", "")

        if not expected or not model_output:
            continue

        # 截断过长的文本
        prompt = EVAL_PROMPT.format(
            expected=expected[:300],
            model_output=model_output[:500],
        )

        try:
            resp = chat(
                model=args.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0},
            )
            note = resp["message"]["content"].strip().strip("'").strip('"')
            item["evaluation_note"] = note
            success += 1
            print(f"  [{i+1}/{total}] {note[:60]}")
        except Exception as e:
            item["evaluation_note"] = f"评估失败: {e}"
            print(f"  [{i+1}/{total}] 失败: {e}")

    # 写回（按 question+mode 唯一匹配，兼容多模式结果）
    with open(input_path, "r", encoding="utf-8") as f:
        full_results = json.load(f)

    for item in results:
        item_key = (item["question"], item.get("mode", ""))
        for fr in full_results:
            fr_key = (fr["question"], fr.get("mode", ""))
            if fr_key == item_key:
                fr["evaluation_note"] = item["evaluation_note"]
                break

    with open(input_path, "w", encoding="utf-8") as f:
        json.dump(full_results, f, ensure_ascii=False, indent=2)

    print(f"\n完成: {success}/{total} 已评估")
    print(f"结束: {datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    main()
