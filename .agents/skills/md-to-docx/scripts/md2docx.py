#!/usr/bin/env python3
"""Convert a Markdown file to .docx.

Strategy: pandoc if installed; otherwise a built-in Markdown -> HTML conversion
followed by macOS `textutil` or LibreOffice `soffice`. On the fallback path,
local PNG/JPEG images are injected into the .docx afterwards, because textutil
drops images. Standard library only.

Usage: python3 md2docx.py INPUT.md [OUTPUT.docx] [--font-size 11] [--heading-size 16]
"""

from __future__ import annotations

import html
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

MARKER = "MD2DOCXIMAGE{}END"
MAX_WIDTH_EMU = 6 * 914400  # 6 inches, fits A4/Letter with default margins
EMU_PER_PX = 9525           # at 96 DPI


# --------------------------------------------------------------------------- #
# Markdown -> HTML (common subset: headings, paragraphs, bold/italic, code,
# fenced code, links, images, nested lists, tables, blockquotes, rules)
# --------------------------------------------------------------------------- #

def inline(text: str, images: list[str]) -> str:
    codes: list[str] = []

    def keep_code(match: re.Match) -> str:
        codes.append(f"<code>{html.escape(match.group(1))}</code>")
        return f"\x00{len(codes) - 1}\x00"

    def image(match: re.Match) -> str:
        images.append(html.unescape(match.group(2)))
        return f"\x01{MARKER.format(len(images) - 1)}\x01"

    text = re.sub(r"`([^`]+)`", keep_code, text)
    text = html.escape(text, quote=False)
    text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", image, text)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], text)


def _block(tag: str, content: str) -> str:
    """Wrap content in a block tag, moving image markers to their own paragraphs."""
    parts = [p for p in content.split("\x01")]
    out = []
    for part in parts:
        if re.fullmatch(MARKER.format(r"\d+"), part):
            out.append(f"<p>{part}</p>")
        elif part.strip():
            out.append(f"<{tag}>{part}</{tag}>")
    return "".join(out)


def markdown_to_html(
    source: str,
    title: str,
    images: list[str],
    font_size: float = 11,
    heading_size: float = 16,
) -> str:
    lines = source.splitlines()
    out: list[str] = []
    paragraph: list[str] = []
    list_stack: list[tuple[int, str]] = []
    i = 0

    def inl(text: str) -> str:
        return inline(text, images)

    def flush_paragraph() -> None:
        if paragraph:
            out.append(_block("p", inl(" ".join(paragraph))))
            paragraph.clear()

    def close_lists(indent: int = -1) -> None:
        while list_stack and list_stack[-1][0] > indent:
            out.append(f"</{list_stack.pop()[1]}>")

    if lines and lines[0].strip() == "---":  # YAML front matter
        end = next((n for n in range(1, len(lines)) if lines[n].strip() == "---"), None)
        if end:
            i = end + 1

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_paragraph(); close_lists()
            block = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i]); i += 1
            out.append(f"<pre><code>{html.escape(chr(10).join(block))}</code></pre>")
            i += 1
            continue

        if not stripped:
            flush_paragraph()
            nxt = next((l for l in lines[i + 1:] if l.strip()), "")
            if not re.match(r"\s*([-*+]|\d+\.)\s", nxt):
                close_lists()
            i += 1
            continue

        heading = re.match(r"(#{1,6})\s+(.*?)\s*#*$", stripped)
        if heading:
            flush_paragraph(); close_lists()
            out.append(_block(f"h{len(heading.group(1))}", inl(heading.group(2))))
            i += 1
            continue

        if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", stripped):
            flush_paragraph(); close_lists()
            out.append("<hr>")
            i += 1
            continue

        if (
            stripped.startswith("|")
            and i + 1 < len(lines)
            and re.fullmatch(r"\|?[\s:|-]+\|?", lines[i + 1].strip())
        ):
            flush_paragraph(); close_lists()

            def cells(row: str) -> list[str]:
                return [c.strip() for c in row.strip().strip("|").split("|")]

            out.append('<table border="1" cellspacing="0" cellpadding="4">')
            out.append("<tr>" + "".join(f"<th>{inl(c)}</th>" for c in cells(stripped)) + "</tr>")
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                out.append("<tr>" + "".join(f"<td>{inl(c)}</td>" for c in cells(lines[i])) + "</tr>")
                i += 1
            out.append("</table>")
            continue

        item = re.match(r"(\s*)([-*+]|\d+\.)\s+(.*)", line)
        if item:
            flush_paragraph()
            indent = len(item.group(1).expandtabs(4))
            tag = "ol" if item.group(2)[0].isdigit() else "ul"
            close_lists(indent)
            if list_stack and list_stack[-1][0] == indent and list_stack[-1][1] != tag:
                out.append(f"</{list_stack.pop()[1]}>")
            if not list_stack or list_stack[-1][0] < indent:
                out.append(f"<{tag}>")
                list_stack.append((indent, tag))
            out.append(f"<li>{inl(item.group(3)).replace(chr(1), ' ')}</li>")
            i += 1
            continue

        if stripped.startswith(">"):
            flush_paragraph(); close_lists()
            out.append(_block("blockquote", inl(stripped.lstrip("> "))))
            i += 1
            continue

        if list_stack and line.startswith((" ", "\t")):
            out[-1] = out[-1].replace("</li>", f" {inl(stripped)}</li>")
            i += 1
            continue

        if list_stack:
            close_lists()
        paragraph.append(stripped)
        i += 1

    flush_paragraph(); close_lists()
    body = "\n".join(out).replace("\x01", "")
    code_size = max(font_size - 1.5, 6)
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        f"<title>{html.escape(title)}</title>"
        f"<style>body{{font-family:Calibri,Arial,sans-serif;font-size:{font_size}pt}}"
        f"h1,h2,h3,h4,h5,h6{{font-size:{heading_size}pt}}"
        f"pre,code{{font-family:Menlo,Consolas,monospace;font-size:{code_size}pt}}</style>"
        f"</head><body>\n{body}\n</body></html>\n"
    )


