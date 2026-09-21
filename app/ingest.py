"""Any content in, clean text out.

Accepts a PDF, a plain-text/markdown file, a spreadsheet, a web page, or pasted text.
Deliberately boring: the panel will hand us an unseen document live, so this path has to
be fast and impossible to surprise.
"""
import csv
import html
import io
import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
import zipfile

import pymupdf

# Roughly 60k characters keeps even a long document inside one comfortable request
# while leaving plenty of room for the concept map response.
MAX_CHARS = 60_000
MAX_PAGES = 80

# A fetched page is untrusted and unbounded, so it gets its own ceilings: enough for a
# long article, small enough that a hostile server cannot hold a worker open or fill RAM.
MAX_FETCH_BYTES = 2 * 1024 * 1024
FETCH_TIMEOUT_S = 15
MAX_REDIRECTS = 4
FETCH_UA = "Rehnuma/1.0 (+learning content fetcher)"

# Beyond a couple of hundred rows a table stops being something a learner can be taught
# from, and starts being a database export.
MAX_CSV_ROWS = 200

# Documents need a couple of paragraphs before they are worth teaching from. A page is
# held to a lower bar on purpose: short landing pages are legitimate, and refusing them
# looks like a broken fetcher rather than a thin source.
MIN_URL_CHARS = 120


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


# ---------------------------------------------------------------- spreadsheets

_NUMERIC_CELL = re.compile(r"^[-+]?[\d,. ]*\d[\d,. ]*%?$")


def _csv_dialect(sample: str, filename: str) -> str:
    if (filename or "").lower().endswith(".tsv"):
        return "\t"
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        # A single-column file gives the sniffer nothing to go on; a comma is the safe guess.
        return ","


def _looks_like_header(row: list[str]) -> bool:
    """csv.Sniffer.has_header guesses from column types and gets an all-text table wrong,
    which is exactly the shape people bring us. Judge the row on its own terms instead."""
    cells = [(c or "").strip() for c in row]
    if not cells:
        return False
    # A heading row names its columns; one blank is tolerated for an unnamed index column.
    if sum(1 for c in cells if c) < max(1, len(cells) - 1):
        return False
    if any(len(c) > 60 for c in cells):
        return False        # that length is a sentence of data, not a label
    return not all(_NUMERIC_CELL.match(c) for c in cells if c)


def from_csv(data: bytes, filename: str = "") -> tuple[str, bool]:
    """Turn a table into prose.

    The concept mapper reads meaning, not grids, so handing it raw comma soup wastes the
    request. We state the shape of the table first, then render each row as labelled lines
    that read like short factual paragraphs.
    """
    raw = _decode_text(data)
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    if not raw.strip():
        raise IngestError("That spreadsheet appears to be empty.")

    delimiter = _csv_dialect(raw[:8000], filename)
    try:
        rows = [r for r in csv.reader(io.StringIO(raw), delimiter=delimiter)
                if any((c or "").strip() for c in r)]
    except csv.Error as e:
        raise IngestError("That spreadsheet could not be read. Please check it opens "
                          "in a spreadsheet application, or paste the text instead.") from e
    if not rows:
        raise IngestError("That spreadsheet appears to be empty.")

    header = [(c or "").strip() for c in rows[0]]
    body = rows[1:]
    # A file with no header row would otherwise lose its first record to the column names.
    if not _looks_like_header(rows[0]):
        header = [f"Column {i + 1}" for i in range(len(rows[0]))]
        body = rows
    header = [h or f"Column {i + 1}" for i, h in enumerate(header)]

    if not body:
        raise IngestError("That spreadsheet has column headings but no rows of data.")

    stem = title_from(filename, "") if filename else ""
    if not stem or stem == "Untitled":
        stem = "This table"
    shown = body[:MAX_CSV_ROWS]
    lines = [
        f"{stem}: a table of {len(body)} rows and {len(header)} columns.",
        "The columns are: " + ", ".join(header) + ".",
    ]
    if len(body) > len(shown):
        lines.append(f"The first {len(shown)} rows are described below.")
    lines.append("")

    for n, row in enumerate(shown, start=1):
        lines.append(f"Row {n}")
        for i, name in enumerate(header):
            value = (row[i] or "").strip() if i < len(row) else ""
            if value:
                lines.append(f"{name}: {value}")
        lines.append("")

    text = _clean("\n".join(lines))
    truncated_rows = len(body) > len(shown)
    text, truncated = _truncate(text)
    return text, (truncated or truncated_rows)


# ---------------------------------------------------------------- web pages

