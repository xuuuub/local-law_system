"""
多 Agent 系统测试脚本

用法：
    python scripts/test_agents.py                              # 交互模式
    python scripts/test_agents.py --query "问题"                # 单次查询
    python scripts/test_agents.py --query "问题" --mode parallel  # 并行模式
    python scripts/test_agents.py --query "问题" --mode hierarchical
    python scripts/test_agents.py --model qwen2.5:14b           # 换大模型
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
from agents.orchestrator import AgentOrchestrator

MODES = ["sequential", "parallel", "hierarchical"]

TEST_QUESTIONS = [
    ("sequential", "试用期最长可以约定多久？"),
    ("sequential", "用人单位什么情况下可以单方解除劳动合同？"),
    ("sequential", "酒驾的处罚标准是什么？"),
    ("parallel", "分别说明劳动合同解除的条件和工伤认定的条件"),
    ("parallel", "未成年人的刑事责任和劳动者试用期的规定"),
    ("hierarchical", "总结一下劳动合同法中关于试用期的核心规定"),
    ("hierarchical", "合同纠纷的诉讼时效是多久？如果超过时效还可以起诉吗？"),
    ("hierarchical", "试用期被违法约定，劳动者应该怎么维权，能拿到多少赔偿？"),
]


def run_single(orch: AgentOrchestrator, query: str, mode: str):
    print(f"[模式: {mode}] 问题：{query}\n")
    result = orch.ask(query, mode=mode)
    print("回答：")
    print(result)
    print()


def run_interactive(orch: AgentOrchestrator):
    print("=" * 60)
    print("法律多 Agent 协作问答系统 (LangChain + qwen2.5)")
    print("=" * 60)
    print("可用命令：")
    print("  直接输入问题 → sequential（串行）")
    print("  :s 问题      → sequential（串行）")
    print("  :p 问题      → parallel（并行）")
    print("  :h 问题      → hierarchical（Agent合作）")
    print("  list         → 列出测试问题")
    print("  exit         → 退出")
    print("=" * 60)

    session_id = "interactive"

    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue
        if user_input.lower() == "exit":
            print("再见！")
            break
        if user_input.lower() == "list":
            print("\n测试问题：")
            for i, (m, q) in enumerate(TEST_QUESTIONS, 1):
                print(f"  {i}. [{m}] {q}")
            continue

        # 解析模式前缀
        if user_input.startswith(":s "):
            mode, query = "sequential", user_input[3:]
        elif user_input.startswith(":h "):
            mode, query = "hierarchical", user_input[3:]
        elif user_input.startswith(":p "):
            mode, query = "parallel", user_input[3:]
        else:
            mode, query = "sequential", user_input

        print(f"\n[模式: {mode}]")
        result = orch.ask(query, mode=mode)
        print(result)


def main():
    parser = argparse.ArgumentParser(description="多 Agent 法律问答测试")
    parser.add_argument("--query", "-q", type=str, default=None, help="问题")
    parser.add_argument("--mode", "-m", type=str, default="sequential",
                        choices=MODES, help="Agent 模式")
    parser.add_argument("--model", type=str, default="qwen2.5:3b", help="Ollama 模型")
    parser.add_argument("--list", "-l", action="store_true", help="列出测试问题")
    args = parser.parse_args()

    if args.list:
        for i, (m, q) in enumerate(TEST_QUESTIONS, 1):
            print(f"  {i}. [{m}] {q}")
        return

    print(f"加载多 Agent 系统 (模型: {args.model})...")
    orch = AgentOrchestrator(model=args.model)

    if args.query:
        run_single(orch, args.query, args.mode)
    else:
        run_interactive(orch)


if __name__ == "__main__":
    main()
