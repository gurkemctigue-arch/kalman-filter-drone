"use strict";

// Small source fixtures only. No document packing, rendering or research work.
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { validateCompletionProvenance } = require("../scripts/render_research_docx.cjs");
const hash = (value) => crypto.createHash("sha256").update(value).digest("hex");
const clone = (value) => JSON.parse(JSON.stringify(value));
const directory = fs.mkdtempSync(path.join(os.tmpdir(), "uav-report-word-gate-"));

try {
  const roles = ["main_summary", "main_plan", "offline_manifest", "engineering_manifest", "supplement_manifest", "metric_supplement"];
  const planSha = "a".repeat(64);
  const records = roles.map((role) => {
    const relative = role + ".json";
    const bytes = Buffer.from(JSON.stringify(role === "supplement_manifest" ? { plan_sha256: planSha }
      : role === "metric_supplement" ? { source_plan_sha256: planSha } : { role }));
    fs.writeFileSync(path.join(directory, relative), bytes, { flag: "wx" });
    return { role, exists: true, report_relative_path: relative, bytes: bytes.length, sha256: hash(bytes) };
  });
  const complete = {
    execution_ledger_complete: true, completion_contract_version: 2, source_plan_sha256: planSha,
    metric_supplement: { complete: true, main_flights: 166, engineering_flights: 16, source_plan_sha256: planSha },
    supplement_ledger: { complete: true, terminal_slots: 16, plan_sha256: planSha,
      status_counts: { RECORDED: 14, INCOMPLETE_EVIDENCE: 1, INTERRUPTED: 1 } },
    completion_sources: records,
  };
  assert.equal(validateCompletionProvenance(complete, directory).length, 6);
  assert.throws(() => validateCompletionProvenance({ execution_ledger_complete: true }, directory), /legacy completion flags/);
  const pending = clone(complete);
  pending.supplement_ledger.status_counts = { RECORDED: 15, PENDING: 1 };
  assert.throws(() => validateCompletionProvenance(pending, directory), /nonterminal/);
  const missing = clone(complete);
  missing.completion_sources.pop();
  assert.throws(() => validateCompletionProvenance(missing, directory), /six-source/);
  const duplicate = clone(complete);
  duplicate.completion_sources[1] = duplicate.completion_sources[0];
  assert.throws(() => validateCompletionProvenance(duplicate, directory), /six-source/);
  const absolute = clone(complete);
  absolute.completion_sources[0].report_relative_path = path.resolve(directory, "main_summary.json");
  assert.throws(() => validateCompletionProvenance(absolute, directory), /portable relative path/);
  const wrongPlan = clone(complete);
  wrongPlan.supplement_ledger.plan_sha256 = "b".repeat(64);
  assert.throws(() => validateCompletionProvenance(wrongPlan, directory), /plan SHA differs/);
  const wrongMetricPlan = clone(complete);
  wrongMetricPlan.metric_supplement.source_plan_sha256 = "b".repeat(64);
  assert.throws(() => validateCompletionProvenance(wrongMetricPlan, directory), /different main plan/);
  for (const record of records) {
    const filename = path.join(directory, record.report_relative_path);
    const original = fs.readFileSync(filename);
    fs.appendFileSync(filename, "\n");
    assert.throws(() => validateCompletionProvenance(complete, directory), /changed after the Markdown/);
    fs.writeFileSync(filename, original);
  }
  process.stdout.write("Word completion gate: 14 fixture checks passed; no DOCX rendered.\n");
} finally {
  // Exact fresh fixture directory; never remove a repository or results root.
  fs.rmSync(directory, { recursive: true });
}
