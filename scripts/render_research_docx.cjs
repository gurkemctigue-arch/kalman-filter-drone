#!/usr/bin/env node
/* Render the FINAL saved research Markdown; never calculates research results.
 * Requires npm docx. Invoke only after all flight and offline work has ended.
 */
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const {
  AlignmentType, BorderStyle, Document, ExternalHyperlink, Footer, Header,
  HeadingLevel, ImageRun, LevelFormat, LineRuleType, PageNumber, PageOrientation, Paragraph,
  Packer, SectionType, ShadingType, Table, TableCell, TableLayoutType, TableRow,
  TextRun, VerticalAlign, WidthType,
} = require("docx");

const FONT = "Noto Sans CJK SC";
const A4 = { width: 11906, height: 16838 };
const MARGIN = 1080;
const sha = (buffer) => crypto.createHash("sha256").update(buffer).digest("hex");

function argsFor(argv) {
  const options = { figures: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const flag = argv[index];
    if (flag === "--help") {
      process.stdout.write("node scripts/render_research_docx.cjs --input FINAL.md --output FINAL.docx [--provenance FINAL.sources.json] [--figure FIGURE.png ...]\n");
      process.exit(0);
    }
    if (!["--input", "--output", "--provenance", "--figure"].includes(flag)
        || !argv[index + 1] || argv[index + 1].startsWith("--")) {
      throw new Error("Unknown argument or missing value: " + flag);
    }
    const value = argv[++index];
    if (flag === "--figure") options.figures.push(path.resolve(value));
    else options[flag.slice(2)] = path.resolve(value);
  }
  if (!options.input || !options.output) throw new Error("--input and --output are required");
  if (path.extname(options.input).toLowerCase() !== ".md"
      || path.extname(options.output).toLowerCase() !== ".docx") {
    throw new Error("Expected a Markdown input and a DOCX output");
  }
  options.provenance ||= options.input.replace(/\.md$/i, ".sources.json");
  options.sidecar = options.output.replace(/\.docx$/i, ".render.json");
  if (new Set(options.figures).size !== options.figures.length) throw new Error("Duplicate appendix figure");
  for (const target of [options.output, options.sidecar]) {
    if (fs.existsSync(target)) throw new Error("Preserve existing output; choose a new filename: " + target);
  }
  return options;
}

function readSmall(filename, limit = 32 * 1024 * 1024) {
  if (fs.statSync(filename).size > limit) throw new Error("Input exceeds the document-source size limit: " + filename);
  return fs.readFileSync(filename);
}

