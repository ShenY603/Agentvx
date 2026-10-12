"""工具定义与执行：供 agent 调用。"""

import ast
import operator
from datetime import datetime, timedelta, timezone

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


TOOLS = [search_knowledge_base, calculator, get_current_time]


def run_tool(name: str, args: dict) -> tuple[str, list[str]]:
    """按名字执行工具，返回 (文本结果, 新增来源列表)。"""
    if name == "search_knowledge_base":
        return _search_text_and_sources(args.get("query", ""))
    if name == "calculator":
        return _calc(args.get("expression", "")), []
    if name == "get_current_time":
        return _time(), []
    return f"未知工具：{name}", []
