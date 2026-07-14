"""Чанкинг текста с разбиением по предложениям, размер в символах.

Алгоритм:
1. Разбить текст на параграфы (по двойному переносу строки).
2. Каждый параграф — на предложения (по . ! ? + заглавная, ; — и т.д.).
3. Собирать чанки по символам (max_chars=500, overlap=50).
4. Длинные предложения (>1.5 от max_chars) разрезать по переносам строк.
"""

import re

_SENTENCE_SPLIT_RE = re.compile(
    r"(?<=[.!?])\s+(?=[А-ЯЁA-Z])"
    r"|(?<=;)\s*\n(?=\s*—)"
    r"|(?<=:)\s*\n(?=\s*—)"
)


async def sentence_aware_chunking(
    text: str,
    max_chars: int = 500,
    overlap: int = 50,
) -> list[dict]:
    if not text or not text.strip():
        return []

    paragraphs = re.split(r"\n\s*\n", text)
    sentences = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        parts = _SENTENCE_SPLIT_RE.split(para)
        for part in parts:
            part = part.strip()
            if part:
                sentences.append(part)

    if not sentences:
        return []

    chunks: list[dict] = []
    current_sentences: list[str] = []
    current_chars = 0

    for sent in sentences:
        sent_chars = len(sent)

        if sent_chars > max_chars * 1.5:
            sub_lines = [s.strip() for s in sent.split("\n") if s.strip()]
            if len(sub_lines) > 1:
                for line in sub_lines:
                    line_chars = len(line)
                    if current_chars + line_chars > max_chars and current_sentences:
                        chunk_text = " ".join(current_sentences)
                        chunks.append({
                            "content": chunk_text.strip(),
                            "chunk_order_index": len(chunks),
                            "chars": current_chars,
                        })
                        current_sentences = []
                        current_chars = 0
                    current_sentences.append(line)
                    current_chars += line_chars
                continue

        if current_chars + sent_chars > max_chars and current_sentences:
            chunk_text = " ".join(current_sentences)
            chunks.append({
                "content": chunk_text.strip(),
                "chunk_order_index": len(chunks),
                "chars": current_chars,
            })

            overlap_sentences = []
            overlap_chars = 0
            for s in reversed(current_sentences):
                s_chars = len(s)
                if overlap_chars + s_chars <= overlap or not overlap_sentences:
                    overlap_sentences.insert(0, s)
                    overlap_chars += s_chars
                else:
                    break

            current_sentences = list(overlap_sentences)
            current_chars = overlap_chars

        current_sentences.append(sent)
        current_chars += sent_chars

    if current_sentences:
        chunk_text = " ".join(current_sentences)
        chunks.append({
            "content": chunk_text.strip(),
            "chunk_order_index": len(chunks),
            "chars": current_chars,
        })

    return chunks
