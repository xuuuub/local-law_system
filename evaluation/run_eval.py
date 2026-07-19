"""
批量评估脚本 —— 基于 LangChain 多 Agent 协作（与前端同款链路）

读取 evaluation/test_questions.json 的 102 条测试问题，
逐条通过 AgentOrchestrator（与前端完全相同的链路）运行，
自动填充 retrieved_text + model_output + evaluation_note。

输出格式严格遵循需求.txt 七、测试数据集模板样式（JSON 格式）：
  - question       ：待检索并问答的问题文本
  - expected_answer：人工标注的标准答案
  - retrieved_text ：系统返回的检索段落
  - model_output   ：Agent 生成的最终回答
  - evaluation_note：评价意见

支持三种 Agent 模式，可分别运行或对比运行：
  --mode sequential   串行（检索Agent → 问答Agent）
  --mode parallel     并行（拆子问题 → 多路并发检索 → 问答Agent）
  --mode hierarchical 合作（调度Agent自主决策）
  --mode all          依次运行三种模式，输出对比结果

用法：
    python evaluation/run_eval.py                              # 串行模式，全量
    python evaluation/run_eval.py --mode parallel              # 并行模式
    python evaluation/run_eval.py --mode hierarchical          # 合作模式
    python evaluation/run_eval.py --mode all                   # 三种模式对比
    python evaluation/run_eval.py --start 0 --end 10           # 只跑10条
    python evaluation/run_eval.py --model qwen2.5:7b           # 指定模型
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import time
import argparse
from datetime import datetime

from agents.orchestrator import AgentOrchestrator
from agents.tools import get_retriever
from rag.prompts import build_context_text

MODES = ["sequential", "parallel", "hierarchical"]


def run_single(orch, question, mode, retriever):
    """对一条问题运行指定模式，返回需求.txt格式的结果"""
    try:
        # 1. 检索法条（与前端链路一致：law_search 内部调 FaissRetriever）
        chunks, scores = retriever.search(question, top_k=5)
        retrieved_text = build_context_text(chunks, top_k=5)

        # 2. Agent 生成答案（与前端链路完全一致：AgentOrchestrator.ask）
        model_output = orch.ask(question, mode=mode)

        return {
            "question": question,
            "expected_answer": "",
            "retrieved_text": retrieved_text.strip(),
            "model_output": model_output.strip(),
            "evaluation_note": "",
        }
    except Exception as e:
        return {
            "question": question,
            "expected_answer": "",
            "retrieved_text": "",
            "model_output": f"[ERROR] {str(e)}",
            "evaluation_note": "系统错误",
        }


def run_evaluation(
    questions_file: str = "evaluation/test_questions.json",
    output_file: str = "evaluation/test_results.json",
    model: str = "qwen2.5:3b",
    mode: str = "sequential",
    start: int = 0,
    end: int = None,
):
    # 加载问题
    qf = Path(questions_file)
    if not qf.is_absolute():
        qf = Path(__file__).resolve().parent.parent / questions_file

    with open(qf, "r", encoding="utf-8") as f:
        questions = json.load(f)

    total = len(questions)
    end = min(end or total, total)
    questions = questions[start:end]

    print(f"评估配置: 模型={model}, 模式={mode}, 范围=[{start}:{end}], 共 {len(questions)} 条")
    print(f"开始时间: {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 60)

    # 初始化（与前端同款：AgentOrchestrator + FaissRetriever）
    orch = AgentOrchestrator(model=model)
    retriever = get_retriever()

    if mode == "all":
        # 三种模式对比：对每条问题分别运行三种模式
        results = []
        for i, item in enumerate(questions):
            question = item["question"]
            expected = item.get("expected_answer", "")
            category = item.get("category", "")

            print(f"\n[{start + i + 1}/{end}] ({category}) {question[:50]}...")

            for m in MODES:
                print(f"  [{m}] 运行中...")
                result = run_single(orch, question, m, retriever)
                result["expected_answer"] = expected
                result["mode"] = m          # 附加字段：标记模式
                result["category"] = category  # 附加字段：分类
                results.append(result)

            # 每条问题后保存进度
            _save_progress(results, output_file, qf)

        print(f"\n{'=' * 60}")
        print(f"完成: 三种模式 × {len(questions)} 条 = {len(results)} 条结果")

    else:
        # 单一模式
        if mode not in MODES:
            print(f"错误: 未知模式 '{mode}'，可选: sequential/parallel/hierarchical/all")
            return

        results = []
        success = 0

        for i, item in enumerate(questions):
            question = item["question"]
            expected = item.get("expected_answer", "")
            category = item.get("category", "")

            print(f"\n[{start + i + 1}/{end}] ({category}) {question[:50]}...")

            result = run_single(orch, question, mode, retriever)
            result["expected_answer"] = expected
            result["mode"] = mode          # 附加字段：标记模式
            result["category"] = category  # 附加字段：分类

            if not result["model_output"].startswith("[ERROR]"):
                success += 1
                print(f"  [OK] 成功 ({success})")
            else:
                print(f"  [FAIL] {result['model_output'][:80]}")

            results.append(result)

            # 每10条保存进度
            if (i + 1) % 10 == 0:
                _save_progress(results, output_file, qf)

        print(f"\n{'=' * 60}")
        print(f"完成: {success}/{len(questions)} 成功")

    # 最终保存
    _save_progress(results, output_file, qf)
    print(f"结果: {Path(output_file).resolve() if not Path(output_file).is_absolute() else output_file}")
    print(f"结束时间: {datetime.now().strftime('%H:%M:%S')}")


def _save_progress(results, output_file, questions_file):
    """保存当前进度到输出文件"""
    of = Path(output_file)
    if not of.is_absolute():
        of = Path(__file__).resolve().parent.parent / output_file
    of.parent.mkdir(parents=True, exist_ok=True)

    # 合并：先加载已有结果，追加新结果（支持断点续跑）
    existing = []
    if of.exists():
        try:
            existing = json.load(open(of, "r", encoding="utf-8"))
        except Exception:
            existing = []

    # 按question+mode去重，保留新结果
    new_keys = {(r["question"], r.get("mode", "")) for r in results}
    merged = [e for e in existing if (e["question"], e.get("mode", "")) not in new_keys]
    merged.extend(results)

    with open(of, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="批量法律问答评估（多Agent协作）")
    parser.add_argument("--model", default="qwen2.5:3b", help="Ollama 模型名")
    parser.add_argument("--mode", default="sequential",
                        choices=["sequential", "parallel", "hierarchical", "all"],
                        help="Agent模式: sequential/parallel/hierarchical/all(三种对比)")
    parser.add_argument("--start", type=int, default=0, help="起始索引")
    parser.add_argument("--end", type=int, default=None, help="结束索引")
    parser.add_argument("--output", default="evaluation/test_results.json", help="输出文件")
    args = parser.parse_args()

    run_evaluation(
        model=args.model,
        mode=args.mode,
        start=args.start,
        end=args.end,
        output_file=args.output,
    )
