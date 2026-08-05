"""文档解析器: 将各类文件提取为纯文本.

支持: txt / md / html / pdf (PDF 依赖 pymupdf, 缺失时给出明确提示).
"""
import html.parser
from pathlib import Path

from app.core.exceptions import BizError

SUPPORTED_EXTS = {".txt", ".md", ".markdown", ".html", ".htm", ".pdf"}


class _TextExtractor(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self._parts.append(data.strip())

    def text(self) -> str:
        return "\n".join(self._parts)


def extract_text(file_name: str, raw: bytes) -> str:
    ext = Path(file_name).suffix.lower()
    if ext not in SUPPORTED_EXTS:
        raise BizError(f"不支持的文件类型: {ext}, 支持 {sorted(SUPPORTED_EXTS)}")

    if ext in (".txt", ".md", ".markdown"):
        return _decode(raw)
    if ext in (".html", ".htm"):
        parser = _TextExtractor()
        parser.feed(_decode(raw))
        return parser.text()
    if ext == ".pdf":
        return _extract_pdf(raw)
    raise BizError(f"未实现解析器: {ext}")


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _extract_pdf(raw: bytes) -> str:
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise BizError("解析 PDF 需要安装 pymupdf: pip install pymupdf") from exc

    doc = fitz.open(stream=raw, filetype="pdf")
    parts: list[str] = []
    for page in doc:
        parts.append(page.get_text())
    doc.close()
    text = "\n".join(parts).strip()
    if not text:
        raise BizError("PDF 未提取到文本 (可能是扫描件, 需 OCR, M3 规划)")
    return text


def guess_source_type(file_name: str) -> str:
    ext = Path(file_name).suffix.lower().lstrip(".")
    return {"markdown": "md"}.get(ext, ext or "txt")
