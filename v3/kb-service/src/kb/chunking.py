import re

_SENTENCE_SPLIT_RE = re.compile(
    r"(?<=[.!?])\s+(?=[А-ЯЁA-Z])"
    r"|(?<=;)\s*\n(?=\s*—)"
    r"|(?<=:)\s*\n(?=\s*—)"
)


def _default_tokenizer(text: str) -> int:
    return len(text.split())


async def sentence_aware_chunking(
    text: str,
    chunk_size: int = 300,
    overlap: int = 30,
    tokenizer=None,
) -> list[dict]:
    if not text or not text.strip():
        return []

    count_tokens = tokenizer if tokenizer else _default_tokenizer

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
    current_tokens = 0

    for sent in sentences:
        sent_tokens = count_tokens(sent)

        if sent_tokens > chunk_size * 1.5:
            sub_lines = [s.strip() for s in sent.split("\n") if s.strip()]
            if len(sub_lines) > 1:
                for line in sub_lines:
                    line_tokens = count_tokens(line)
                    if current_tokens + line_tokens > chunk_size and current_sentences:
                        chunk_text = " ".join(current_sentences)
                        chunks.append({
                            "content": chunk_text.strip(),
                            "chunk_order_index": len(chunks),
                            "tokens": current_tokens,
                            "token_count": current_tokens,
                        })
                        current_sentences = []
                        current_tokens = 0
                    current_sentences.append(line)
                    current_tokens += line_tokens
                continue

        if current_tokens + sent_tokens > chunk_size and current_sentences:
            chunk_text = " ".join(current_sentences)
            chunks.append({
                "content": chunk_text.strip(),
                "chunk_order_index": len(chunks),
                "tokens": current_tokens,
                "token_count": current_tokens,
            })

            overlap_sentences = []
            overlap_tokens = 0
            for s in reversed(current_sentences):
                s_tok = count_tokens(s)
                if overlap_tokens + s_tok <= overlap or not overlap_sentences:
                    overlap_sentences.insert(0, s)
                    overlap_tokens += s_tok
                else:
                    break

            current_sentences = list(overlap_sentences)
            current_tokens = overlap_tokens

        current_sentences.append(sent)
        current_tokens += sent_tokens

    if current_sentences:
        chunk_text = " ".join(current_sentences)
        chunks.append({
            "content": chunk_text.strip(),
            "chunk_order_index": len(chunks),
            "tokens": current_tokens,
            "token_count": current_tokens,
        })

    return chunks
