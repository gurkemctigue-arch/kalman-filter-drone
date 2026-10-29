"use strict";
// Explicit DEVELOPMENT_ONLY in-memory content; no DOCX/PDF file is published.
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const { Packer } = require("docx");
const JSZip = require("jszip");
const { argsFor, canonical, columnWidths, validateStructure, makeDocument } = require("../scripts/build_reliability_v4_documents.cjs");
const hash = (value) => crypto.createHash("sha256").update(value).digest("hex");
const seal = (pack) => { const unsigned = { ...pack }; delete unsigned.document_package_sha256;
  pack.document_package_sha256 = hash(Buffer.from(canonical(unsigned))); return pack; };
const clone = (value) => JSON.parse(JSON.stringify(value));

async function main() {
  const content = { title: "纯合成夹具：中文、A4与表格验证", status_label: "DEVELOPMENT_ONLY: FIXTURE_ONLY, never a real experiment",
    blocks: [{ type: "heading", level: 1, text: "保留失败与缺失" },
      { type: "paragraph", text: "该内容仅验证Word XML，不是正式研究结果。" },
      { type: "bullet", text: "右删失保持缺失" },
      { type: "table", headers: ["类别", "有效/计划", "位置RMSE / m"], rows: [["FIXTURE_ONLY", "0/10", "缺失"]] },
      { type: "heading", level: 2, text: "共同支持网格" }] };
  const pack = seal({ schema_version: 1, kind: "RELIABILITY_V4_DOCUMENT_PACKAGE", mode: "draft", scope: "DEVELOPMENT_ONLY",
    request: {}, generated_utc: "FIXTURE_ONLY", completion: { project_acceptance_claimed: false, all_280_slots_terminal: false },
    documents: { plan: content, report: clone(content) } });
  assert.equal(validateStructure(pack).mode, "draft");
  assert.equal(canonical("中文😀"), '"\\u4e2d\\u6587\\ud83d\\ude00"');
  const tampered = clone(pack);
  tampered.documents.plan.blocks[1].text = "changed";
  assert.throws(() => validateStructure(tampered), /digest/);
  const noStatus = clone(pack);
  noStatus.documents.plan.status_label = "完成";
  assert.throws(() => validateStructure(seal(noStatus)), /draft status/);
  const fakeFinal = clone(pack);
  fakeFinal.mode = "final";
  assert.throws(() => validateStructure(seal(fakeFinal)), /FINAL requires/);
  const fakeClaim = clone(pack);
  fakeClaim.completion.project_acceptance_claimed = true;
  assert.throws(() => validateStructure(seal(fakeClaim)), /acceptance claim/);
  const badTable = clone(pack);
  badTable.documents.plan.blocks[3].rows[0].pop();
  assert.throws(() => validateStructure(seal(badTable)), /Malformed table/);
  const badBlock = clone(pack);
  badBlock.documents.plan.blocks[1].type = "html";
  assert.throws(() => validateStructure(seal(badBlock)), /Unknown block/);
  const newline = clone(pack);
  newline.documents.plan.blocks[1].text = "first\nsecond";
  assert.throws(() => validateStructure(seal(newline)), /separate paragraphs/);
  const widths = columnWidths([["A", "long 中文 heading", "C"], ["1", "2", "3"]]);
  assert.equal(widths.reduce((left, right) => left + right, 0), 9746);
  assert.ok(widths.every((value) => value > 0));
  assert.equal(argsFor(["--input", "fixture.json", "--validate-only"]).validateOnly, true);
  assert.throws(() => argsFor(["--input", "fixture.json"]), /required/);
  // Exercise docx-js in memory, then inspect the actual OpenXML layout.
  const bytes = await Packer.toBuffer(makeDocument(content, pack, "Microsoft YaHei"));
  const archive = await JSZip.loadAsync(bytes);
  const xml = await archive.file("word/document.xml").async("string");
  const settings = await archive.file("word/settings.xml").async("string");
  assert.ok(xml.includes('w:w="11906"') && xml.includes('w:h="16838"'));
  assert.ok(xml.includes('w:tblW w:type="dxa" w:w="9746"'));
  assert.equal((xml.match(/<w:gridCol /g) || []).length, 3);
  assert.equal((xml.match(/<w:tcW /g) || []).length, 6);
  assert.ok(xml.includes("<w:tblHeader") && xml.includes("<w:cantSplit"));
  assert.ok(xml.includes('w:pStyle w:val="Heading1"') && xml.includes('w:pStyle w:val="Heading2"'));
  assert.ok(xml.includes("TOC") && xml.includes("DEVELOPMENT_ONLY") && xml.includes("FIXTURE_ONLY"));
  assert.ok(settings.includes("updateFields"));
  process.stdout.write("v4 Word structure: 21 fixture assertions passed; in-memory XML only, no document files or PDF rendered.\n");
}
main().catch((error) => { process.stderr.write(String(error.stack || error) + "\n"); process.exitCode = 1; });
