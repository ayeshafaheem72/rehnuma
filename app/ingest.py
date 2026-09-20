"""Any content in, clean text out.

Accepts a PDF, a plain-text/markdown file, or pasted text. Deliberately boring: the panel
will hand us an unseen document live, so this path has to be fast and impossible to surprise.
"""
import io
import re

import pymupdf

# Roughly 60k characters keeps even a long document inside one comfortable request
# while leaving plenty of room for the concept map response.
MAX_CHARS = 60_000
MAX_PAGES = 80


class IngestError(Exception):
    pass


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    return text.strip()


def _truncate(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_CHARS:
        return text, False
    cut = text[:MAX_CHARS]
    # end on a paragraph break where possible, so we never slice mid-sentence
    last = cut.rfind("\n\n")
    if last > MAX_CHARS * 0.6:
        cut = cut[:last]
    return cut, True


def from_pdf(data: bytes) -> tuple[str, bool]:
    try:
        doc = pymupdf.open(stream=io.BytesIO(data), filetype="pdf")
    except Exception as e:
        raise IngestError("That PDF could not be opened. Is the file complete?") from e
    if doc.needs_pass:
        raise IngestError("That PDF is password protected. Please upload an unlocked copy.")
    pages = []
    for i, page in enumerate(doc):
        if i >= MAX_PAGES:
            break
        pages.append(page.get_text())
    doc.close()
    text = _clean("\n\n".join(pages))
    if len(text) < 200:
        raise IngestError(
            "Almost no text came out of that PDF - it may be a scan of images. "
            "Try a text-based PDF, or paste the text directly."
        )
    return _truncate(text)


def from_text(raw: str) -> tuple[str, bool]:
    text = _clean(raw)
    if len(text) < 200:
        raise IngestError("That is too short to build a learning experience from. "
                          "Please provide at least a couple of paragraphs.")
    return _truncate(text)


def from_upload(filename: str, data: bytes) -> tuple[str, bool]:
    name = (filename or "").lower()
    if name.endswith(".pdf") or data[:5] == b"%PDF-":
        return from_pdf(data)
    if name.endswith((".txt", ".md", ".markdown", ".csv")):
        try:
            return from_text(data.decode("utf-8", errors="replace"))
        except UnicodeDecodeError as e:
            raise IngestError("That file is not readable as text.") from e
    raise IngestError("Unsupported file type. Upload a PDF, .txt or .md file, "
                      "or paste the text instead.")


def title_from(filename: str, text: str) -> str:
    if filename:
        stem = filename.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        stem = re.sub(r"[_-]+", " ", stem).strip()
        if len(stem) > 2:
            return stem[:120]
    first = next((ln.strip() for ln in text.split("\n") if len(ln.strip()) > 8), "Untitled")
    return first[:120]
