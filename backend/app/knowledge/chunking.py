"""文本切分: 段落优先 + 递归字符 + 重叠窗口.

中文以字符计 (无空格分词), 兼顾段落语义边界.
"""


def chunk_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 80,
) -> list[str]:
    """把长文本切分为带重叠的块, 保持段落边界优先."""
    if not text.strip():
        return []
    text = text.strip()
    if len(text) <= chunk_size:
        return [text]

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        # 单段超长: 内部按字符硬切 (递归字符切分)
        while len(para) > chunk_size:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(para[:chunk_size])
            para = para[chunk_size:]
        if not current:
            current = para
        elif len(current) + 1 + len(para) <= chunk_size:
            current = f"{current}\n{para}"
        else:
            chunks.append(current)
            current = para

    if current:
        chunks.append(current)

    # 重叠窗口: 相邻块拼接尾部/头部, 保证检索上下文连续
    if len(chunks) > 1 and overlap > 0:
        merged: list[str] = []
        for i, chunk in enumerate(chunks):
            if i == 0:
                merged.append(chunk)
                continue
            prev = merged[-1]
            tail = prev[-overlap:]
            merged.append(f"{tail}{chunk}")
        chunks = merged

    return chunks


def count_tokens(text: str) -> int:
    """近似 token 数: 中文按字, 英文按词 (粗略估算)."""
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len([t for t in text.replace(" ", "").split() if not any("\u4e00" <= c <= "\u9fff" for c in t)])
    return max(1, cjk + other // 3)
