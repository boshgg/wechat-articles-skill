from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import mimetypes
import re
from pathlib import Path
from urllib.parse import unquote

from PIL import Image


IMAGE_RE = re.compile(r"^!\[([^]]*)\]\((.+)\)$")
LINK_RE = re.compile(r"\[([^]]+)\]\((https?://[^)]+)\)")
INLINE_RE = re.compile(r"\[([^]]+)\]\((https?://[^)]+)\)|\*\*(.+?)\*\*")
NUMBERED_RE = re.compile(r"^(\d+)\.\s+(.+)$")
DATE_RE = re.compile(r"^(\d{4})\.(\d{2})\.(\d{2})")
AUTHOR_RE = re.compile(r"（修改后）([^（）]+)$")

FONT_STACK = "-apple-system,BlinkMacSystemFont,'Segoe UI','Microsoft YaHei','PingFang SC',Arial,sans-serif"
BODY_STYLE = (
    f"margin:0;padding:0;background-color:#edf2f6;color:#172336;"
    f"font-family:{FONT_STACK};letter-spacing:0;"
)
PARAGRAPH_STYLE = (
    "margin:10px 24px 0;font-size:16px;line-height:2;color:#3d4c5f;"
    "text-align:justify;word-break:break-word;letter-spacing:0;"
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inline_markup(text: str) -> str:
    output: list[str] = []
    cursor = 0
    for match in INLINE_RE.finditer(text):
        output.append(html.escape(text[cursor : match.start()]))
        if match.group(1) is not None:
            label = html.escape(match.group(1))
            url = html.escape(match.group(2), quote=True)
            output.append(
                f'<a href="{url}" style="color:#0c564a;text-decoration:underline;'
                f'text-underline-offset:3px;letter-spacing:0;">{label}</a>'
            )
        else:
            output.append(
                f'<strong style="color:inherit;font-weight:800;letter-spacing:0;">'
                f'{html.escape(match.group(3))}</strong>'
            )
        cursor = match.end()
    output.append(html.escape(text[cursor:]))
    return "".join(output)


def split_intro(text: str) -> tuple[str, str]:
    if "**" in text or LINK_RE.search(text):
        return text, ""
    terminal_positions = [
        index + 1 for index, character in enumerate(text) if character in "。！？!?；;"
    ]
    if terminal_positions and terminal_positions[0] <= 54:
        end = terminal_positions[0]
    else:
        comma_positions = [
            index + 1
            for index, character in enumerate(text)
            if character in "，," and 22 <= index + 1 <= 54
            and not (index > 0 and index + 1 < len(text) and text[index - 1].isdigit() and text[index + 1].isdigit())
        ]
        end = comma_positions[0] if comma_positions else len(text)
    return text[:end].strip(), text[end:].strip()


def image_data(markdown_path: Path, target: str) -> tuple[Path, bytes, str, int, int]:
    path = (markdown_path.parent / unquote(target)).resolve()
    data = path.read_bytes()
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    with Image.open(path) as image:
        width, height = image.size
    return path, data, mime, width, height


def render_image(
    markdown_path: Path,
    alt_text: str,
    target: str,
    image_index: int,
    image_records: list[dict[str, object]],
) -> str:
    path, data, mime, width, height = image_data(markdown_path, target)
    digest = sha256(data)
    image_records.append(
        {
            "path": str(path),
            "sha256": digest,
            "bytes": len(data),
            "width": width,
            "height": height,
        }
    )
    encoded = base64.b64encode(data).decode("ascii")
    role = "cover" if image_index == 1 else "illustration"
    bottom = "0" if image_index == 1 else "24px"
    return (
        f'<section data-role="{role}" style="margin:0 0 {bottom};padding:0;'
        f'background-color:#ffffff;text-align:center;line-height:0;letter-spacing:0;">'
        f'<img src="data:{mime};base64,{encoded}" alt="{html.escape(alt_text, quote=True)}" '
        f'width="{width}" height="{height}" data-sha256="{digest}" '
        f'style="display:block;width:100%;height:auto;margin:0;box-sizing:border-box;" />'
        f'</section>'
    )


def render_section_heading(text: str, number: int) -> str:
    if number == 1:
        return (
            '<section style="margin:34px 24px 20px;padding-left:14px;'
            'border-left:6px solid #e0b82f;box-sizing:border-box;letter-spacing:0;">'
            '<div style="margin:0;color:#c63c34;font-size:13px;font-weight:900;'
            'line-height:1.5;letter-spacing:0;">TECHNICAL BRIEF</div>'
            f'<h2 style="margin:4px 0 0;color:#0b1d33;font-size:25px;line-height:1.45;'
            f'font-weight:900;word-break:break-word;letter-spacing:0;">{html.escape(text)}</h2>'
            '</section>'
        )
    return (
        '<section style="margin:30px 24px 20px;padding:22px 20px;background-color:#0b1d33;'
        'border-top:5px solid #e0b82f;box-sizing:border-box;letter-spacing:0;">'
        f'<div style="margin:0;color:#74c8ac;font-size:13px;font-weight:900;'
        f'line-height:1.5;letter-spacing:0;">SECTION {number:02d}</div>'
        f'<h2 style="margin:5px 0 0;color:#ffffff;font-size:23px;line-height:1.5;'
        f'font-weight:900;word-break:break-word;letter-spacing:0;">{html.escape(text)}</h2>'
        '</section>'
    )


def render_subheading(text: str) -> str:
    return (
        f'<h3 style="margin:22px 24px 8px;font-size:17px;line-height:1.8;'
        f'color:#0b1d33;font-weight:900;letter-spacing:0;">'
        f'{html.escape(text)}</h3>'
    )


def render_minor_heading(text: str) -> str:
    return (
        f'<h4 style="margin:18px 24px 6px;font-size:15px;line-height:1.75;'
        f'color:#0b1d33;font-weight:900;letter-spacing:0;">'
        f'{html.escape(text)}</h4>'
    )


def render_quote(text: str) -> str:
    return (
        '<section style="margin:16px 24px 20px;padding:15px 16px;border-left:5px solid #0c564a;'
        'background-color:#eef7f4;box-sizing:border-box;letter-spacing:0;">'
        '<p style="margin:0;font-size:15.5px;line-height:1.85;color:#34534c;text-align:justify;'
        f'word-break:break-word;letter-spacing:0;">{inline_markup(text)}</p></section>'
    )


def render_company_section(paragraphs: list[str]) -> str:
    body = "".join(
        f'<p style="margin:0 0 15px;font-size:15.5px;line-height:1.9;color:#d8e7f2;'
        f'text-align:justify;word-break:break-word;letter-spacing:0;">{inline_markup(text)}</p>'
        for text in paragraphs
    )
    return (
        '<section data-role="company" style="margin:30px 0 0;padding:32px 24px 28px;'
        'background-color:#0b1d33;border-top:5px solid #e0b82f;box-sizing:border-box;letter-spacing:0;">'
        '<p style="margin:0 0 7px;font-size:13px;line-height:1.5;color:#74c8ac;'
        'font-weight:900;letter-spacing:0;">JINPENG INDUSTRIAL</p>'
        '<h2 style="margin:0 0 20px;font-size:25px;line-height:1.45;color:#ffffff;'
        'font-weight:900;letter-spacing:0;">关于商丘金蓬</h2>'
        f'{body}'
        '<p style="margin:22px 0 0;padding-top:16px;border-top:1px solid #38526b;'
        'font-size:12px;line-height:1.6;color:#a8c9e3;text-align:center;letter-spacing:0;">'
        '固废资源化装备研发 · 制造 · 服务</p>'
        '</section>'
    )


def parse_blocks(markdown_path: Path) -> tuple[str, list[dict[str, str]]]:
    from _article_tables import read_table
    lines = markdown_path.read_text(encoding="utf-8").splitlines()
    title = ""
    blocks: list[dict[str, str]] = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        index += 1
        if not line:
            continue
        table = read_table(lines, index - 1)
        if table:
            rows, index = table
            blocks.append({"type": "table", "rows": rows})
            continue
        if line.startswith("# "):
            title = line[2:].strip()
            continue
        if line.startswith("## "):
            blocks.append({"type": "h2", "text": line[3:].strip()})
            continue
        if line.startswith("#### "):
            blocks.append({"type": "h4", "text": line[5:].strip()})
            continue
        if line.startswith("### "):
            blocks.append({"type": "h3", "text": line[4:].strip()})
            continue
        if line == "---":
            blocks.append({"type": "hr", "text": ""})
            continue
        if line.startswith("> "):
            quote_lines = [line[2:].strip()]
            while index < len(lines):
                next_line = lines[index].strip()
                if not next_line:
                    index += 1
                    break
                if not next_line.startswith("> "):
                    break
                quote_lines.append(next_line[2:].strip())
                index += 1
            blocks.append({"type": "quote", "text": " ".join(quote_lines)})
            continue
        image_match = IMAGE_RE.match(line)
        if image_match:
            blocks.append(
                {"type": "image", "alt": image_match.group(1), "target": image_match.group(2)}
            )
            continue
        numbered_match = NUMBERED_RE.match(line)
        if numbered_match:
            blocks.append({"type": "numbered", "number": int(numbered_match.group(1)), "text": numbered_match.group(2)})
            continue
        paragraph_lines = [line]
        while index < len(lines):
            next_line = lines[index].strip()
            if not next_line:
                index += 1
                break
            if (
                next_line.startswith("# ")
                or next_line.startswith("## ")
                or next_line.startswith("#### ")
                or next_line.startswith("### ")
                or next_line.startswith("> ")
                or next_line == "---"
                or IMAGE_RE.match(next_line)
                or NUMBERED_RE.match(next_line)
            ):
                break
            paragraph_lines.append(next_line)
            index += 1
        text = " ".join(paragraph_lines)
        if text.startswith("- "):
            text = text[2:]
        blocks.append({"type": "paragraph", "text": text})
    if not title:
        raise ValueError(f"Missing title: {markdown_path}")
    return title, blocks


def metadata(markdown_path: Path) -> tuple[str, str]:
    date_match = DATE_RE.match(markdown_path.stem)
    author_match = AUTHOR_RE.search(markdown_path.stem)
    date = (
        f"{date_match.group(1)}年{date_match.group(2)}月{date_match.group(3)}日"
        if date_match
        else ""
    )
    author = author_match.group(1) if author_match else ""
    return date, author


def build_html(markdown_path: Path, output_root: Path | None = None,
               cover_has_title: bool = False) -> tuple[Path, dict[str, object]]:
    title, blocks = parse_blocks(markdown_path)
    _date, author = metadata(markdown_path)
    image_records: list[dict[str, object]] = []
    rendered: list[str] = []
    section_number = 0
    image_index = 0
    first_prose = True
    numbered_items: list[dict] = []
    previous_block_type = ""

    company_index = next(
        (i for i, block in enumerate(blocks) if block["type"] == "h2" and block["text"] == "关于商丘金蓬"),
        None,
    )
    company_paragraphs: list[str] = []
    if company_index is not None:
        company_paragraphs = [
            block["text"]
            for block in blocks[company_index + 1 :]
            if block["type"] == "paragraph"
        ]
        blocks = blocks[:company_index]

    has_cover = bool(
        blocks
        and blocks[0]["type"] == "image"
        and "封面" in blocks[0].get("alt", "")
    )
    if cover_has_title and not has_cover:
        raise ValueError("An explicitly identified first cover image is required to suppress the visible title.")
    if not cover_has_title:
        rendered.append(
            '<section data-role="title" style="margin:0;padding:34px 24px 30px;'
            'background-color:#0b1d33;border-top:5px solid #e0b82f;'
            'box-sizing:border-box;letter-spacing:0;">'
            '<p style="margin:0 0 8px;color:#74c8ac;font-size:13px;line-height:1.5;'
            'font-weight:900;letter-spacing:0;">JINPENG INDUSTRIAL</p>'
            f'<h1 style="margin:0;color:#ffffff;font-size:27px;line-height:1.5;'
            f'font-weight:900;word-break:break-word;text-wrap:balance;letter-spacing:0;">{html.escape(title)}</h1>'
            '</section>'
        )

    def flush_numbered() -> None:
        if not numbered_items:
            return
        items = "".join(
            f'<li value="{item["number"]}" style="margin:0;padding:14px 12px;font-size:15.5px;line-height:1.9;'
            f'color:#3d4c5f;border-bottom:1px solid #d3dde5;letter-spacing:0;">'
            f'{inline_markup(item["text"])}</li>'
            for item in numbered_items
        )
        rendered.append(
            f'<ol start="{numbered_items[0]["number"]}" style="margin:18px 24px 20px;padding:0 0 0 36px;background-color:#f3f6f8;'
            'border:1px solid #d3dde5;box-sizing:border-box;letter-spacing:0;">'
            f'{items}</ol>'
        )
        numbered_items.clear()

    for block in blocks:
        block_type = block["type"]
        if block_type != "numbered":
            flush_numbered()
        if block_type == "image":
            image_index += 1
            rendered.append(
                render_image(
                    markdown_path,
                    block.get("alt", ""),
                    block["target"],
                    image_index,
                    image_records,
                )
            )
        elif block_type == "table":
            table_rows = []
            for row_index, row in enumerate(block["rows"]):
                tag = "th" if row_index == 0 else "td"
                color = "#ffffff" if row_index == 0 else "#3d4c5f"
                background = "#0b1d33" if row_index == 0 else ("#f3f6f8" if row_index % 2 else "#ffffff")
                cells = "".join(
                    f'<{tag} style="padding:10px 7px;border:1px solid #d3dde5;'
                    f'color:{color};background-color:{background};text-align:left;'
                    f'vertical-align:top;word-break:break-word;overflow-wrap:anywhere;'
                    f'font-size:13px;line-height:1.8;letter-spacing:0;">{inline_markup(cell)}</{tag}>'
                    for cell in row
                )
                table_rows.append(f'<tr>{cells}</tr>')
            rendered.append(
                '<section data-role="table" style="margin:18px 24px 24px;">'
                '<table style="width:100%;table-layout:fixed;border-collapse:collapse;'
                'box-sizing:border-box;letter-spacing:0;">'
                + "".join(table_rows) + '</table></section>'
            )
            first_prose = False
        elif block_type == "h2":
            section_number += 1
            rendered.append(render_section_heading(block["text"], section_number))
            first_prose = False
        elif block_type == "h3":
            rendered.append(render_subheading(block["text"]))
            first_prose = False
        elif block_type == "h4":
            rendered.append(render_minor_heading(block["text"]))
            first_prose = False
        elif block_type == "hr":
            rendered.append(
                '<div style="margin:30px 24px 0;border-top:1px solid #d3dde5;'
                'height:0;line-height:0;letter-spacing:0;"></div>'
            )
        elif block_type == "numbered":
            numbered_items.append(block)
        elif block_type == "quote":
            rendered.append(render_quote(block["text"]))
            first_prose = False
        elif block_type == "paragraph":
            text = block["text"]
            if previous_block_type == "image" and (text.endswith("（原稿配图）") or re.match(r"^图\s*\d+\s", text) or text.startswith("Image by ")):
                rendered.append(
                    f'<p style="margin:8px 24px 22px;font-size:13px;line-height:1.7;'
                    f'color:#7b8794;text-align:center;word-break:break-word;letter-spacing:0;">'
                    f'{inline_markup(text)}</p>'
                )
                first_prose = False
            elif first_prose:
                lead, detail = split_intro(text)
                detail_html = (
                    f'<p style="margin:9px 0 0;font-size:15.5px;line-height:1.8;'
                    f'color:#a8c9e3;font-weight:400;text-align:justify;word-break:break-word;'
                    f'letter-spacing:0;">{inline_markup(detail)}</p>'
                    if detail
                    else ""
                )
                rendered.append(
                    f'<section style="margin:30px 24px 22px;padding:21px 20px;'
                    f'border-left:5px solid #e0b82f;background-color:#0b1d33;'
                    f'box-sizing:border-box;letter-spacing:0;">'
                    f'<p style="margin:0;font-size:20px;line-height:1.65;color:#ffffff;font-weight:800;'
                    f'text-align:justify;'
                    f'word-break:break-word;letter-spacing:0;">{inline_markup(lead)}</p>'
                    f'{detail_html}</section>'
                )
                first_prose = False
            elif text == "参考资料：":
                rendered.append(
                    '<p style="margin:30px 24px 14px;padding-top:18px;border-top:1px solid #d3dde5;'
                    'font-size:17px;line-height:1.8;color:#0b1d33;font-weight:900;letter-spacing:0;">参考资料：</p>'
                )
            else:
                rendered.append(f'<p style="{PARAGRAPH_STYLE}">{inline_markup(text)}</p>')
        previous_block_type = block_type
    flush_numbered()

    if company_paragraphs:
        rendered.append(render_company_section(company_paragraphs))

    document = (
        '<!doctype html>\n'
        '<html lang="zh-CN">\n<head>\n'
        '<meta charset="utf-8" />\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1" />\n'
        f'<meta name="author" content="{html.escape(author, quote=True)}" />\n'
        f'<title>{html.escape(title)}</title>\n'
        '</head>\n'
        f'<body style="{BODY_STYLE}">\n'
        '<main data-layout="jinpeng-reference-v2" style="width:100%;max-width:677px;margin:0 auto;'
        'padding:0;background-color:#ffffff;box-shadow:0 10px 40px rgba(9,35,54,0.08);'
        'box-sizing:border-box;letter-spacing:0;">\n'
        + "\n".join(rendered)
        + '\n<section aria-hidden="true" style="height:9px;background-color:#e0b82f;line-height:0;letter-spacing:0;"></section>'
        + '\n<section aria-hidden="true" style="height:18px;background-color:#0b1d33;line-height:0;letter-spacing:0;"></section>'
        + '\n</main>\n</body>\n</html>\n'
    )

    output_root = output_root or markdown_path.resolve().parent.parent / "html文章"
    output_root.mkdir(parents=True, exist_ok=True)
    output_path = output_root / f"{markdown_path.stem}.html"
    output_path.write_text(document, encoding="utf-8")
    return output_path, {
        "markdown": str(markdown_path),
        "html": str(output_path),
        "html_sha256": sha256(document.encode("utf-8")),
        "images": image_records,
    }


def validate_html(path: Path, record: dict[str, object]) -> None:
    content = path.read_text(encoding="utf-8")
    errors: list[str] = []
    if "（修改后）" not in path.stem:
        errors.append("missing revision marker in filename")
    if 'data-layout="jinpeng-reference-v2"' not in content:
        errors.append("missing layout marker")
    if "关于商丘金蓬" not in content:
        errors.append("missing company section")
    if "<script" in content.lower() or "<style" in content.lower():
        errors.append("contains non-portable script/style block")
    if "file://" in content.lower():
        errors.append("contains file URL")
    if content.count("data:image/") != len(record["images"]):
        errors.append("embedded image count mismatch")
    for image_record in record["images"]:
        digest = image_record["sha256"]
        if f'data-sha256="{digest}"' not in content:
            errors.append(f"missing image hash {digest}")
    if errors:
        raise ValueError(f"{path.name}: " + "; ".join(errors))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build WeChat-ready HTML from reviewed Markdown.")
    parser.add_argument("markdown", nargs="+", type=Path, help="Reviewed Markdown file(s)")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    for markdown_path in args.markdown:
        output_path, record = build_html(markdown_path.resolve(), args.output_dir)
        validate_html(output_path, record)
        print(json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    main()