def _assert_public_url(url: str) -> str:
    """Refuse anything that could make the server fetch its own private network.

    This runs on the original URL and again on every redirect hop, because a public host
    is free to redirect us at 169.254.169.254 or localhost.
    """
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise IngestError("Please use a web address starting with http:// or https://.")
    host = parts.hostname
    if not host:
        raise IngestError("That does not look like a complete web address.")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError as e:
        raise IngestError("That address could not be found. Please check the link.") from e

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        mapped = getattr(ip, "ipv4_mapped", None)
        if mapped is not None:
            ip = mapped
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified or not ip.is_global):
            raise IngestError("That address is on a private network, so it cannot be "
                              "fetched. Please use a public web page.")
    return url


class _GuardedRedirects(urllib.request.HTTPRedirectHandler):
    """urllib follows redirects for us; this makes it check where it is being sent."""

    max_redirections = MAX_REDIRECTS

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _assert_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_BLOCK_TAGS = re.compile(
    r"(?is)<(script|style|noscript|template|svg|canvas|nav|header|footer|aside|form|"
    r"iframe|object|embed|select|button)\b.*?</\1\s*>"
)
_BREAK_TAGS = re.compile(
    r"(?i)</?(p|div|section|article|li|ul|ol|tr|table|thead|tbody|h[1-6]|blockquote|"
    r"pre|figure|figcaption|br|hr)\b[^>]*>"
)


def _strip_markup(fragment: str) -> str:
    text = _BLOCK_TAGS.sub(" ", fragment)
    # Block boundaries carry the paragraph structure a learner reads by, so keep them.
    text = _BREAK_TAGS.sub("\n\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    # Stripped markup leaves lines holding nothing but spaces, which survive _clean's
    # blank-run rule and would otherwise eat the character budget.
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return _clean(text)


def _html_to_text(raw: str) -> str:
    """A small extractor, on purpose: no parser dependency to install or go wrong."""
    title = ""
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
    if m:
        title = _clean(html.unescape(re.sub(r"(?s)<[^>]+>", " ", m.group(1))))

    body = re.sub(r"(?s)<!--.*?-->", " ", raw)
    body = re.sub(r"(?is)<head\b.*?</head>", " ", body)

    # Where a page marks its own main content, trust it - that one line removes most of
    # the navigation, cookie banners and footer links a regex could never tell apart.
    text = ""
    for pattern in (r"(?is)<main\b[^>]*>(.*?)</main\s*>",
                    r"(?is)<article\b[^>]*>(.*)</article\s*>"):
        found = re.search(pattern, body)
        if found:
            candidate = _strip_markup(found.group(1))
            if len(candidate) >= 200:
                text = candidate
                break
    if not text:
        text = _strip_markup(body)

    # The page title is usually the best name for the source, so lead with it.
    if title and not text.startswith(title):
        text = f"{title}\n\n{text}"
    return text


def _decode(body: bytes, charset: str) -> str:
    # Servers do declare charsets Python has never heard of, and that must not 500 a route.
    for encoding in (charset, "utf-8"):
        if encoding:
            try:
                return body.decode(encoding, errors="replace")
            except LookupError:
                continue
    return body.decode("utf-8", errors="replace")


def _fetch(url: str) -> tuple[bytes, str, str]:
    request = urllib.request.Request(url, headers={
        "User-Agent": FETCH_UA,
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
        # Ask for no compression, so the size cap below counts the bytes we will actually read.
        "Accept-Encoding": "identity",
    })
    opener = urllib.request.build_opener(_GuardedRedirects())
    opener.addheaders = []
    try:
        with opener.open(request, timeout=FETCH_TIMEOUT_S) as resp:
            declared = resp.headers.get("Content-Length")
            if declared and declared.isdigit() and int(declared) > MAX_FETCH_BYTES:
                raise IngestError("That page is larger than 2 MB. Please save the part you "
                                  "want and upload it, or paste the text instead.")
            content_type = (resp.headers.get_content_type() or "").lower()
            charset = resp.headers.get_content_charset() or ""
            # One byte over the cap is enough to know the page is too big.
            body = resp.read(MAX_FETCH_BYTES + 1)
    except IngestError:
        raise
    except urllib.error.HTTPError as e:
        raise IngestError(f"That page replied with an error ({e.code}). "
                          "It may need a sign-in, or the link may be wrong.") from e
    except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
        raise IngestError("That page could not be reached within 15 seconds. "
                          "Please check the link, or paste the text instead.") from e
    except Exception as e:
        raise IngestError("That page could not be fetched. Please check the link, "
                          "or paste the text instead.") from e

    if len(body) > MAX_FETCH_BYTES:
        raise IngestError("That page is larger than 2 MB. Please save the part you want "
                          "and upload it, or paste the text instead.")
    return body, content_type, charset


def from_url(url: str) -> tuple[str, bool]:
    """Fetch a public web page and return readable text."""
    url = (url or "").strip()
    if not url:
        raise IngestError("Please give a web address to read.")
    if "://" not in url:
        url = "https://" + url
    _assert_public_url(url)

    body, content_type, charset = _fetch(url)

    # A link straight to a PDF is a normal thing for someone to paste.
    if content_type == "application/pdf" or body[:5] == b"%PDF-":
        return from_pdf(body)

    raw = _decode(body, charset)
    if content_type in ("text/plain", "text/markdown", "text/csv"):
        text = _clean(raw)
    else:
        text = _html_to_text(raw)

    if len(text) < MIN_URL_CHARS:
        raise IngestError("Very little readable text came back from that page - it may "
                          "need JavaScript or a sign-in. Please paste the text instead.")
    return _truncate(text)


# ---------------------------------------------------------------- Office files

# Word and PowerPoint files are zip archives of XML. Reading them with a few patterns rather
# than a parser means no library to install and no XML entity expansion to defend against.
MAX_ZIP_MEMBER = 20 * 1024 * 1024
_DOCX_PARA = re.compile(r"(?s)<w:p[ >].*?</w:p>")
_DOCX_RUN = re.compile(r"(?s)<w:t(?:\s[^>]*)?>(.*?)</w:t>|(<w:tab\s*/>)|(<w:br\s*/>)")
_PPTX_PARA = re.compile(r"(?s)<a:p[ >].*?</a:p>")
_PPTX_TEXT = re.compile(r"(?s)<a:t(?:\s[^>]*)?>(.*?)</a:t>")


def _open_zip(data: bytes, what: str) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise IngestError(f"That {what} could not be opened. Is the file complete?") from e


def _zip_text(z: zipfile.ZipFile, name: str) -> str:
    if z.getinfo(name).file_size > MAX_ZIP_MEMBER:
        raise IngestError("That file is too large once opened. Please upload a smaller one.")
    with z.open(name) as f:
        return f.read(MAX_ZIP_MEMBER + 1).decode("utf-8", errors="replace")


def from_docx(data: bytes) -> tuple[str, bool]:
    with _open_zip(data, "Word document") as z:
        if "word/document.xml" not in z.namelist():
            raise IngestError("That does not look like a Word (.docx) document.")
        xml = _zip_text(z, "word/document.xml")
    lines = []
    for para in _DOCX_PARA.findall(xml):
        parts = []
        for m in _DOCX_RUN.finditer(para):
            parts.append(html.unescape(m.group(1)) if m.group(1) is not None else " ")
        line = "".join(parts).strip()
        if line:
            lines.append(line)
    return _office_result(lines, "document")


def from_pptx(data: bytes) -> tuple[str, bool]:
    with _open_zip(data, "PowerPoint file") as z:
        slides = sorted(
            (n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
            key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)))
        if not slides:
            raise IngestError("That does not look like a PowerPoint (.pptx) file.")
        blocks = []
        for i, name in enumerate(slides[:MAX_PAGES], start=1):
            xml = _zip_text(z, name)
            lines = []
            for para in _PPTX_PARA.findall(xml):
                text = "".join(html.unescape(t) for t in _PPTX_TEXT.findall(para)).strip()
                if text:
                    lines.append(text)
            if lines:
                blocks.append(f"Slide {i}\n" + "\n".join(lines))
    return _office_result(blocks, "presentation")


