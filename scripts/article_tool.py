"""Local extraction, reviewed-article builds, invariant checks and explicit backups."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote
from zipfile import ZipFile

from lxml import etree
from lxml import html as html_parser

from _build_wechat_html import build_html, parse_blocks, validate_html
from _build_reviewed_docs import build_document

SKILL = Path(__file__).resolve().parent.parent
DEFAULTS = json.loads((SKILL / "assets/project-defaults.json").read_text(encoding="utf-8"))
CLOSING = (SKILL / "assets/company-closing.md").read_text(encoding="utf-8").strip()
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
      "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "v": "urn:schemas-microsoft-com:vml"}
FILENAME = re.compile(r"^(\d{4}\.\d{2}\.\d{2})(.+)（修改后）([^（）]+)$")
EDITORIAL = ("审查发现", "修改建议", "修改依据", "待核实", "知识库实测", "图片缺失", "审稿意见")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def xml(data: bytes):
    return etree.fromstring(data, parser=etree.XMLParser(resolve_entities=False, no_network=True))


def text_of(element) -> str:
    nodes = element.xpath(".//w:t|.//w:tab|.//w:br|.//w:cr", namespaces=NS)
    return "".join((node.text or "") if etree.QName(node).localname == "t" else
                   ("\t" if etree.QName(node).localname == "tab" else "\n") for node in nodes)


def extract(source: Path, output: Path) -> Path:
    source, output = source.resolve(), output.resolve()
    if source.suffix.lower() != ".docx":
        raise ValueError("Binary .doc needs a fidelity-preserving conversion copy first; do not rename its extension.")
    target = output / "source.json"
    if target.exists():
        raise FileExistsError(target)
    output.mkdir(parents=True, exist_ok=True)
    record = {"source": str(source), "sha256": digest(source), "blocks": [], "images": [], "warnings": []}
    with ZipFile(source) as archive:
        root = xml(archive.read("word/document.xml"))
        rels = {r.get("Id"): r for r in xml(archive.read("word/_rels/document.xml.rels"))}
        flags = {"tracked_changes": ".//w:ins|.//w:del", "text_boxes": ".//w:txbxContent",
                 "merged_cells": ".//w:vMerge|.//w:gridSpan", "content_controls": ".//w:sdt",
                 "footnotes": ".//w:footnoteReference|.//w:endnoteReference",
                 "comments": ".//w:commentReference", "embedded_objects": ".//w:object"}
        for label, query in flags.items():
            if root.xpath(query, namespaces=NS):
                record["warnings"].append(label)
        if root.xpath("//*[local-name()='oMath' or local-name()='chart' or local-name()='relIds']"):
            record["warnings"].append("equations_charts_or_smartart")
        if root.xpath("//*[local-name()='AlternateContent']"):
            record["warnings"].append("alternate_content")
        for index, element in enumerate(root.xpath("./w:body/*", namespaces=NS)):
            kind = etree.QName(element).localname
            if kind not in ("p", "tbl"):
                continue
            block = {"index": index, "type": "table" if kind == "tbl" else "paragraph",
                     "text": text_of(element), "images": []}
            if kind == "tbl":
                block["rows"] = [[text_of(cell) for cell in row.xpath("./w:tc", namespaces=NS)]
                                 for row in element.xpath("./w:tr", namespaces=NS)]
                if element.xpath(".//w:tbl", namespaces=NS):
                    record["warnings"].append("nested_table")
            else:
                block["style"] = element.xpath("./w:pPr/w:pStyle/@w:val", namespaces=NS)
                block["numbering"] = element.xpath("./w:pPr/w:numPr/w:numId/@w:val", namespaces=NS)
                block["bold"] = element.xpath(".//w:r[w:rPr/w:b]/w:t/text()", namespaces=NS)
            ids = element.xpath(".//a:blip/@r:embed|.//v:imagedata/@r:id", namespaces=NS)
            if element.xpath(".//a:blip/@r:link", namespaces=NS):
                record["warnings"].append("external_image")
            if ids and kind == "tbl":
                record["warnings"].append("image_in_table")
            for rid in ids:
                rel = rels.get(rid)
                if rel is None or rel.get("TargetMode") == "External":
                    record["warnings"].append("unresolved_image")
                    continue
                name = rel.get("Target", "").replace("\\", "/")
                entry = name.lstrip("/") if name.startswith("/") else "word/" + name
                if ".." in Path(entry).parts or entry not in archive.namelist():
                    record["warnings"].append("unsupported_media_path")
                    continue
                data = archive.read(entry)
                sha = hashlib.sha256(data).hexdigest()
                image_path = output / "media" / (sha[:16] + Path(entry).suffix)
                image_path.parent.mkdir(exist_ok=True)
                image_path.write_bytes(data)
                item = {"path": str(image_path), "sha256": sha, "source_entry": entry, "block": index}
                block["images"].append(item)
                record["images"].append(item)
            record["blocks"].append(block)
        referenced = {item["source_entry"] for item in record["images"]}
        record["unused_media"] = [n for n in archive.namelist() if n.startswith("word/media/") and n not in referenced]
    record["warnings"] = sorted(set(record["warnings"]))
    save_json(target, record)
    return target


def markdown_check(path: Path, literal_text: list[str] | None = None) -> tuple[str, list]:
    content = path.read_text(encoding="utf-8")
    match = FILENAME.fullmatch(path.stem)
    if not match or any(c in path.stem for c in '<>:"/\\|?*') or match[2].startswith('+') or '+' in match[3]:
        raise ValueError("Use YYYY.MM.DD原标题（修改后）作者.md with no field separators or illegal characters.")
    datetime.strptime(match[1], "%Y.%m.%d")
    if content.count("\n## 关于商丘金蓬") != 1 or not content.strip().endswith(CLOSING):
        raise ValueError("Append the exact company-closing.md block exactly once.")
    if len(re.findall(r"^# ", content, re.M)) != 1:
        raise ValueError("Exactly one article H1 is required.")
    checked_content = content
    for original_phrase in literal_text or []:
        checked_content = checked_content.replace(original_phrase, "")
    if any(token in checked_content for token in EDITORIAL) or "修改后" in content:
        raise ValueError("Possible editorial leakage: inspect manually before building.")
    if "```" in content or "~~~" in content or re.search(r"(?m)^\s*[-*+]\s*$", content):
        raise ValueError("Code fences and empty list items are not supported.")
    for line in content.splitlines():
        if line.count("**") % 2 or re.search(r"\*\*\s|\s\*\*", line):
            # A space after a closing marker is valid; test paired contents instead.
            if line.count("**") % 2 or any(s != s.strip() for s in re.findall(r"\*\*(.*?)\*\*", line)):
                raise ValueError("Malformed bold marker: " + line[:100])
    for previous, current in zip(content.splitlines(), content.splitlines()[1:]):
        if previous.strip() and re.match(r"^[-*+] ", current):
            raise ValueError("Separate each list item with a blank line for portable paragraph rendering.")
    title, blocks = parse_blocks(path)
    if title != match[2]:
        raise ValueError("Filename title differs from the reader-facing H1; resolve metadata first.")
    return title, blocks


def normalize(text: str) -> str:
    text = re.sub(r"\[([^]]+)\]\(https?://[^)]+\)", r"\1", text).replace("**", "")
    return re.sub(r"\s+", "", text)


def verify(manifest: Path) -> dict:
    record = json.loads(manifest.read_text(encoding="utf-8"))
    source = json.loads(Path(record["snapshot"]).read_text(encoding="utf-8"))
    if digest(Path(source["source"])) != source["sha256"]:
        raise ValueError("Original Word changed after extraction.")
    md, word, html_path = [Path(record[k]) for k in ("markdown", "word", "html")]
    for key in ("markdown", "word", "html"):
        if digest(Path(record[key])) != record["hashes"][key]:
            raise ValueError(f"{key} changed after build; regenerate the manifest and re-run QA.")
    literals = record.get("literal_text", [])
    original_text = "\n".join(block["text"] for block in source["blocks"])
    if any(len(phrase) < 10 or phrase not in original_text for phrase in literals):
        raise ValueError("Literal-text exceptions require an exact contextual phrase from the original Word.")
    title, blocks = markdown_check(md, literals)
    doc = html_parser.fromstring(html_path.read_bytes())
    main = doc.xpath("//main[@data-layout='jinpeng-reference-v2']")
    if len(main) != 1 or doc.xpath("//script|//style|//link[@rel='stylesheet']"):
        raise ValueError("Nonportable HTML or missing layout.")
    main_text = normalize(main[0].text_content())
    if not record.get("cover_has_title") and doc.xpath("//main//h1/text()") != [title]:
        raise ValueError("Reader-facing HTML title is missing or changed.")
    with ZipFile(word) as archive:
        word_root = xml(archive.read("word/document.xml"))
        if word_root.xpath(".//w:ins|.//w:del|.//w:commentReference", namespaces=NS):
            raise ValueError("Revision or comment leaked into Word.")
        word_text = normalize(text_of(word_root))
        word_media = Counter(hashlib.sha256(archive.read(n)).hexdigest() for n in archive.namelist() if n.startswith("word/media/"))
        rels = {r.get("Id"): r.get("Target") for r in xml(archive.read("word/_rels/document.xml.rels"))}
        word_image_order = [hashlib.sha256(archive.read("word/" + rels[rid])).hexdigest()
                            for rid in word_root.xpath(".//a:blip/@r:embed", namespaces=NS)]
        numbering = xml(archive.read("word/numbering.xml"))
        starts = {node.get("{" + NS["w"] + "}abstractNumId"): int(node.xpath("./w:lvl/w:start/@w:val", namespaces=NS)[0])
                  for node in numbering.xpath("./w:abstractNum[w:lvl/w:start]", namespaces=NS)}
        numbering_ids = {node.get("{" + NS["w"] + "}numId"): node.xpath("./w:abstractNumId/@w:val", namespaces=NS)[0]
                         for node in numbering.xpath("./w:num", namespaces=NS)}
        word_numbers = [starts[numbering_ids[value]] for value in word_root.xpath(".//w:pPr/w:numPr/w:numId/@w:val", namespaces=NS)]
    expected_images = []
    md_table_count = 0
    cursors = {"html": 0, "word": 0}
    for block in blocks:
        if block["type"] == "image":
            expected_images.append(digest((md.parent / unquote(block["target"])).resolve()))
            continue
        if block["type"] == "hr":
            continue
        fragments = [cell for row in block["rows"] for cell in row] if block["type"] == "table" else [block.get("text", "")]
        md_table_count += block["type"] == "table"
        for fragment in fragments:
            needle = normalize(fragment)
            for key, haystack in (("html", main_text), ("word", word_text)):
                position = haystack.find(needle, cursors[key])
                if position < 0:
                    raise ValueError(f"{key}: missing or reordered text: {fragment[:80]}")
                cursors[key] = position + len(needle)
    actual_images = []
    for image in doc.xpath("//main//img"):
        src = image.get("src", "")
        if not re.match(r"^data:image/[^;]+;base64,", src):
            raise ValueError("Image is not embedded original media.")
        sha = hashlib.sha256(base64.b64decode(src.split(",", 1)[1], validate=True)).hexdigest()
        if sha != image.get("data-sha256"):
            raise ValueError("HTML decoded image hash differs from declared hash.")
        actual_images.append(sha)
    original_images = [item["sha256"] for item in source["images"]]
    if not (expected_images == actual_images == original_images == word_image_order):
        raise ValueError("Original/Markdown/HTML/Word image order or occurrence count mismatch.")
    if set(word_media) != set(expected_images):
        raise ValueError("Word contains missing or extra media.")
    for item in source["images"]:
        if digest(Path(item["path"])) != item["sha256"]:
            raise ValueError("Extracted original asset changed.")
    if len(doc.xpath("//main//table")) != md_table_count or len(word_root.xpath(".//w:tbl", namespaces=NS)) != md_table_count:
        raise ValueError("Table count mismatch.")
    source_shapes = [[len(row) for row in block["rows"]] for block in source["blocks"] if block["type"] == "table"]
    markdown_shapes = [[len(row) for row in block["rows"]] for block in blocks if block["type"] == "table"]
    if source_shapes != markdown_shapes:
        raise ValueError("Original table rows/columns were lost or reordered before rendering.")
    expected_numbers = [block["number"] for block in blocks if block["type"] == "numbered"]
    html_numbers = [int(node.get("value", "-1")) for node in doc.xpath("//main//ol/li")]
    if expected_numbers != html_numbers or expected_numbers != word_numbers:
        raise ValueError("Step numbering changed in HTML or Word.")
    checked_html_text = main[0].text_content()
    for original_phrase in literals:
        checked_html_text = checked_html_text.replace(original_phrase, "")
    if "修改后" in checked_html_text or any(token in checked_html_text for token in EDITORIAL):
        raise ValueError("Editorial content leaked into HTML.")
    if len(doc.xpath("//section[@data-role='company']")) != 1:
        raise ValueError("Company closing not rendered exactly once.")
    return {"structural": "pass", "images": len(actual_images), "tables": md_table_count,
            "semantic_review": "requires_agent_review", "visual_review": "not_run", "wechat_paste": "not_run"}


def build(md: Path, snapshot: Path, audit: Path, workspace: Path, replace: bool = False,
          literal_text: list[str] | None = None, cover_has_title: bool = False) -> Path:
    md, snapshot, audit, workspace = [p.resolve() for p in (md, snapshot, audit, workspace)]
    title, _ = markdown_check(md, literal_text)
    if md.parent != workspace / DEFAULTS["markdown"]:
        raise ValueError("Reviewed Markdown must be directly in workspace/Markdown.")
    source = json.loads(snapshot.read_text(encoding="utf-8"))
    if source["warnings"]:
        raise ValueError("Complex source requires manual fidelity handling: " + ", ".join(source["warnings"]))
    if digest(Path(source["source"])) != source["sha256"]:
        raise ValueError("Original changed since extraction.")
    if not audit.is_file() or not audit.read_text(encoding="utf-8").strip():
        raise ValueError("Provide a separate completed review record; script cannot perform technical review.")
    word_dir, html_dir = [workspace / DEFAULTS[k] for k in ("edited_word", "html")]
    manifest = workspace / "_work" / "qa" / md.stem / "build.json"
    targets = [word_dir / (md.stem + ".docx"), html_dir / (md.stem + ".html"), manifest]
    if not replace and any(p.exists() for p in targets):
        raise FileExistsError("Output exists; inspect ownership/version before using --replace.")
    word = build_document(md, output_root=word_dir)
    html_path, html_record = build_html(md, output_root=html_dir, cover_has_title=cover_has_title)
    validate_html(html_path, html_record)
    record = {"title": title, "markdown": str(md), "word": str(word), "html": str(html_path),
              "snapshot": str(snapshot), "audit": str(audit), "source_sha256": source["sha256"],
              "hashes": {"markdown": digest(md), "word": digest(word), "html": digest(html_path)},
              "backup_status": "not_run", "literal_text": literal_text or [], "cover_has_title": cover_has_title}
    save_json(manifest, record)
    record["checks"] = verify(manifest)
    save_json(manifest, record)
    return manifest


def backup(manifest: Path, destination: Path, replace: bool = False) -> Path:
    verify(manifest)
    record = json.loads(manifest.read_text(encoding="utf-8"))
    source = Path(record["html"])
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / source.name
    if target.exists() and digest(target) != digest(source) and not replace:
        raise FileExistsError("Different backup with the same name; confirm version before --replace.")
    if not target.exists() or digest(target) != digest(source):
        shutil.copy2(source, target)
    if digest(target) != digest(source):
        raise IOError("Backup hash mismatch.")
    record.update(backup_html=str(target.resolve()), backup_sha256=digest(target), backup_status="pass")
    save_json(manifest, record)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    extraction = commands.add_parser("extract")
    extraction.add_argument("source", type=Path)
    extraction.add_argument("--out", type=Path, required=True)
    builder = commands.add_parser("build")
    builder.add_argument("markdown", type=Path)
    builder.add_argument("--snapshot", type=Path, required=True)
    builder.add_argument("--audit", type=Path, required=True)
    builder.add_argument("--workspace", type=Path, default=Path(DEFAULTS["workspace"]))
    builder.add_argument("--replace", action="store_true")
    builder.add_argument("--literal-text", action="append", default=[], help="Exact original contextual phrase, manually confirmed not to be editorial notes")
    builder.add_argument("--cover-has-title", action="store_true", help="Use only after visually confirming the first cover already includes the complete title")
    checker = commands.add_parser("verify")
    checker.add_argument("manifest", type=Path)
    copier = commands.add_parser("backup")
    copier.add_argument("manifest", type=Path)
    copier.add_argument("--destination", type=Path, default=Path(DEFAULTS["backup"]))
    copier.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    if args.command == "extract":
        result = extract(args.source, args.out)
    elif args.command == "build":
        result = build(args.markdown, args.snapshot, args.audit, args.workspace, args.replace, args.literal_text, args.cover_has_title)
    elif args.command == "verify":
        result = verify(args.manifest)
    else:
        result = backup(args.manifest, args.destination, args.replace)
    print(json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else result)


if __name__ == "__main__":
    main()
