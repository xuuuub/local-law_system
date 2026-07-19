"""
Agent 编排器 —— 基于 LangChain 1.x 的多 Agent 协作

三种模式：
- sequential：串行 —— 检索Agent → 问答Agent
- parallel：  并行 —— 拆子问题 → 多路并发检索 → 问答Agent 汇总
- hierarchical：合作 —— 调度Agent + 检索/问答/总结子Agent

依赖（langchain 1.x 新 API）：
- langchain.agents.create_agent  （返回 LangGraph compiled agent）
- langchain_ollama.ChatOllama
- LCEL chain（问答/总结 Agent）
- 复用 rag.prompts 的模板（prompt 与 agent 打通）
"""
import sys
import os
import re
from pathlib import Path
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Ollama 走本地，无需 OpenAI key
os.environ.setdefault("OPENAI_API_KEY", "no-key")

# 必须在 langchain / huggingface_hub 被 import 之前加载 config，
# 使 HF_ENDPOINT / HF_HUB_OFFLINE 等环境变量及时生效（config.py 内设置）
import config  # noqa: F401

from langchain_ollama import ChatOllama
from langchain.agents import create_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from agents.tools import law_search, get_retriever
from rag.prompts import (
    QA_TASK_TEMPLATE,
    SUMMARY_TASK_TEMPLATE,
    RETRIEVAL_TASK_TEMPLATE,
    build_context_text,
)


