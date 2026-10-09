"""ingest 单元测试：只测解析与分块，不依赖数据库和模型。"""

from pathlib import Path

from app.ingest import load_documents, split_documents


def _write(path: Path, name: str, content: str) -> Path:
    p = path / name
    p.write_text(content, encoding="utf-8")
    return p


def test_load_markdown_with_relative_source(tmp_path: Path) -> None:
    _write(tmp_path, "a.md", "第一段\n\n第二段")
    docs = load_documents(tmp_path)
    assert len(docs) == 1
    assert docs[0].metadata["source"] == "a.md"
    assert "第一段" in docs[0].page_content


def test_load_ignores_unsupported_suffix(tmp_path: Path) -> None:
    _write(tmp_path, "a.md", "内容")
    _write(tmp_path, "b.xyz", "应被忽略")
    docs = load_documents(tmp_path)
    assert [d.metadata["source"] for d in docs] == ["a.md"]


def test_split_keeps_source_and_produces_chunks(tmp_path: Path) -> None:
    _write(tmp_path, "a.md", "句子一。句子二。句子三。" * 50)
    docs = load_documents(tmp_path)
    chunks = split_documents(docs)
    assert len(chunks) > 1
    assert all(c.metadata.get("source") == "a.md" for c in chunks)
