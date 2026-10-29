#!/usr/bin/env node
"use strict";
/* Render only source-reconstructed v4 document packages. Old v3 gates stay intact. */
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { spawnSync } = require("node:child_process");
const {
  AlignmentType, BorderStyle, Document, Footer, Header, HeadingLevel, ImageRun,
  LevelFormat, PageBreak, PageNumber, Packer, Paragraph, ShadingType, Table,
  TableCell, TableLayoutType, TableOfContents, TableRow, TextRun, VerticalAlign, WidthType,
} = require("docx");

const ROOT = path.resolve(__dirname, "..");
const A4 = { width: 11906, height: 16838 };
const MARGIN = 1080;
const TEXT_WIDTH = A4.width - 2 * MARGIN;
const digest = (value) => crypto.createHash("sha256").update(value).digest("hex");

function readSmall(filename) {
  if (!fs.statSync(filename).isFile() || fs.statSync(filename).size > 128 * 1024 * 1024) {
    throw new Error("Missing or oversized document source: " + filename);
  }
  return fs.readFileSync(filename);
}

function canonical(value) {
  if (value === null || typeof value !== "object") return JSON.stringify(value).replace(/[\u007f-\uffff]/g,
    (character) => "\\u" + character.charCodeAt(0).toString(16).padStart(4, "0"));
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  return "{" + Object.keys(value).sort().map((key) => canonical(key) + ":" + canonical(value[key])).join(",") + "}";
}

function validateStructure(pack) {
  if (pack.schema_version !== 1 || pack.kind !== "RELIABILITY_V4_DOCUMENT_PACKAGE"
      || !["draft", "final"].includes(pack.mode) || !pack.documents || !pack.request
      || pack.completion?.project_acceptance_claimed !== false) {
    throw new Error("Unsupported v4 document package or an unsupported acceptance claim");
  }
  const unsigned = { ...pack };
  delete unsigned.document_package_sha256;
  if (digest(Buffer.from(canonical(unsigned), "utf8")) !== pack.document_package_sha256) {
    throw new Error("Document package digest changed");
  }
  if (pack.mode === "draft" && (pack.scope !== "DEVELOPMENT_ONLY"
      || pack.completion.all_280_slots_terminal !== false)) throw new Error("Draft status is not explicit");
  if (pack.mode === "final") {
    if (pack.scope !== "FORMAL_EXECUTION_LEDGER_COMPLETE" || pack.completion.all_280_slots_terminal !== true
        || pack.completion.replay_all_20_slots_accounted !== true || pack.replay_outcomes.length !== 20
        || new Set(pack.replay_outcomes.map((row) => row.slot_id)).size !== 20) {
      throw new Error("FINAL requires the complete source-verified 280+20-slot ledger");
    }
    for (const [name, mode, count] of [["core", "FORMAL", 120], ["extension", "EXTENSION_FORMAL", 160]]) {
      const row = pack.cohorts?.[name];
      if (row?.mode !== mode || row.planned_slots !== count || row.terminal_slots !== count
          || row.all_slots_terminal !== true) throw new Error("FINAL cohort is incomplete");
    }
  }
  if (Object.keys(pack.documents).sort().join(",") !== "plan,report") throw new Error("Expected plan and report");
  for (const document of Object.values(pack.documents)) {
    if (typeof document.title !== "string" || typeof document.status_label !== "string"
        || !Array.isArray(document.blocks) || !document.blocks.length
        || pack.mode === "draft" && !document.status_label.includes("DEVELOPMENT_ONLY")) {
      throw new Error("Missing document content or draft status");
    }
    for (const block of document.blocks) {
      if (!["heading", "paragraph", "bullet", "table", "figure"].includes(block.type)) throw new Error("Unknown block type");
      if (["heading", "paragraph", "bullet"].includes(block.type)
          && (typeof block.text !== "string" || /[\r\n]/.test(block.text))) throw new Error("Use separate paragraphs");
      if (block.type === "heading" && ![1, 2].includes(block.level)) throw new Error("Unsupported heading level");
      if (block.type === "table" && (!Array.isArray(block.headers) || block.headers.length < 1 || block.headers.length > 8
          || !Array.isArray(block.rows) || block.rows.some((row) => row.length !== block.headers.length)
          || [...block.headers, ...block.rows.flat()].some((value) => typeof value !== "string" || /[\r\n]/.test(value)))) {
        throw new Error("Malformed table");
      }
      if (block.type === "figure" && (!/^[a-f0-9]{64}$/.test(block.sha256 || "")
          || !Number.isInteger(block.bytes) || block.bytes < 1 || path.extname(block.path).toLowerCase() !== ".png")) {
        throw new Error("Malformed figure binding");
      }
    }
  }
  return pack;
}

