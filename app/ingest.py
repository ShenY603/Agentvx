"""文档摄入脚本：解析 docs/ 文档 → 分块 → 向量化 → 写入 PGVector。

用法：
    python -m app.ingest                # 全量/增量摄入 docs/
    python -m app.ingest --reset       # 先清空 collection 再摄入
    python -m app.ingest --docs 路径    # 指定文档目录
"""

import argparse
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import PROJECT_ROOT, settings
from app.vector_store import add_documents, delete_collection

# 中文友好的分块分隔符：优先在段落/句子边界切
_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""]


def _load_pdf(path: Path) -> list[Document]:
    import pymupdf

    pdf = pymupdf.open(str(path))
    try:
        docs: list[Document] = []
        for i, page in enumerate(pdf):
            text = page.get_text().strip()
            if text:
                docs.append(
                    Document(page_content=text, metadata={"source": str(path), "page": i + 1})
                )
        return docs
    finally:
        pdf.close()


def _load_docx(path: Path) -> list[Document]:
    import docx2txt

    text = docx2txt.process(str(path)).strip()
    if not text:
        return []
    return [Document(page_content=text, metadata={"source": str(path)})]


def _load_text(path: Path) -> list[Document]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    return [Document(page_content=text, metadata={"source": str(path)})]


def _relative_source(doc: Document, docs_dir: Path) -> Document:
    """把 source 从绝对路径归一化为相对 docs_dir 的路径，便于引用展示。"""
    try:
        doc.metadata["source"] = str(Path(doc.metadata["source"]).relative_to(docs_dir))
    except ValueError:
        pass
    return doc


def load_documents(docs_dir: Path) -> list[Document]:
    """遍历目录，按扩展名加载 PDF / Word / Markdown / txt。"""
    docs: list[Document] = []
    for path in sorted(docs_dir.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        try:
            if suffix == ".pdf":
                loaded = _load_pdf(path)
            elif suffix == ".docx":
                loaded = _load_docx(path)
            elif suffix in {".md", ".markdown", ".txt"}:
                loaded = _load_text(path)
            else:
                continue
        except Exception as exc:  # 单个文件失败不中断整体摄入
            print(f"[skip] {path.name}: {exc}")
            continue
        docs.extend(_relative_source(doc, docs_dir) for doc in loaded)
        print(f"[loaded] {path.name}: {len(loaded)} 段")
    return docs


def split_documents(docs: list[Document]) -> list[Document]:
    """按 chunk_size / overlap 分块，保留 source/page 元数据。"""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=_SEPARATORS,
    )
    return splitter.split_documents(docs)


def main() -> None:
    parser = argparse.ArgumentParser(description="摄入文档到 pgvector")
    parser.add_argument("--docs", type=Path, default=PROJECT_ROOT / "docs")
    parser.add_argument("--reset", action="store_true", help="先清空 collection 再摄入")
    args = parser.parse_args()

    if args.reset:
        delete_collection()
        print("已清空 collection")

    docs = load_documents(args.docs)
    if not docs:
        print("未找到可摄入的文档（支持 pdf/docx/md/txt）")
        return

    chunks = split_documents(docs)
    add_documents(chunks)
    print(f"完成：{len(docs)} 个文档 → {len(chunks)} 个分块 → collection '{settings.collection_name}'")


if __name__ == "__main__":
    main()
