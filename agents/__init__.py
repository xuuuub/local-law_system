"""
多 Agent 协作模块

基于 LangChain 实现：
- 检索Agent：ReAct Agent + law_search 工具，搜索 FAISS 向量库
- 问答Agent：LCEL chain，基于法条生成答案
- 总结Agent：LCEL chain，结构化总结法律要点

支持三种模式：
- sequential：串行（检索 → 问答）
- parallel：并行（拆子问题 → 多路检索 → 汇总）
- hierarchical：合作（调度Agent 自主调用 检索/问答/总结 子Agent）

Prompt 统一管理在 rag/prompts.py。
"""