function verifyEvidence(filename, python) {
  const pack = validateStructure(JSON.parse(readSmall(filename).toString("utf8").replace(/^\uFEFF/, "")));
  const source = pack.sources.find((row) => row.role === "document_renderer_implementation");
  if (!source || source.sha256 !== digest(fs.readFileSync(__filename))) throw new Error("Renderer source differs from saved package");
  const result = spawnSync(python, ["-B", path.join(ROOT, "scripts/build_reliability_v4_report.py"),
    "--verify-package", filename], { cwd: ROOT, encoding: "utf8", windowsHide: true, maxBuffer: 4 * 1024 * 1024 });
  if (result.error || result.status !== 0) throw new Error("Original v4 evidence verification failed: " + (result.error || result.stderr || result.stdout));
  const receipt = JSON.parse(result.stdout.trim());
  if (receipt.validation !== "PACKAGE_EVIDENCE_RECONSTRUCTED" || receipt.sha256 !== pack.document_package_sha256) {
    throw new Error("Python evidence receipt disagrees");
  }
  return pack;
}

function run(text, font, extra = {}) {
  return new TextRun({ text, font, ...extra });
}

function columnWidths(rows, width = TEXT_WIDTH) {
  const weights = rows[0].map((_, index) => Math.sqrt(Math.max(8, Math.min(48,
    Math.max(...rows.map((row) => Array.from(row[index] || "").reduce((sum, char) => sum + (char.charCodeAt(0) > 255 ? 2 : 1), 0)))))));
  const total = weights.reduce((left, right) => left + right, 0);
  const widths = weights.map((weight) => Math.floor(width * weight / total));
  widths[widths.length - 1] += width - widths.reduce((left, right) => left + right, 0);
  return widths;
}

function makeTable(block, font) {
  const rows = [block.headers, ...block.rows];
  if (rows.length === 1) rows.push(block.headers.map((_, index) => index === 0 ? "暂无已记录结果" : "缺失"));
  const widths = columnWidths(rows);
  const border = { style: BorderStyle.SINGLE, size: 4, color: "D7DFEA" };
  return new Table({ width: { size: TEXT_WIDTH, type: WidthType.DXA }, columnWidths: widths,
    layout: TableLayoutType.FIXED,
    borders: { top: border, bottom: border, left: border, right: border, insideHorizontal: border, insideVertical: border },
    rows: rows.map((row, index) => new TableRow({ tableHeader: index === 0, cantSplit: true,
      children: row.map((text, column) => new TableCell({ width: { size: widths[column], type: WidthType.DXA },
        verticalAlign: VerticalAlign.TOP, margins: { top: 70, bottom: 70, left: 70, right: 70 },
        shading: { type: ShadingType.CLEAR, fill: index === 0 ? "E4EDF7" : index % 2 ? "FFFFFF" : "F5F8FC" },
        children: [new Paragraph({ spacing: { before: 0, after: 0, line: 250 },
          children: [run(text, font, { size: row.length > 5 ? 17 : 18, bold: index === 0 })] })],
      })),
    })),
  });
}

function makeFigure(block, font) {
  const bytes = readSmall(block.path);
  if (bytes.length !== block.bytes || digest(bytes) !== block.sha256
      || bytes.length < 24 || !bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))) {
    throw new Error("Bound PNG changed or has an invalid header: " + block.path);
  }
  const width = bytes.readUInt32BE(16), height = bytes.readUInt32BE(20);
  if (!width || !height) throw new Error("Empty figure geometry");
  const scale = Math.min(TEXT_WIDTH / 15 / width, 640 / height, 1);
  return [new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true,
    children: [new ImageRun({ type: "png", data: bytes,
      transformation: { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) },
      altText: { title: block.caption, description: block.scope, name: path.basename(block.path) } })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 },
    children: [run(block.caption + "；" + block.scope, font, { size: 18, color: "475569" })] })];
}

