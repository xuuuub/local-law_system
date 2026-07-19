"""
法律智能问答 - Streamlit 前端

启动：
    streamlit run frontend/streamlit_app.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import requests
import uuid

API_URL = "http://localhost:8000"

# 每个 Streamlit 浏览器会话生成唯一 session_id，隔离对话历史
if "session_id" not in st.session_state:
    st.session_state.session_id = uuid.uuid4().hex[:8]

st.set_page_config(page_title="法律智能问答", page_icon="⚖️", layout="wide")

# ==================== 侧边栏 ====================

with st.sidebar:
    st.title("⚖️ 法律智能问答")
    st.markdown("基于本地 LLM + LangChain 多 Agent")

    st.divider()

    model = st.selectbox(
        "模型",
        ["qwen2.5:3b", "qwen2.5:7b", "qwen2.5:14b"],
        index=0,
        help="3b 快 / 14b 准",
    )

    mode = st.selectbox(
        "Agent 模式",
        ["sequential", "parallel", "hierarchical"],
        index=0,
        format_func=lambda x: {
            "sequential": "串行模式",
            "parallel": "并行模式",
            "hierarchical": "Agent合作",
        }.get(x, x),
    )

    st.divider()

    # 健康检查
    if st.button("系统状态"):
        try:
            resp = requests.get(f"{API_URL}/health", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                st.success(f"在线 | 索引: {data['index_size']} 条, {data['index_dim']} 维")
            else:
                st.warning("API 异常")
        except Exception:
            st.error("API 未启动")

    st.divider()
    st.caption("法律信息仅供参考，复杂问题请咨询律师")

# ==================== 主界面 ====================

st.title("⚖️ 法律智能问答系统")

# 示例问题
examples = [
    "试用期最长可以约定多久？",
    "未成年人犯罪是否承担刑事责任？",
    "总结一下劳动合同法中关于试用期的核心规定",
    "合同纠纷的诉讼时效是多久？",
    "酒驾的处罚标准是什么？",
]

cols = st.columns(len(examples))
for i, (col, ex) in enumerate(zip(cols, examples)):
    if col.button(ex, key=f"ex_{i}", use_container_width=True):
        st.session_state.prompt = ex

# 输入区
if "prompt" not in st.session_state:
    st.session_state.prompt = ""

prompt = st.text_area(
    "输入你的法律问题",
    value=st.session_state.prompt,
    height=80,
    placeholder="例如：试用期最长可以约定多久？",
    label_visibility="collapsed",
)

col1, col2 = st.columns([1, 5])
with col1:
    send = st.button("发送", type="primary", use_container_width=True)
with col2:
    if st.button("清空对话", use_container_width=True):
        st.session_state.messages = []
        # 同步清空后端对话历史
        try:
            requests.post(f"{API_URL}/clear_session",
                          params={"session_id": st.session_state.session_id}, timeout=5)
        except Exception:
            pass  # 后端未启动时静默忽略

# 初始化消息历史
if "messages" not in st.session_state:
    st.session_state.messages = []

# ==================== 对话逻辑 ====================

if send and prompt.strip():
    st.session_state.prompt = ""
    with st.spinner("思考中..."):
        try:
            resp = requests.post(
                f"{API_URL}/chat",
                json={
                    "question": prompt.strip(),
                    "mode": mode,
                    "model": model,
                    "session_id": st.session_state.session_id,
                },
                timeout=90,
            )
            if resp.status_code == 200:
                data = resp.json()
                st.session_state.messages.append({"role": "user", "content": prompt.strip()})
                st.session_state.messages.append({"role": "assistant", "content": data["answer"]})
            else:
                st.error(f"API 错误: {resp.status_code}")
        except requests.ConnectionError:
            st.error("无法连接 API，请先启动后端: python api/server.py")
        except Exception as e:
            st.error(f"请求失败: {e}")

# ==================== 显示对话 ====================

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


# 底部提示
if not st.session_state.messages:
    st.info("👆 输入问题或点击示例开始")