function validateCompletionProvenance(provenance, inputDirectory) {
  const ledger = provenance.supplement_ledger;
  if (provenance.execution_ledger_complete !== true
      || provenance.completion_contract_version !== 2
      || !ledger || ledger.complete !== true || ledger.terminal_slots !== 16
      || !provenance.metric_supplement || provenance.metric_supplement.complete !== true
      || provenance.metric_supplement.main_flights !== 166 || provenance.metric_supplement.engineering_flights !== 16
      || !/^[a-f0-9]{64}$/.test(ledger.plan_sha256 || "")) {
    throw new Error("Finalize the bound 166 flights, 166 offline slots, 16 engineering flights and 16 supplementary slots; legacy completion flags are insufficient");
  }
  const counts = Object.entries(ledger.status_counts || {});
  if (!counts.length || counts.some(([status, count]) =>
    !["RECORDED", "INCOMPLETE_EVIDENCE", "INTERRUPTED"].includes(status)
      || !Number.isInteger(count) || count < 0)
      || counts.reduce((sum, [, count]) => sum + count, 0) !== 16) {
    throw new Error("Supplementary bookkeeping contains nonterminal or invalid counts");
  }
  const roles = ["main_summary", "main_plan", "offline_manifest", "engineering_manifest", "supplement_manifest", "metric_supplement"];
  const records = provenance.completion_sources;
  if (!Array.isArray(records) || records.length !== roles.length
      || new Set(records.map((record) => record.role)).size !== roles.length
      || records.some((record) => !roles.includes(record.role))) {
    throw new Error("Missing exact six-source ledger/metric SHA bindings");
  }
  const verified = records.map((record) => {
    const relative = record.report_relative_path;
    if (record.exists !== true || typeof relative !== "string" || !relative
        || path.isAbsolute(relative) || /^[a-z][a-z0-9+.-]*:/i.test(relative)
        || !/^[a-f0-9]{64}$/.test(record.sha256 || "")) {
      throw new Error("A completion source lacks a portable relative path or saved SHA: " + record.role);
    }
    // Relative paths make Linux-generated provenance usable on Windows after
    // archiving the same directory tree. No frozen Linux root is inferred.
    const filename = path.resolve(inputDirectory, relative);
    const bytes = readSmall(filename);
    if (bytes.length !== record.bytes || sha(bytes) !== record.sha256) {
      throw new Error("Completion source changed after the Markdown report was saved: " + record.role);
    }
    const data = JSON.parse(bytes.toString("utf8").replace(/^\uFEFF/, ""));
    return { role: record.role, path: filename, bytes: bytes.length, sha256: sha(bytes), data };
  });
  if (new Set(verified.map((record) => record.path)).size !== roles.length) {
    throw new Error("Completion sources must be six distinct files");
  }
  const supplement = verified.find((record) => record.role === "supplement_manifest").data;
  if (supplement.plan_sha256 !== ledger.plan_sha256) throw new Error("Supplementary plan SHA differs from the saved completion check");
  const metrics = verified.find((record) => record.role === "metric_supplement").data;
  if (metrics.source_plan_sha256 !== provenance.source_plan_sha256
      || metrics.source_plan_sha256 !== provenance.metric_supplement.source_plan_sha256) {
    throw new Error("Metric supplement belongs to a different main plan");
  }
  return verified.map(({ data, ...record }) => record);
}

function tableCells(line) {
  const text = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  const values = [];
  let cell = "";
  for (let index = 0; index < text.length; index += 1) {
    if (text[index] === "\\" && text[index + 1] === "|") {
      cell += "|";
      index += 1;
    } else if (text[index] === "|") {
      values.push(cell.trim());
      cell = "";
    } else cell += text[index];
  }
  values.push(cell.trim());
  return values;
}

function localSource(target, inputDirectory) {
  const cleaned = target.replace(/^<|>$/g, "");
  if (/^[a-z][a-z0-9+.-]*:/i.test(cleaned) && !/^[A-Za-z]:[\\/]/.test(cleaned)) {
    throw new Error("Images must be existing local files; no network fetch: " + cleaned);
  }
  return path.resolve(inputDirectory, decodeURIComponent(cleaned));
}

function linkTarget(target, inputDirectory, outputDirectory) {
  const cleaned = target.replace(/^<|>$/g, "");
  if (/^(https?:|mailto:|#)/i.test(cleaned)) return cleaned;
  const resolved = localSource(cleaned, inputDirectory);
  const relative = path.relative(outputDirectory, resolved);
  if (path.isAbsolute(relative)) throw new Error("Place the DOCX and its evidence on the same filesystem volume");
  return relative.split(path.sep).map(encodeURIComponent).join("/");
}

function inline(text, context, extra = {}) {
  const children = [];
  const token = /(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\((?:<[^>]+>|[^)]+)\))/g;
  let last = 0;
  const run = (value, style = {}) => new TextRun({ text: value, font: FONT, ...extra, ...style });
  for (const match of text.matchAll(token)) {
    if (match.index > last) children.push(run(text.slice(last, match.index)));
    const value = match[0];
    if (value.startsWith("`")) children.push(run(value.slice(1, -1), { font: "Consolas" }));
    else if (value.startsWith("**")) children.push(run(value.slice(2, -2), { bold: true }));
    else {
      const found = /^\[([^\]]+)\]\((.*)\)$/.exec(value);
      children.push(new ExternalHyperlink({
        link: linkTarget(found[2], context.inputDirectory, context.outputDirectory),
        children: [run(found[1], { color: "1F5A91", underline: {} })],
      }));
    }
    last = match.index + value.length;
  }
  if (last < text.length) children.push(run(text.slice(last)));
  return children.length ? children : [run("")];
}

