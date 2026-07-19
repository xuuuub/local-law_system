"""启动 API 服务"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.server import app
import uvicorn
uvicorn.run(app, host="0.0.0.0", port=8000)
