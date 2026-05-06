import re

from fastapi import HTTPException

MAX_QUERY_LENGTH = 1000

# Common prompt-injection patterns
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"forget\s+(all\s+)?previous",
    r"disregard\s+(all\s+)?previous",
    r"you\s+are\s+now\s+a",
    r"act\s+as\s+(a|an)\s+",
    r"pretend\s+(you\s+are|to\s+be)",
    r"new\s+system\s+prompt",
    r"<\s*script",
    r"</?\s*[a-zA-Z]+\s*>",
    r"(\beval\b|\bexec\b|\bimport\b).*\(",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]


def sanitize_query(query: str) -> str:
    """
    Validate and sanitize a user query to prevent prompt injection.
    Raises HTTPException(400) for invalid input.
    Returns the sanitized query string.
    """
    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    query = query.strip()

    if len(query) > MAX_QUERY_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Query too long. Maximum {MAX_QUERY_LENGTH} characters allowed.",
        )

    for pattern in _COMPILED:
        if pattern.search(query):
            raise HTTPException(
                status_code=400,
                detail="Invalid query content detected.",
            )

    # Strip characters commonly used for injection; keep normal punctuation
    query = re.sub(r"[^\w\s\.,?!:;'\"\-()]", " ", query)
    query = re.sub(r"\s+", " ", query).strip()

    return query