function imageGeometry(buffer, filename) {
  if (buffer.length >= 24 && buffer.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))) {
    return { type: "png", width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) };
  }
  if (buffer.length > 4 && buffer[0] === 255 && buffer[1] === 216) {
    let offset = 2;
    const frames = new Set([192, 193, 194, 195, 197, 198, 199, 201, 202, 203, 205, 206, 207]);
    while (offset + 9 < buffer.length) {
      if (buffer[offset] !== 255) throw new Error("Invalid JPEG marker: " + filename);
      while (buffer[offset] === 255) offset += 1;
      const marker = buffer[offset++];
      if (marker === 217 || marker === 218) break;
      if (marker === 1 || (marker >= 208 && marker <= 215)) continue;
      const length = buffer.readUInt16BE(offset);
      if (length < 2 || offset + length > buffer.length) break;
      if (frames.has(marker)) return { type: "jpg", height: buffer.readUInt16BE(offset + 3), width: buffer.readUInt16BE(offset + 5) };
      offset += length;
    }
  }
  throw new Error("Only valid PNG/JPEG figures are supported: " + filename);
}

function makeFigure(filename, caption, mode, context) {
  const data = readSmall(filename);
  const geometry = imageGeometry(data, filename);
  if (!geometry.width || !geometry.height) throw new Error("Invalid figure dimensions: " + filename);
  const maxWidth = ((mode === "landscape" ? A4.height : A4.width) - 2 * MARGIN) / 15;
  const maxHeight = mode === "landscape" ? 520 : 760;
  const scale = Math.min(maxWidth / geometry.width, maxHeight / geometry.height, 1);
  context.images.push({ path: filename, bytes: data.length, sha256: sha(data), ...geometry });
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true,
      spacing: { before: 0, after: 120, line: 240, lineRule: LineRuleType.AT_LEAST },
      children: [new ImageRun({
      type: geometry.type, data,
      transformation: { width: Math.round(geometry.width * scale), height: Math.round(geometry.height * scale) },
      altText: { title: caption, description: path.basename(filename), name: path.basename(filename) },
    })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 160 },
      children: [new TextRun({ text: caption, font: FONT, size: 18, color: "475569" })] }),
  ];
}

function cellWidths(rows, totalWidth) {
  const weights = rows[0].map((_, index) => {
    const length = Math.max(...rows.map((row) => Array.from(row[index] || "")
      .reduce((sum, character) => sum + (character.charCodeAt(0) > 255 ? 2 : 1), 0)));
    return Math.sqrt(Math.max(8, Math.min(42, length)));
  });
  const sum = weights.reduce((left, right) => left + right, 0);
  const widths = weights.map((weight) => Math.floor(totalWidth * weight / sum));
  widths[widths.length - 1] += totalWidth - widths.reduce((left, right) => left + right, 0);
  return widths;
}

function makeTable(rows, mode, context) {
  if (!rows.length || rows.some((row) => row.length !== rows[0].length)) throw new Error("Malformed Markdown table");
  const totalWidth = (mode === "landscape" ? A4.height : A4.width) - 2 * MARGIN;
  const widths = cellWidths(rows, totalWidth);
  const size = rows[0].length > 8 ? 15 : 18;
  const border = { style: BorderStyle.SINGLE, size: 4, color: "D7DFEA" };
  return new Table({
    width: { size: totalWidth, type: WidthType.DXA }, columnWidths: widths,
    layout: TableLayoutType.FIXED,
    borders: { top: border, bottom: border, left: border, right: border, insideHorizontal: border, insideVertical: border },
    rows: rows.map((row, rowIndex) => new TableRow({
      tableHeader: rowIndex === 0, cantSplit: true,
      children: row.map((value, index) => new TableCell({
        width: { size: widths[index], type: WidthType.DXA },
        verticalAlign: VerticalAlign.TOP,
        margins: { top: 75, bottom: 75, left: 70, right: 70 },
        shading: { type: ShadingType.CLEAR, fill: rowIndex === 0 ? "E4EDF7" : (rowIndex % 2 === 0 ? "F6F8FB" : "FFFFFF") },
        children: [new Paragraph({ spacing: { before: 0, after: 0, line: 245 },
          children: inline(value, context, { size, bold: rowIndex === 0 }) })],
      })),
    })),
  });
}

