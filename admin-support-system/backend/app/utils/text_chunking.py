import re
from typing import List

MAX_CHUNK_SIZE = 500  # characters (~100-125 tokens)
CHUNK_OVERLAP = 50


def chunk_text(
    text: str,
    max_size: int = MAX_CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> List[str]:
    """
    Split text into chunks respecting sentence boundaries.
    Falls back to word-level splitting for very long sentences.
    """
    if not text or not text.strip():
        return []

    text = text.strip()
    if len(text) <= max_size:
        return [text]

    # Split on sentence boundaries
    sentences = re.split(r"(?<=[.!?])\s+", text)

    chunks: List[str] = []
    current = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # Sentence fits in current chunk
        if len(current) + len(sentence) + 1 <= max_size:
            current = (current + " " + sentence).strip() if current else sentence
        else:
            # Flush current chunk with overlap tail
            if current:
                chunks.append(current)
                # Keep the tail of current chunk as overlap seed
                tail = current[-overlap:] if len(current) > overlap else current
                current = tail

            # If single sentence exceeds max_size, split by words
            if len(sentence) > max_size:
                words = sentence.split()
                for word in words:
                    if len(current) + len(word) + 1 <= max_size:
                        current = (current + " " + word).strip() if current else word
                    else:
                        if current:
                            chunks.append(current)
                            tail = current[-overlap:] if len(current) > overlap else current
                            current = tail
                        current = word
            else:
                current = sentence

    if current:
        chunks.append(current)

    return chunks
