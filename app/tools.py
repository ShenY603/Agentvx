"""工具定义与执行：供 agent 调用。"""

import ast
import operator
from datetime import datetime, timedelta, timezone

import httpx
from langchain_core.tools import tool

from app.config import settings
from app.vector_store import search


def _safe_eval(expression: str):
    """安全求值四则运算（仅数字与 + - * / ** 括号）。"""
    allowed = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in allowed:
            return allowed[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in allowed:
            return allowed[type(node.op)](_eval(node.operand))
        raise ValueError("不支持的表达式")

    return _eval(ast.parse(expression, mode="eval"))


def _search_text_and_sources(query: str) -> tuple[str, list[str]]:
    """检索知识库，返回格式化文本与来源列表。"""
    docs = search(query, k=settings.top_k)
    sources: list[str] = []
    parts: list[str] = []
    for i, doc in enumerate(docs, start=1):
        source = doc.metadata.get("source", "未知来源")
        page = doc.metadata.get("page")
        label = f"{source}" + (f" 第{page}页" if page else "")
        sources.append(label)
        parts.append(f"[{i}]（来源：{label}）\n{doc.page_content}")
    text = "\n\n".join(parts) if parts else "未检索到相关内容。"
    return text, sources


def _calc(expression: str) -> str:
    try:
        return f"{expression} = {_safe_eval(expression)}"
    except Exception as exc:
        return f"计算失败：{exc}"


_CHINA_TZ = timezone(timedelta(hours=8))  # 中国 UTC+8，无夏令时


def _time() -> str:
    return datetime.now(_CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _weather(city: str) -> str:
    """查询高德天气实时天气。"""
    key = settings.amap_api_key
    if not key:
        return "未配置高德天气 API Key，无法查询天气。"
    city = (city or "").strip() or settings.default_city
    try:
        resp = httpx.get(
            "https://restapi.amap.com/v3/weather/weatherInfo",
            params={"city": city, "extensions": "base", "key": key},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # 网络/解析异常兜底为文本，不抛出
        return f"天气查询失败：{exc}"
    if data.get("status") != "1" or not data.get("lives"):
        return f"未查询到「{city}」的天气（{data.get('info', '未知错误')}）"
    lives = data["lives"]
    # 城市名可能匹配到多个同名区县（如「西安」→ 黑龙江/吉林的「西安区」+ 陕西「西安市」），优先取市级结果
    city_level = [live for live in lives if (live.get("city") or "").endswith("市")]
    lives = city_level or lives
    lines = []
    for live in lives[:3]:
        location = f"{live.get('province', '')}{live.get('city', '')}"
        lines.append(
            f"{location}：{live.get('weather', '')}，气温 {live.get('temperature', '')}℃，"
            f"湿度 {live.get('humidity', '')}%，{live.get('winddirection', '')}风"
            f"{live.get('windpower', '')}级（{live.get('reporttime', '')}）"
        )
    return "\n".join(lines)


def _web_search(query: str) -> tuple[str, list[str]]:
    """博查网页搜索，返回格式化文本与来源列表。"""
    key = settings.bocha_api_key
    if not key:
        return "未配置博查搜索 API Key，无法搜索网页。", []
    try:
        resp = httpx.post(
            "https://api.bochaai.com/v1/web-search",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"query": query, "count": 8, "summary": True},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return f"网页搜索失败：{exc}", []
    if data.get("code") != 200:
        return f"网页搜索出错：{data.get('msg') or '未知错误'}", []
    results = (((data.get("data") or {}).get("webPages")) or {}).get("value") or []
    if not results:
        return "未搜索到相关内容。", []
    parts: list[str] = []
    sources: list[str] = []
    for i, item in enumerate(results, start=1):
        title = item.get("name") or item.get("url") or "无标题"
        url = item.get("url") or ""
        summary = item.get("summary") or item.get("snippet") or ""
        parts.append(f"[{i}] {title}\n{url}\n{summary}".strip())
        sources.append(f"{title}（{url}）" if url else title)
    return "\n\n".join(parts), sources


# ---- 工具 schema（供 bind_tools）----


@tool
def search_knowledge_base(query: str) -> str:
    """检索知识库，返回相关文档片段。知识/文档类问题需要查资料时使用，query 为检索关键词。"""
    return _search_text_and_sources(query)[0]


@tool
def calculator(expression: str) -> str:
    """计算数学表达式（支持 + - * / ** 与括号），返回结果。"""
    return _calc(expression)


@tool
def get_current_time() -> str:
    """返回当前日期和时间。"""
    return _time()


@tool
def get_weather(city: str = "") -> str:
    """查询指定城市的实时天气。city 为城市名（如「西安」「北京」），用户未指定时传空串查默认城市。"""
    return _weather(city)


@tool
def web_search(query: str) -> str:
    """搜索网页获取最新/实时信息。query 为搜索关键词。"""
    return _web_search(query)[0]


TOOLS = [search_knowledge_base, calculator, get_current_time, get_weather, web_search]


def run_tool(name: str, args: dict) -> tuple[str, list[str]]:
    """按名字执行工具，返回 (文本结果, 新增来源列表)。"""
    if name == "search_knowledge_base":
        return _search_text_and_sources(args.get("query", ""))
    if name == "calculator":
        return _calc(args.get("expression", "")), []
    if name == "get_current_time":
        return _time(), []
    if name == "get_weather":
        return _weather(args.get("city", "")), []
    if name == "web_search":
        return _web_search(args.get("query", ""))
    return f"未知工具：{name}", []
