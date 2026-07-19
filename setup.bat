@echo off
chcp 65001 >nul
echo ============================================
echo   法律智能问答系统 - 环境部署
echo ============================================

echo [1/4] 创建 law conda 环境 (Python 3.12)...
conda create -n law python=3.12 -y
if %ERRORLEVEL% NEQ 0 (
    echo [FAIL] conda 创建失败，请检查 conda 是否已安装
    pause
    exit /b 1
)

echo [2/4] 安装 Python 依赖...
conda run -n law pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if %ERRORLEVEL% NEQ 0 (
    echo [FAIL] 依赖安装失败
    pause
    exit /b 1
)

echo [3/4] 下载 Ollama 模型（需要 Ollama 桌面版运行中）...
ollama pull qwen2.5:3b
ollama pull qwen2.5:7b

echo [4/4] 验证环境...
conda run -n law python -c "import torch; print('CUDA:', torch.cuda.is_available()); import faiss; print('FAISS ok'); import crewai; print('CrewAI ok'); from rag.retriever import FaissRetriever; print('Retriever ok')"

echo ============================================
echo   部署完成！
echo   使用方式：
echo   conda activate law
echo   python scripts/run_api.py        (启动后端)
echo   streamlit run frontend/streamlit_app.py  (启动前端)
echo ============================================
pause