def _office_result(blocks: list, what: str) -> tuple[str, bool]:
    text = _clean("\n\n".join(blocks))
    if len(text) < 200:
        raise IngestError(f"Almost no text came out of that {what}. If it is mostly images, "
                          "paste the text directly instead.")
    return _truncate(text)


# ---------------------------------------------------------------- text files

def _decode_text(data: bytes) -> str:
    """A text file may be UTF-8, UTF-16 (what Notepad calls "Unicode", and the likeliest
    way for an Urdu file to arrive) or an old Windows code page. Guessing UTF-8 for all of
    them turns the second into gibberish."""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


# ---------------------------------------------------------------- dispatch

SUPPORTED = "PDF, Word (.docx), PowerPoint (.pptx), .txt, .md, .html or .csv"


def from_upload(filename: str, data: bytes) -> tuple[str, bool]:
    name = (filename or "").lower()
    if name.endswith(".pdf") or data[:5] == b"%PDF-":
        return from_pdf(data)
    if name.endswith(".docx"):
        return from_docx(data)
    if name.endswith(".pptx"):
        return from_pptx(data)
    if name.endswith((".csv", ".tsv")):
        return from_csv(data, filename)
    if name.endswith((".html", ".htm")):
        return from_text(_html_to_text(_decode_text(data)))
    if name.endswith((".txt", ".md", ".markdown")):
        return from_text(_decode_text(data))
    raise IngestError(f"Unsupported file type. Upload a {SUPPORTED} file, "
                      "paste a link, or paste the text instead.")


def title_from(filename: str, text: str) -> str:
    if filename:
        stem = filename.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        stem = re.sub(r"[_-]+", " ", stem).strip()
        if len(stem) > 2:
            return stem[:120]
    first = next((ln.strip() for ln in text.split("\n") if len(ln.strip()) > 8), "Untitled")
    return first[:120]