function section(mode, children) {
  return {
    properties: {
      type: SectionType.NEXT_PAGE,
      page: { size: { ...A4, orientation: mode === "landscape" ? PageOrientation.LANDSCAPE : PageOrientation.PORTRAIT },
        margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN, header: 440, footer: 440 } },
    },
    headers: { default: new Header({ children: [new Paragraph({
      children: [new TextRun({ text: "RGB-D 无人机目标跟踪与自主跟随 · 研究结果", font: FONT, size: 16, color: "64748B" })],
      border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "CED8E5", space: 5 } },
    })] }) },
    footers: { default: new Footer({ children: [new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: "第 ", size: 16 }), new TextRun({ children: [PageNumber.CURRENT], size: 16 }),
        new TextRun({ text: " 页 / 共 ", size: 16 }), new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 16 }),
        new TextRun({ text: " 页", font: FONT, size: 16 })],
    })] }) },
    children,
  };
}

function renderMarkdown(markdown, context, figures) {
  const sections = [];
  let current = [], mode = "portrait", numberedList = 0;
  const useMode = (next) => {
    if (next !== mode && current.length) { sections.push(section(mode, current)); current = []; }
    mode = next;
  };
  const lines = markdown.replace(/^\uFEFF/, "").replace(/\r\n/g, "\n").split("\n");
  let code = false, previousNumbered = false;
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (/^```/.test(line)) { code = !code; previousNumbered = false; continue; }
    if (code) {
      current.push(new Paragraph({ spacing: { after: 30 }, children: [new TextRun({ text: line, font: "Consolas", size: 17 })] }));
      continue;
    }
    if (!line.trim()) { previousNumbered = false; continue; }
    if (/^\|/.test(line.trim()) && index + 1 < lines.length
        && tableCells(lines[index + 1]).every((cell) => /^:?-{3,}:?$/.test(cell))) {
      const rows = [tableCells(line)];
      index += 1;
      while (index + 1 < lines.length && /^\|/.test(lines[index + 1].trim())) rows.push(tableCells(lines[++index]));
      useMode(rows[0].length > 7 ? "landscape" : "portrait");
      current.push(makeTable(rows, mode, context), new Paragraph({ text: "", spacing: { after: 90 } }));
      previousNumbered = false;
      continue;
    }
    useMode("portrait");
    const heading = /^(#{1,6})\s+(.+)$/.exec(line);
    const image = /^!\[([^\]]*)\]\((.+)\)\s*$/.exec(line);
    const numbered = /^\d+\.\s+(.+)$/.exec(line);
    const bullet = /^[-*]\s+(.+)$/.exec(line);
    if (heading) {
      const firstTitle = heading[1].length === 1 && sections.length === 0 && current.length === 0;
      current.push(new Paragraph({ heading: firstTitle ? HeadingLevel.TITLE :
        [HeadingLevel.HEADING_1, HeadingLevel.HEADING_2, HeadingLevel.HEADING_3][Math.min(2, Math.max(0, heading[1].length - 2))],
        keepNext: true, children: inline(heading[2], context) }));
    } else if (image) {
      current.push(...makeFigure(localSource(image[2], context.inputDirectory), image[1], mode, context));
    } else if (numbered || bullet) {
      if (numbered && !previousNumbered) numberedList += 1;
      current.push(new Paragraph({
        numbering: { reference: numbered ? "numbers" : "bullets", level: 0, ...(numbered ? { instance: numberedList } : {}) },
        children: inline((numbered || bullet)[1], context),
      }));
    } else {
      if (/^<[^>]+>/.test(line)) throw new Error("HTML is outside this report renderer's supported Markdown subset");
      current.push(new Paragraph({ children: inline(line, context) }));
    }
    previousNumbered = Boolean(numbered);
  }
  if (code) throw new Error("Unclosed Markdown code block");
  if (figures.length) {
    useMode("portrait");
    current.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: inline("附图：已有研究结果", context) }),
      new Paragraph({ children: inline("以下图表从现有正式汇总生成；适用范围、失败分母和输入哈希以配套绘图 manifest 为准。", context) }));
    figures.forEach((filename, index) => {
      const geometry = imageGeometry(readSmall(filename), filename);
      useMode(geometry.width / geometry.height > 1.4 ? "landscape" : "portrait");
      current.push(...makeFigure(filename, `图 ${index + 1}  ${path.basename(filename)}`, mode, context));
    });
  }
  if (current.length) sections.push(section(mode, current));
  if (!sections.length) throw new Error("The Markdown report is empty");
  return sections;
}

async function main() {
  const options = argsFor(process.argv.slice(2));
  const markdown = readSmall(options.input);
  const provenanceBytes = readSmall(options.provenance);
  const provenance = JSON.parse(provenanceBytes.toString("utf8").replace(/^\uFEFF/, ""));
  if (provenance.report_sha256 !== sha(markdown)) throw new Error("Final Markdown does not match its saved report provenance");
  const completionSources = validateCompletionProvenance(provenance, path.dirname(options.input));
  const context = { inputDirectory: path.dirname(options.input), outputDirectory: path.dirname(options.output), images: [] };
  const sections = renderMarkdown(markdown.toString("utf8"), context, options.figures);
  const document = new Document({
    creator: "无人机目标跟踪研究项目", title: "无人机目标跟踪与自主跟随：研究结果报告",
    description: "从已保存、带 SHA 来源记录的最终 Markdown 渲染；保留负结果与研究边界。",
    styles: {
      default: { document: { run: { font: FONT, size: 21, color: "172334" },
        paragraph: { spacing: { after: 120, line: 300 }, widowControl: true } } },
      paragraphStyles: [
        { id: "Title", name: "Title", basedOn: "Normal", next: "Normal", run: { font: FONT, size: 38, bold: true, color: "173B61" }, paragraph: { spacing: { before: 100, after: 300 }, keepNext: true } },
        { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", run: { font: FONT, size: 30, bold: true, color: "173B61" }, paragraph: { outlineLevel: 0, spacing: { before: 260, after: 140 }, keepNext: true } },
        { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", run: { font: FONT, size: 25, bold: true, color: "24557D" }, paragraph: { outlineLevel: 1, spacing: { before: 180, after: 110 }, keepNext: true } },
        { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", run: { font: FONT, size: 22, bold: true }, paragraph: { outlineLevel: 2, spacing: { before: 160, after: 90 }, keepNext: true } },
      ],
    },
    numbering: { config: [
      { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 360, hanging: 180 } } } }] },
      { reference: "numbers", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", start: 1, alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 420, hanging: 240 } } } }] },
    ] },
    sections,
  });
  const buffer = await Packer.toBuffer(document);
  fs.mkdirSync(path.dirname(options.output), { recursive: true });
  fs.writeFileSync(options.output, buffer, { flag: "wx" });
  const manifest = {
    schema_version: 1, created_utc: new Date().toISOString(), source: "FINAL_SAVED_MARKDOWN_TO_DOCX",
    renderer: { path: __filename, sha256: sha(fs.readFileSync(__filename)) },
    input: { path: options.input, bytes: markdown.length, sha256: sha(markdown) },
    report_provenance: { path: options.provenance, sha256: sha(provenanceBytes), execution_ledger_complete: true,
      completion_contract_version: 2, supplement_ledger: provenance.supplement_ledger,
      verified_completion_sources: completionSources },
    output: { path: options.output, bytes: buffer.length, sha256: sha(buffer) },
    figures: context.images, section_count: sections.length,
    validation_status: "RENDER_AND_PAGE_INSPECTION_REQUIRED",
    scope: "Formatting only. No metric recalculation, data filtering, synthetic results, bag reads, flight, inference or external network access.",
  };
  fs.writeFileSync(options.sidecar, JSON.stringify(manifest, null, 2) + "\n", { flag: "wx" });
  process.stdout.write(JSON.stringify({ output: options.output, provenance: options.sidecar, validation: manifest.validation_status }) + "\n");
}

module.exports = { validateCompletionProvenance };
if (require.main === module) {
  main().catch((error) => { process.stderr.write(error.stack + "\n"); process.exitCode = 1; });
}