class AgentOrchestrator:
    """LangChain 1.x 多 Agent 编排器"""

    def __init__(self, model: str = "qwen2.5:3b", temperature: float = 0.1):
        self.model = model
        self.temperature = temperature
        # ChatOllama：连接本地 Ollama 服务，支持 tool calling
        self.llm = ChatOllama(
            model=model,
            temperature=temperature,
            base_url="http://localhost:11434",
            timeout=60,            # 缩短超时：180→60秒，避免卡死演示
            num_retries=2,         # Ollama 崩溃时自动重试2次
        )
        # 预加载检索器（首次加载 embedding 模型耗时）
        get_retriever()
        self._sessions: Dict[str, List[Dict]] = {}

    # ============ Agent 构造 ============

    def _retrieval_agent(self):
        """检索 Agent：LangGraph agent + law_search 工具，LLM 自主决定检索"""
        return create_agent(
            model=self.llm,
            tools=[law_search],
            system_prompt=RETRIEVAL_TASK_TEMPLATE.replace("{question}", ""),
        )

    def _qa_chain(self):
        """问答 Agent：LCEL chain（QA_TASK_TEMPLATE | llm）"""
        prompt = ChatPromptTemplate.from_template(QA_TASK_TEMPLATE)
        return prompt | self.llm | StrOutputParser()

    def _summary_chain(self):
        """总结 Agent：LCEL chain（SUMMARY_TASK_TEMPLATE | llm）"""
        prompt = ChatPromptTemplate.from_template(SUMMARY_TASK_TEMPLATE)
        return prompt | self.llm | StrOutputParser()

    def _orchestrator_agent(self):
        """
        调度 Agent：LangGraph agent，把检索/问答/总结包装成工具，
        由 LLM 自主决策调用哪个子 Agent，体现"合作"。
        """
        return create_agent(
            model=self.llm,
            tools=[
                self._make_retrieve_tool(),
                self._make_answer_tool(),
                self._make_summarize_tool(),
            ],
            system_prompt=(
                "你是法律智能调度员。分析用户问题后，决定调用哪个工具：\n"
                "- retrieve_laws：检索法律条文\n"
                "- answer_question：基于法条回答问题\n"
                "- summarize_laws：结构化总结法条\n"
                "一般流程：先 retrieve_laws 检索，再 answer_question 回答；"
                "若用户要总结/概括/列要点，调用 summarize_laws。"
            ),
        )

    # ============ 调度 Agent 的子工具（包装子 Agent）============

    def _make_retrieve_tool(self):
        from langchain_core.tools import tool as tool_dec

        @tool_dec
        def retrieve_laws(question: str) -> str:
            """检索与问题相关的法律条文，返回法条原文（含法律名和条款编号）。
            当需要查找法律依据时调用。"""
            try:
                retriever = get_retriever()
                chunks, _ = retriever.search(question, top_k=5)
                if not chunks:
                    return "未检索到相关法条"
                return build_context_text(chunks)
            except Exception as e:
                return f"检索失败：{e}"
        return retrieve_laws

    def _make_answer_tool(self):
        from langchain_core.tools import tool as tool_dec

        @tool_dec
        def answer_question(question: str) -> str:
            """基于已检索到的法律条文回答用户问题。
            需要先调用 retrieve_laws 获取法条后再调用本工具。"""
            try:
                retriever = get_retriever()
                chunks, _ = retriever.search(question, top_k=5)
                context = build_context_text(chunks)
                chain = self._qa_chain()
                return chain.invoke({"context": context, "question": question})
            except Exception as e:
                return f"问答失败：{e}"
        return answer_question

    def _make_summarize_tool(self):
        from langchain_core.tools import tool as tool_dec

        @tool_dec
        def summarize_laws(question: str) -> str:
            """检索并结构化总结法律条文。当用户要求总结/概括/列要点时调用。"""
            try:
                retriever = get_retriever()
                chunks, _ = retriever.search(question, top_k=5)
                context = build_context_text(chunks)
                chain = self._summary_chain()
                return chain.invoke({"context": context})
            except Exception as e:
                return f"总结失败：{e}"
        return summarize_laws

    # ============ 调用 LangGraph agent 的辅助方法 ============

    @staticmethod
    def _invoke_agent(agent, user_input: str) -> str:
        """统一调用 LangGraph agent 并提取最终文本"""
        result = agent.invoke({"messages": [{"role": "user", "content": user_input}]})
        msgs = result.get("messages", [])
        if msgs:
            last = msgs[-1]
            # 兼容 BaseMessage 对象和 dict
            return getattr(last, "content", None) or (last.get("content", "") if isinstance(last, dict) else "")
        return ""

    # ============ 三种模式 ============

    def _run_sequential(self, question: str, history_text: str) -> str:
        """串行：检索Agent → 问答Agent"""
        # 1. 检索 Agent（LangGraph，自主调 law_search）拿法条
        context = self._invoke_agent(self._retrieval_agent(), question)
        if not context:
            retriever = get_retriever()
            chunks, _ = retriever.search(question, top_k=5)
            context = build_context_text(chunks)
        if history_text:
            context = f"[对话历史]\n{history_text}\n\n" + context
        # 2. 问答 Agent 生成答案（复用 prompts.QA_TASK_TEMPLATE）
        chain = self._qa_chain()
        return chain.invoke({"context": context, "question": question})

    def _run_parallel(self, question: str, history_text: str) -> str:
        """
        并行：拆子问题 → 多路并发检索 → 问答Agent 汇总
        （ThreadPoolExecutor 真并行执行多路检索）
        拆分失败时自动降级为串行，并在答案末尾标注。
        """
        sub_questions = self._split_question(question)
        if len(sub_questions) <= 1:
            # 拆分失败，降级为串行
            answer = self._run_sequential(question, history_text)
            return answer + "\n\n⚠️ 注：问题拆分未成功，已自动降级为串行模式。"

        retriever = get_retriever()

        def _search_one(q: str) -> str:
            chunks, _ = retriever.search(q, top_k=3)
            return build_context_text(chunks)

        # 真并行：ThreadPoolExecutor 并发检索
        with ThreadPoolExecutor(max_workers=len(sub_questions)) as pool:
            results = list(pool.map(_search_one, sub_questions))

        context = "\n---\n".join(results)
        if history_text:
            context = f"[对话历史]\n{history_text}\n\n" + context
        chain = self._qa_chain()
        return chain.invoke({"context": context, "question": question})

    def _run_hierarchical(self, question: str, history_text: str) -> str:
        """合作：调度Agent 自主决策调用检索/问答/总结 子Agent"""
        prompt_input = question
        if history_text:
            prompt_input = f"[对话历史]\n{history_text}\n\n问题：{question}"
        return self._invoke_agent(self._orchestrator_agent(), prompt_input)

    def _split_question(self, question: str) -> List[str]:
        """用 LLM 把问题拆成 2~3 个子关键词/子问题"""
        try:
            from ollama import chat
            resp = chat(
                model=self.model,
                messages=[{"role": "user",
                           "content": f"把下面问题拆为2~3个检索关键词，每行一个，不要编号：\n{question}"}],
                options={"temperature": 0},
            )
            raw_lines = resp["message"]["content"].split("\n")
            # 清洗编号前缀：去掉 "1." "2、" "一、" "（1）" 等中英文编号
            subs = []
            for line in raw_lines:
                cleaned = re.sub(r'^[\d]+[.、)\s]+|^[一二三四五六七八九十]+[、.\s]+|^[(\d]+\)\s*', '', line.strip())
                cleaned = cleaned.strip()
                if cleaned and len(cleaned) > 1:
                    subs.append(cleaned)
            subs = subs[:3]
            return subs if len(subs) > 1 else [question]
        except Exception:
            return [question]

    # ============ 对外接口 ============

    def ask(self, question: str, mode: str = "sequential",
            history_text: str = "") -> str:
        if mode == "sequential":
            return self._run_sequential(question, history_text)
        elif mode == "parallel":
            return self._run_parallel(question, history_text)
        elif mode == "hierarchical":
            return self._run_hierarchical(question, history_text)
        raise ValueError(f"未知模式: {mode}（可选 sequential/parallel/hierarchical）")

    def chat(self, question: str, session_id: str = "default",
             mode: str = "sequential") -> str:
        if session_id not in self._sessions:
            self._sessions[session_id] = []
        history = self._sessions[session_id]
        history_text = ""
        if history:
            history_text = "\n".join(
                f"用户：{h['q']}\n助手：{h['a']}" for h in history[-5:])
        answer = self.ask(question, mode=mode, history_text=history_text)
        history.append({"q": question, "a": answer})
        if len(history) > 10:
            self._sessions[session_id] = history[-10:]
        return answer

    def clear_session(self, session_id: str = "default"):
        self._sessions.pop(session_id, None)


if __name__ == "__main__":
    orch = AgentOrchestrator(model="qwen2.5:3b")
    for m in ["sequential", "parallel", "hierarchical"]:
        print(f"\n===== {m} =====")
        print(orch.ask("试用期最长可以约定多久？", mode=m))
