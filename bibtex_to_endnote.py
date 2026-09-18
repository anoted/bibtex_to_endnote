#!/usr/bin/env python3
"""
Convert BibTeX/BibLaTeX-like records to EndNote Tagged format (.enw).

Usage:
    python bibtex_to_endnote.py references.bib references.enw

The parser is intentionally tolerant of:
- Markdown ```bibtex fences
- stray prose between entries
- nested braces in titles/names
- multiline fields such as keywords
- mixed @article, @book, @misc, @inproceedings, etc.
- EndNote-style `type = {...}` fields already present in the BibTeX

Optional:
    pip install pylatexenc

If pylatexenc is installed, common LaTeX accents/commands are converted to Unicode.
Otherwise, the script still works and applies a few safe cleanups.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


ENDNOTE_TYPE_MAP = {
    "article": "Journal Article",
    "book": "Book",
    "booklet": "Book",
    "inbook": "Book Section",
    "incollection": "Book Section",
    "inproceedings": "Conference Proceedings",
    "conference": "Conference Proceedings",
    "proceedings": "Conference Proceedings",
    "phdthesis": "Thesis",
    "mastersthesis": "Thesis",
    "techreport": "Report",
    "report": "Report",
    "manual": "Generic",
    "unpublished": "Unpublished Work",
    "online": "Web Page",
    "electronic": "Electronic Article",
    "misc": "Generic",
}

# Common values already present in your bibliography.
KNOWN_ENDNOTE_TYPES = {
    "Aggregated Database",
    "Ancient Text",
    "Artwork",
    "Audiovisual Material",
    "Bill",
    "Blog",
    "Book",
    "Book Section",
    "Case",
    "Catalog",
    "Chart or Table",
    "Classical Work",
    "Computer Program",
    "Conference Paper",
    "Conference Proceedings",
    "Dataset",
    "Dictionary",
    "Edited Book",
    "Electronic Article",
    "Electronic Book",
    "Encyclopedia",
    "Equation",
    "Figure",
    "Film or Broadcast",
    "Generic",
    "Government Document",
    "Grant",
    "Hearing",
    "Journal Article",
    "Legal Rule or Regulation",
    "Magazine Article",
    "Manuscript",
    "Map",
    "Music",
    "Newspaper Article",
    "Online Database",
    "Online Multimedia",
    "Pamphlet",
    "Patent",
    "Personal Communication",
    "Report",
    "Serial",
    "Standard",
    "Statute",
    "Thesis",
    "Unpublished Work",
    "Web Page",
}


def strip_markdown_fences(text: str) -> str:
    """Remove Markdown code-fence lines but leave their contents."""
    return re.sub(r"(?m)^\s*```[A-Za-z0-9_-]*\s*$", "", text)


def extract_entries(text: str) -> List[str]:
    """
    Extract complete @type{...} or @type(...) entries with balanced delimiters.
    Ignores arbitrary text between entries.
    """
    entries: List[str] = []
    i = 0
    n = len(text)

    while i < n:
        at = text.find("@", i)
        if at < 0:
            break

        m = re.match(r"@([A-Za-z][A-Za-z0-9_-]*)\s*([\{\(])", text[at:])
        if not m:
            i = at + 1
            continue

        open_char = m.group(2)
        close_char = "}" if open_char == "{" else ")"
        start_delim = at + m.end() - 1

        depth = 0
        in_quote = False
        escaped = False
        j = start_delim

        while j < n:
            ch = text[j]

            if escaped:
                escaped = False
                j += 1
                continue

            if ch == "\\":
                escaped = True
                j += 1
                continue

            if ch == '"':
                in_quote = not in_quote
                j += 1
                continue

            if not in_quote:
                if ch == open_char:
                    depth += 1
                elif ch == close_char:
                    depth -= 1
                    if depth == 0:
                        entries.append(text[at : j + 1])
                        i = j + 1
                        break
            j += 1
        else:
            # Incomplete final entry. Skip it rather than crashing.
            i = at + 1

    return entries


def split_entry_header(entry: str) -> Tuple[str, str, str]:
    """Return (entry_type, citation_key, body)."""
    m = re.match(r"@([A-Za-z][A-Za-z0-9_-]*)\s*([\{\(])", entry)
    if not m:
        raise ValueError("Invalid BibTeX entry header")

    entry_type = m.group(1).lower()
    open_char = m.group(2)
    close_char = "}" if open_char == "{" else ")"

    inner = entry[m.end() : -1] if entry.rstrip().endswith(close_char) else entry[m.end() :]

    # First top-level comma separates key from fields.
    depth = 0
    in_quote = False
    escaped = False
    comma = None

    for idx, ch in enumerate(inner):
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_quote = not in_quote
            continue
        if in_quote:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            comma = idx
            break

    if comma is None:
        citation_key = inner.strip()
        body = ""
    else:
        citation_key = inner[:comma].strip()
        body = inner[comma + 1 :]

    return entry_type, citation_key, body


def read_braced_value(s: str, i: int) -> Tuple[str, int]:
    assert s[i] == "{"
    depth = 0
    escaped = False
    out: List[str] = []
    i += 1
    depth = 1

    while i < len(s):
        ch = s[i]
        if escaped:
            out.append(ch)
            escaped = False
            i += 1
            continue
        if ch == "\\":
            out.append(ch)
            escaped = True
            i += 1
            continue
        if ch == "{":
            depth += 1
            out.append(ch)
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return "".join(out), i + 1
            out.append(ch)
        else:
            out.append(ch)
        i += 1

    return "".join(out), i


def read_quoted_value(s: str, i: int) -> Tuple[str, int]:
    assert s[i] == '"'
    i += 1
    escaped = False
    out: List[str] = []

    while i < len(s):
        ch = s[i]
        if escaped:
            out.append(ch)
            escaped = False
            i += 1
            continue
        if ch == "\\":
            out.append(ch)
            escaped = True
            i += 1
            continue
        if ch == '"':
            return "".join(out), i + 1
        out.append(ch)
        i += 1

    return "".join(out), i


def read_bare_value(s: str, i: int) -> Tuple[str, int]:
    start = i
    while i < len(s) and s[i] not in ",\r\n":
        i += 1
    return s[start:i].strip(), i


def parse_fields(body: str) -> Dict[str, str]:
    """
    Parse top-level BibTeX fields. Supports braced, quoted, and bare values.
    Also supports simple BibTeX concatenation with #.
    """
    fields: Dict[str, str] = {}
    i = 0
    n = len(body)

    while i < n:
        while i < n and (body[i].isspace() or body[i] == ","):
            i += 1
        if i >= n:
            break

        m = re.match(r"([A-Za-z][A-Za-z0-9_:-]*)", body[i:])
        if not m:
            i += 1
            continue

        name = m.group(1).lower()
        i += m.end()

        while i < n and body[i].isspace():
            i += 1
        if i >= n or body[i] != "=":
            # Not a field assignment. Skip to next comma.
            while i < n and body[i] != ",":
                i += 1
            continue

        i += 1
        parts: List[str] = []

        while True:
            while i < n and body[i].isspace():
                i += 1
            if i >= n:
                break

            if body[i] == "{":
                value, i = read_braced_value(body, i)
            elif body[i] == '"':
                value, i = read_quoted_value(body, i)
            else:
                value, i = read_bare_value(body, i)

            parts.append(value.strip())

            while i < n and body[i].isspace():
                i += 1
            if i < n and body[i] == "#":
                i += 1
                continue
            break

        fields[name] = "".join(parts).strip()

        while i < n and body[i] != ",":
            i += 1
        if i < n and body[i] == ",":
            i += 1

    return fields


def latex_to_unicode(text: str) -> str:
    """
    Convert LaTeX-ish text to Unicode when pylatexenc is available.
    Otherwise perform conservative cleanup.
    """
    if not text:
        return ""

    try:
        from pylatexenc.latex2text import LatexNodes2Text  # type: ignore

        text = LatexNodes2Text().latex_to_text(text)
    except Exception:
        replacements = {
            r"\&": "&",
            r"\%": "%",
            r"\_": "_",
            r"\#": "#",
            r"\{": "{",
            r"\}": "}",
            r"~": " ",
            r"---": "—",
            r"--": "–",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)

        # Remove braces used only for BibTeX capitalization/grouping.
        text = text.replace("{", "").replace("}", "")

    # Normalize whitespace without destroying intended line-separated keywords.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()


def clean_scalar(value: str) -> str:
    value = latex_to_unicode(value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\s*\n\s*", " ", value)
    return value.strip()


def split_people(value: str) -> List[str]:
    """
    Split BibTeX author/editor list on ' and '.
    EndNote accepts repeated %A / %E tags.
    """
    if not value:
        return []
    parts = re.split(r"\s+and\s+", value, flags=re.IGNORECASE)
    return [clean_scalar(p) for p in parts if clean_scalar(p)]


def split_keywords(value: str) -> List[str]:
    if not value:
        return []

    value = latex_to_unicode(value)

    # Newline and semicolon are strong separators.
    chunks = re.split(r"[\n;]+", value)
    out: List[str] = []

    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue

        # Many exported bibliographies put comma-separated keywords on one line.
        # Split those too, but preserve the original phrase if there are no commas.
        if "," in chunk:
            out.extend(x.strip() for x in chunk.split(",") if x.strip())
        else:
            out.append(chunk)

    return out


def normalize_ref_type(entry_type: str, fields: Dict[str, str]) -> str:
    explicit = clean_scalar(fields.get("type", ""))

    if explicit:
        # Keep values such as "Web Page", "Journal Article", "Conference Paper",
        # "Electronic Article", "Online Multimedia", "Generic", etc.
        if explicit in KNOWN_ENDNOTE_TYPES:
            return explicit

        # Case-insensitive match against known EndNote names.
        for known in KNOWN_ENDNOTE_TYPES:
            if explicit.casefold() == known.casefold():
                return known

    return ENDNOTE_TYPE_MAP.get(entry_type.lower(), "Generic")


def add_tag(lines: List[str], tag: str, value: str) -> None:
    value = clean_scalar(value)
    if value:
        lines.append(f"{tag} {value}")


def entry_to_endnote(entry: str) -> Tuple[str, str]:
    entry_type, key, body = split_entry_header(entry)
    fields = parse_fields(body)
    ref_type = normalize_ref_type(entry_type, fields)

    lines: List[str] = [f"%0 {ref_type}"]

    # Preserve BibTeX citation key as EndNote Label.
    if key:
        lines.append(f"%F {key}")

    for author in split_people(fields.get("author", "")):
        lines.append(f"%A {author}")

    for editor in split_people(fields.get("editor", "")):
        lines.append(f"%E {editor}")

    add_tag(lines, "%T", fields.get("title", ""))

    # Journal and conference/book container fields.
    if fields.get("journal"):
        add_tag(lines, "%J", fields["journal"])
    if fields.get("booktitle"):
        add_tag(lines, "%B", fields["booktitle"])
    if fields.get("series"):
        add_tag(lines, "%S", fields["series"])

    add_tag(lines, "%D", fields.get("year", ""))
    add_tag(lines, "%8", fields.get("month", ""))
    add_tag(lines, "%V", fields.get("volume", ""))
    add_tag(lines, "%N", fields.get("number", ""))
    add_tag(lines, "%P", fields.get("pages", ""))

    publisher = fields.get("publisher") or fields.get("howpublished") or ""
    add_tag(lines, "%I", publisher)
    add_tag(lines, "%C", fields.get("address", ""))
    add_tag(lines, "%7", fields.get("edition", ""))

    # Identifiers / links.
    doi = fields.get("doi", "") or fields.get("DOI".lower(), "")
    add_tag(lines, "%R", doi)
    add_tag(lines, "%U", fields.get("url", ""))
    add_tag(lines, "%@", fields.get("isbn", "") or fields.get("issn", ""))

    for kw in split_keywords(fields.get("keywords", "")):
        lines.append(f"%K {kw}")

    add_tag(lines, "%X", fields.get("abstract", ""))

    # Notes: keep useful BibTeX-only metadata without overloading other fields.
    notes: List[str] = []
    if fields.get("note"):
        notes.append(clean_scalar(fields["note"]))

    eprint = clean_scalar(fields.get("eprint", ""))
    archive = clean_scalar(fields.get("archiveprefix", ""))
    primary_class = clean_scalar(fields.get("primaryclass", ""))

    if eprint:
        if archive:
            notes.append(f"{archive}: {eprint}")
        else:
            notes.append(f"eprint: {eprint}")
    if primary_class:
        notes.append(f"Primary class: {primary_class}")

    for note in notes:
        if note:
            lines.append(f"%Z {note}")

    return key, "\n".join(lines) + "\n"


def convert_text(text: str) -> Tuple[str, List[str]]:
    text = strip_markdown_fences(text)
    entries = extract_entries(text)

    output_records: List[str] = []
    keys: List[str] = []
    warnings: List[str] = []

    for idx, entry in enumerate(entries, start=1):
        try:
            key, record = entry_to_endnote(entry)
            output_records.append(record)
            if key:
                keys.append(key)
        except Exception as exc:
            warnings.append(f"Entry {idx}: skipped because {exc}")

    dupes = [key for key, count in Counter(keys).items() if count > 1]
    if dupes:
        warnings.append(
            "Duplicate BibTeX citation keys preserved: " + ", ".join(sorted(dupes))
        )

    # EndNote tagged records are separated by a blank line.
    output = "\n".join(output_records)
    return output, warnings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert BibTeX/BibLaTeX-like references to EndNote Tagged (.enw)."
    )
    parser.add_argument("input", type=Path, help="Input .bib or text file")
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        help="Output .enw file (default: same basename as input)",
    )
    args = parser.parse_args()

    input_path: Path = args.input
    output_path: Path = args.output or input_path.with_suffix(".enw")

    text = input_path.read_text(encoding="utf-8-sig")
    converted, warnings = convert_text(text)
    output_path.write_text(converted, encoding="utf-8")

    count = converted.count("\n%0 ") + (1 if converted.startswith("%0 ") else 0)
    print(f"Converted {count} reference(s) -> {output_path}")

    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
