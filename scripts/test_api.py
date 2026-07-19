"""API 快速测试"""
import requests, json, time

BASE = "http://localhost:8000"

# 健康检查
try:
    r = requests.get(f"{BASE}/health", timeout=5)
    print("health:", r.json())
except:
    print("API 未启动，请先运行: python api/server.py")
    exit(1)

# 测试搜索
r = requests.post(f"{BASE}/search", json={"query": "试用期", "top_k": 3})
data = r.json()
print(f"\nsearch 返回 {len(data['results'])} 条:")
for item in data["results"]:
    print(f"  {item['title']} {item['article_no']} ({item['score']:.4f})")
    print(f"    {item['content'][:80]}...")

# 测试问答
print("\n提问: 试用期最长多久？")
r = requests.post(f"{BASE}/chat", json={
    "question": "试用期最长可以约定多久？",
    "mode": "sequential",
    "model": "qwen2.5:3b"
}, timeout=120)
result = r.json()
print(f"回答:\n{result['answer'][:300]}")
