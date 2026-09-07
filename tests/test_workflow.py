import json
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from fixtures import create_fixture
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from article_tool import NS, backup, build, digest, markdown_check, text_of, verify, xml
from _build_wechat_html import inline_markup, split_intro
from _article_tables import read_table
from docx import Document


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manifest = create_fixture(self.root)
        self.record = json.loads(self.manifest.read_text(encoding="utf-8"))

    def tearDown(self):
        self.temp.cleanup()

    def test_three_formats_and_backup(self):
        result = verify(self.manifest)
        self.assertEqual(result["images"], 1)
        self.assertEqual(result["tables"], 1)
        target = backup(self.manifest, self.root / "backup")
        self.assertEqual(digest(target), digest(Path(self.record["html"])))
        self.assertEqual(target, backup(self.manifest, self.root / "backup"))
        self.assertEqual(Document(self.record["word"]).core_properties.author, "李明")

    def test_six_items_remain_visible_paragraphs(self):
        text = Path(self.record["html"]).read_text(encoding="utf-8")
        for index in range(1, 7):
            self.assertIn(f"第{index}项正文应当保持可见。", text)
        self.assertNotIn("<li", text)
        self.assertNotIn("**", text)
        self.assertIn("color:inherit", text)

    def test_explicit_step_numbers_survive_image_break(self):
        md = Path(self.record["markdown"])
        content = md.read_text(encoding="utf-8")
        content = content.replace("- **检查项1：** 第1项正文应当保持可见。", "4. 第1项正文应当保持可见。")
        content = content.replace("图1 合成测试图", "5. 图1 合成测试图")
        md.write_text(content, encoding="utf-8")
        build(md, Path(self.record["snapshot"]), Path(self.record["audit"]), self.root, replace=True)
        html = Path(self.record["html"]).read_text(encoding="utf-8")
        self.assertIn('<ol start="4"', html)
        self.assertIn('<ol start="5"', html)
        self.assertEqual(verify(self.manifest)["structural"], "pass")

    def test_cover_label_does_not_hide_title(self):
        md = Path(self.record["markdown"])
        content = md.read_text(encoding="utf-8")
        old_image = "![测试图片](assets/synthetic.png)"
        content = content.replace(old_image, "")
        h1, rest = content.split("\n\n", 1)
        md.write_text(h1 + "\n\n![封面](assets/synthetic.png)\n\n" + rest, encoding="utf-8")
        build(md, Path(self.record["snapshot"]), Path(self.record["audit"]), self.root, replace=True)
        html = Path(self.record["html"]).read_text(encoding="utf-8")
        self.assertIn("<h1 ", html)
        self.assertEqual(verify(self.manifest)["structural"], "pass")

    def test_reference_label_punctuation_is_preserved(self):
        md = Path(self.record["markdown"])
        content = md.read_text(encoding="utf-8").replace("文字与原图均应完整保留。", "参考资料：\n\n[测试链接](https://example.com/)")
        md.write_text(content, encoding="utf-8")
        build(md, Path(self.record["snapshot"]), Path(self.record["audit"]), self.root, replace=True)
        self.assertIn("参考资料：</p>", Path(self.record["html"]).read_text(encoding="utf-8"))

    def test_literal_plus_in_original_title_is_allowed(self):
        md = Path(self.record["markdown"])
        renamed = md.with_name(md.name.replace("物料与工艺", "C++设备数据采集"))
        renamed.write_text(md.read_text(encoding="utf-8").replace("物料与工艺", "C++设备数据采集"), encoding="utf-8")
        manifest = build(renamed, Path(self.record["snapshot"]), Path(self.record["audit"]), self.root)
        self.assertEqual(verify(manifest)["structural"], "pass")

    def test_new_editorial_phrase_cannot_be_exempted(self):
        phrase = "审查发现：这是人为添加的编辑意见，原稿没有这句话。"
        md = Path(self.record["markdown"])
        md.write_text(md.read_text(encoding="utf-8").replace("文字与原图均应完整保留。", phrase), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "original Word"):
            build(md, Path(self.record["snapshot"]), Path(self.record["audit"]), self.root, replace=True, literal_text=[phrase])

    def test_source_mutation_is_detected(self):
        source = self.root / "原稿.docx"
        source.write_bytes(source.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "Original Word changed"):
            verify(self.manifest)

    def test_output_mutation_is_detected(self):
        html = Path(self.record["html"])
        html.write_text(html.read_text(encoding="utf-8").replace("第6项正文", "missing"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed after build"):
            verify(self.manifest)

    def test_asset_mutation_is_detected(self):
        asset = self.root / "Markdown/assets/synthetic.png"
        asset.write_bytes(asset.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "image order"):
            verify(self.manifest)

    def test_existing_outputs_are_protected(self):
        with self.assertRaises(FileExistsError):
            build(Path(self.record["markdown"]), Path(self.record["snapshot"]), Path(self.record["audit"]), self.root)

    def test_missing_table_rows_are_detected(self):
        md = Path(self.record["markdown"])
        content = md.read_text(encoding="utf-8")
        md.write_text(content.replace("| 测试设备 | 1.84 | 小数不应被截开 |", ""), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Original table"):
            build(md, Path(self.record["snapshot"]), Path(self.record["audit"]), self.root, replace=True)

    def test_duplicate_image_occurrences_are_detected(self):
        md = Path(self.record["markdown"])
        content = md.read_text(encoding="utf-8")
        image = "![测试图片](assets/synthetic.png)"
        md.write_text(content.replace(image, image + "\n\n" + image), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "image order"):
            build(md, Path(self.record["snapshot"]), Path(self.record["audit"]), self.root, replace=True)

    def test_backup_collision_is_protected(self):
        folder = self.root / "backup"
        folder.mkdir()
        target = folder / Path(self.record["html"]).name
        target.write_text("another article", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            backup(self.manifest, folder)
        self.assertEqual(target.read_text(encoding="utf-8"), "another article")

    def test_malformed_markdown_is_rejected(self):
        md = Path(self.record["markdown"])
        original = md.read_text(encoding="utf-8")
        md.write_text(original.replace("**检查项1：**", "**检查项1： **"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "bold"):
            markdown_check(md)

    def test_editorial_leakage_is_rejected(self):
        md = Path(self.record["markdown"])
        md.write_text(md.read_text(encoding="utf-8").replace("文字与原图", "修改建议：文字与原图"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "editorial"):
            markdown_check(md)

    def test_closing_and_title_are_required(self):
        md = Path(self.record["markdown"])
        md.write_text(md.read_text(encoding="utf-8").replace("站好每一班岗", "变更固定结尾"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "company-closing"):
            markdown_check(md)


class MarkupTests(unittest.TestCase):
    def test_empty_edge_table_cells_are_preserved(self):
        rows, end = read_table(["||B|C||", "|---|---|---|---|", "||2|3||"], 0)
        self.assertEqual(rows, [["", "B", "C", ""], ["", "2", "3", ""]])
        self.assertEqual(end, 3)

    def test_word_tabs_and_breaks_survive_extraction(self):
        element = xml(f'<w:p xmlns:w="{NS["w"]}"><w:r><w:t>A</w:t><w:tab/><w:t>B</w:t><w:br/><w:t>C</w:t></w:r></w:p>'.encode())
        self.assertEqual(text_of(element), "A\tB\nC")

    def test_thousands_separator_is_not_a_breakpoint(self):
        text = "这是足够长的前缀文字用于测试自动拆分导语123456784,010吨原料"
        lead, detail = split_intro(text)
        self.assertNotEqual(lead[-2:], "4,")
        self.assertEqual(lead + detail, text)

    def test_bold_markup_stays_in_one_piece(self):
        text = "这段文字足够长，**重要信息仍然需要保持完整，这里不能截断加粗标记**。"
        self.assertEqual(split_intro(text), (text, ""))

    def test_html_in_source_is_escaped(self):
        rendered = inline_markup('<script>alert("x")</script>')
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)


if __name__ == "__main__":
    unittest.main()