function makeDocument(content, pack, font) {
  const children = [
    new Paragraph({ spacing: { before: 1500, after: 500 }, alignment: AlignmentType.CENTER,
      children: [run(content.title, font, { size: 36, bold: true, color: "173454" })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 350 },
      children: [run(content.status_label, font, { size: 21, bold: true, color: pack.mode === "final" ? "174C44" : "895812" })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, children: [run("方案版本：v4　｜　文档模式：" + pack.mode.toUpperCase(), font, { size: 21 })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, children: [run("生成时间：" + pack.generated_utc, font, { size: 18, color: "64748B" })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 500 },
      children: [run("仿真研究 · 行人与汽车 · 唯一实例与指定个体 · 三轴云台", font, { size: 20 })] }),
    new Paragraph({ children: [new PageBreak()] }),
    new TableOfContents("目录", { hyperlink: true, headingStyleRange: "1-2" }),
    new Paragraph({ children: [run("目录页码由Word/LibreOffice更新字段后生成；最终PDF须逐页检查。", font, { size: 17, color: "64748B" })] }),
    new Paragraph({ children: [new PageBreak()] }),
  ];
  for (const block of content.blocks) {
    if (block.type === "heading") children.push(new Paragraph({
      heading: block.level === 1 ? HeadingLevel.HEADING_1 : HeadingLevel.HEADING_2,
      keepNext: true, children: [run(block.text, font)] }));
    else if (block.type === "paragraph" || block.type === "bullet") children.push(new Paragraph({
      ...(block.type === "bullet" ? { numbering: { reference: "v4-bullets", level: 0 } } : {}),
      children: [run(block.text, font)] }));
    else if (block.type === "table") children.push(makeTable(block, font), new Paragraph({ text: "", spacing: { after: 100 } }));
    else if (block.type === "figure") children.push(...makeFigure(block, font));
  }
  return new Document({ title: content.title, subject: content.status_label,
    creator: "UAV Tracking Project", description: "Source-bound v4 simulation evidence; execution and acceptance are separate",
    features: { updateFields: true },
    styles: { default: { document: { run: { font, size: 22 }, paragraph: { spacing: { after: 150, line: 330 }, widowControl: true } } },
      paragraphStyles: [
        { id: "Heading1", name: "heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { font, size: 29, bold: true, color: "173454" }, paragraph: { outlineLevel: 0, spacing: { before: 320, after: 160 }, keepNext: true } },
        { id: "Heading2", name: "heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { font, size: 24, bold: true, color: "285470" }, paragraph: { outlineLevel: 1, spacing: { before: 220, after: 120 }, keepNext: true } },
      ] },
    numbering: { config: [{ reference: "v4-bullets", levels: [{ level: 0, format: LevelFormat.BULLET,
      text: "\u2022", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 440, hanging: 220 } } } }] }] },
    sections: [{ properties: { page: { size: A4, margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN, header: 440, footer: 440 } } },
      headers: { default: new Header({ children: [new Paragraph({
        border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "CED8E5", space: 5 } },
        children: [run("RGB-D云台无人机目标跟踪与自主跟随 · v4 · " + pack.scope, font, { size: 15, color: "64748B" })] })] }) },
      footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
        children: [run("第 ", font, { size: 16 }), new TextRun({ children: [PageNumber.CURRENT], size: 16 }),
          run(" 页 / 共 ", font, { size: 16 }), new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 16 }), run(" 页", font, { size: 16 })] })] }) },
      children }],
  });
}

function argsFor(argv) {
  const options = { python: "python", font: "Microsoft YaHei", validateOnly: false };
  for (let index = 0; index < argv.length; index++) {
    const flag = argv[index];
    if (flag === "--help") return { help: true };
    if (flag === "--validate-only") { options.validateOnly = true; continue; }
    if (!["--input", "--output", "--python", "--font"].includes(flag) || !argv[index + 1] || argv[index + 1].startsWith("--")) {
      throw new Error("Unknown option/missing value: " + flag);
    }
    options[flag.slice(2)] = argv[++index];
  }
  if (!options.input || !options.validateOnly && !options.output) throw new Error("--input and --output are required; --validate-only omits rendering");
  return options;
}

async function main(argv = process.argv.slice(2)) {
  const options = argsFor(argv);
  if (options.help) {
    process.stdout.write("node scripts/build_reliability_v4_documents.cjs --input /package/documents.json --output /new/documents [--python python] [--font FONT] [--validate-only]\n");
    return;
  }
  const input = path.resolve(options.input);
  const pack = verifyEvidence(input, options.python);
  if (options.validateOnly) {
    process.stdout.write(JSON.stringify({ validation: "V4_DOCUMENT_SOURCES_VERIFIED_NO_RENDERING", mode: pack.mode }) + "\n");
    return;
  }
  const output = path.resolve(options.output);
  if (fs.existsSync(output)) throw new Error("Choose a new output directory; preserve existing documents");
  if (output === path.dirname(input) || output.startsWith(path.dirname(input) + path.sep)) throw new Error("Keep DOCX outside the original package directory");
  fs.mkdirSync(output, { recursive: true });
  const manifest = { schema_version: 1, kind: "RELIABILITY_V4_DOCX_RENDER", mode: pack.mode, scope: pack.scope,
    input: { path: input, sha256: digest(readSmall(input)), package_digest: pack.document_package_sha256 },
    renderer: { path: __filename, sha256: digest(fs.readFileSync(__filename)), node: process.version, font: options.font },
    outputs: [], validation: "DOCX_GENERATED_PENDING_PDF_RENDER_AND_PER_PAGE_VISUAL_REVIEW" };
  for (const [role, content] of Object.entries(pack.documents)) {
    const bytes = await Packer.toBuffer(makeDocument(content, pack, options.font));
    const name = "v4_" + role + "_" + pack.mode + ".docx";
    fs.writeFileSync(path.join(output, name), bytes, { flag: "wx" });
    manifest.outputs.push({ role, path: name, bytes: bytes.length, sha256: digest(bytes) });
  }
  // Recheck the package and all upstream sources after serialization as well.
  verifyEvidence(input, options.python);
  fs.writeFileSync(path.join(output, "render_manifest.json"), JSON.stringify(manifest, null, 2) + "\n", { flag: "wx" });
  process.stdout.write(JSON.stringify(manifest) + "\n");
}

module.exports = { argsFor, canonical, columnWidths, validateStructure, verifyEvidence, makeTable, makeDocument, main };
if (require.main === module) main().catch((error) => { process.stderr.write(String(error.stack || error) + "\n"); process.exitCode = 1; });