def fix_textutil_scaling(docx: Path) -> None:
    """textutil converts CSS pt as if they were px (x4/3); scale sizes/spacing back."""
    with zipfile.ZipFile(docx) as zin:
        parts = {name: zin.read(name) for name in zin.namelist()}
    document = parts["word/document.xml"].decode("utf-8")

    def scale(match: re.Match) -> str:
        return f'{match.group(1)}"{round(int(match.group(2)) * 3 / 4)}"'

    def scale_spacing(match: re.Match) -> str:
        return re.sub(r'(w:(?:before|after)=)"(\d+)"', scale, match.group(0))

    document = re.sub(r'(<w:sz(?:-cs)? w:val=)"(\d+)"', scale, document)
    document = re.sub(r"<w:spacing\b[^>]*>", scale_spacing, document)
    parts["word/document.xml"] = document.encode("utf-8")
    tmp = docx.with_suffix(".tmp.docx")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, content in parts.items():
            zout.writestr(name, content)
    os.replace(tmp, docx)


# --------------------------------------------------------------------------- #
# Image injection into an existing .docx
# --------------------------------------------------------------------------- #

def image_size(data: bytes) -> tuple[int, int] | None:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            length = struct.unpack(">H", data[i + 2:i + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return w, h
            i += 2 + length
    return None


def _drawing(rel_id: str, index: int, name: str, cx: int, cy: int) -> str:
    name = html.escape(name)
    return (
        '<w:p><w:r><w:drawing>'
        '<wp:inline distT="0" distB="0" distL="0" distR="0" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
        f'<wp:extent cx="{cx}" cy="{cy}"/>'
        f'<wp:docPr id="{1000 + index}" name="{name}"/>'
        '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        f'<pic:nvPicPr><pic:cNvPr id="{1000 + index}" name="{name}"/><pic:cNvPicPr/></pic:nvPicPr>'
        '<pic:blipFill>'
        f'<a:blip r:embed="{rel_id}" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
        '<a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
        '<pic:spPr><a:xfrm><a:off x="0" y="0"/>'
        f'<a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
        '</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>'
    )


def inject_images(docx: Path, images: list[str], base: Path) -> list[str]:
    """Replace marker paragraphs with embedded images. Returns warnings."""
    warnings: list[str] = []
    with zipfile.ZipFile(docx) as zin:
        parts = {name: zin.read(name) for name in zin.namelist()}

    document = parts["word/document.xml"].decode("utf-8")
    rels_name = "word/_rels/document.xml.rels"
    rels = parts.get(rels_name, b"").decode("utf-8") or (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        "</Relationships>"
    )
    types = parts["[Content_Types].xml"].decode("utf-8")

    for index, src in enumerate(images):
        pattern = re.compile(
            r"<w:p[ >](?:(?!</w:p>).)*?" + re.escape(MARKER.format(index)) + r".*?</w:p>",
            re.S,
        )
        path = (base / src).resolve() if not re.match(r"[a-z]+://", src) else None
        data = path.read_bytes() if path and path.is_file() else None
        size = image_size(data) if data else None
        if not size:
            warnings.append(f"Image not embedded (missing, remote, or not PNG/JPEG): {src}")
            document = pattern.sub(f"<w:p><w:r><w:t>[image: {html.escape(src)}]</w:t></w:r></w:p>", document, 1)
            continue

        ext = "png" if data[:4] == b"\x89PNG" else "jpeg"
        media = f"media/md2docx_image{index}.{ext}"
        rel_id = f"rIdMd2Docx{index}"
        parts[f"word/{media}"] = data
        rels = rels.replace(
            "</Relationships>",
            f'<Relationship Id="{rel_id}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
            f'Target="{media}"/></Relationships>',
        )
        if f'Extension="{ext}"' not in types:
            types = types.replace(
                "</Types>", f'<Default Extension="{ext}" ContentType="image/{ext}"/></Types>'
            )
        w, h = size
        cx, cy = w * EMU_PER_PX, h * EMU_PER_PX
        if cx > MAX_WIDTH_EMU:
            cx, cy = MAX_WIDTH_EMU, int(cy * MAX_WIDTH_EMU / cx)
        document, count = pattern.subn(_drawing(rel_id, index, Path(src).name, cx, cy), document, 1)
        if not count:
            warnings.append(f"Marker for image {src} not found in converted document.")

    parts["word/document.xml"] = document.encode("utf-8")
    parts[rels_name] = rels.encode("utf-8")
    parts["[Content_Types].xml"] = types.encode("utf-8")

    tmp = docx.with_suffix(".tmp.docx")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, content in parts.items():
            zout.writestr(name, content)
    os.replace(tmp, docx)
    return warnings


# --------------------------------------------------------------------------- #
# Conversion drivers
# --------------------------------------------------------------------------- #

def convert(
    src: Path, dst: Path, font_size: float = 11, heading_size: float = 16
) -> tuple[str, list[str]]:
    if shutil.which("pandoc"):
        subprocess.run(
            ["pandoc", str(src), "-o", str(dst), "--resource-path", str(src.parent)],
            check=True,
        )
        return "pandoc", [
            "pandoc uses its default styles; font sizes were not applied. "
            "Use pandoc --reference-doc=template.docx to control them."
        ]

    images: list[str] = []
    html_text = markdown_to_html(
        src.read_text(encoding="utf-8"), src.stem, images, font_size, heading_size
    )
    with tempfile.TemporaryDirectory() as work:
        html_path = Path(work) / "document.html"
        html_path.write_text(html_text, encoding="utf-8")
        if shutil.which("textutil"):
            subprocess.run(
                ["textutil", "-convert", "docx", str(html_path), "-output", str(dst)],
                check=True,
            )
            fix_textutil_scaling(dst)
            engine = "textutil"
        elif shutil.which("soffice") or shutil.which("libreoffice"):
            office = shutil.which("soffice") or shutil.which("libreoffice")
            subprocess.run(
                [office, "--headless", "--convert-to", "docx:MS Word 2007 XML",
                 "--outdir", work, str(html_path)],
                check=True, capture_output=True,
            )
            shutil.move(str(Path(work) / "document.docx"), dst)
            engine = "libreoffice"
        else:
            raise SystemExit(
                "No converter found. Install pandoc (brew install pandoc) or LibreOffice, "
                "or run on macOS where textutil is built in."
            )

    warnings = inject_images(dst, images, src.parent) if images else []
    return engine, warnings


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Convert Markdown to .docx.")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--font-size", type=float, default=11, help="body text size in pt (default 11)")
    parser.add_argument("--heading-size", type=float, default=16, help="heading size in pt (default 16)")
    args = parser.parse_args()

    src = args.input.resolve()
    if not src.is_file():
        raise SystemExit(f"Input not found: {src}")
    dst = args.output.resolve() if args.output else src.with_suffix(".docx")
    engine, warnings = convert(src, dst, args.font_size, args.heading_size)
    for warning in warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    print(f"Wrote {dst} using {engine}")


if __name__ == "__main__":
    main()
