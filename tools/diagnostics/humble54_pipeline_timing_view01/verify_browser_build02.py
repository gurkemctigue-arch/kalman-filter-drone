"""Explicit Windows browser verification; run only after the owner reports idle."""
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
import html
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "results/diagnostics/humble54_pipeline_timing_view01"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
EXPECTED_SOURCE = "4a1e5e92244ea3a6fb7bbe6287d6c367e921ca8818f39873876381c25b16e305"
EXPECTED_OUTPUT = "d757d8b334d7067540e67cf34ca7ee0fa8181a5e4c82c2d722e9731d33deb3d1"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Rendered(HTMLParser):
    wanted = {"status", "coverage", "metrics", "detail-caption", "pageinfo", "distribution-caption", "provenance"}
    void = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__()
        self.stack, self.body, self.paths, self.svg = [], {}, [], 0
        self.text = {key: [] for key in self.wanted}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "body":
            self.body = attrs
        if tag == "svg":
            self.svg += 1
        if tag == "path":
            self.paths.append(attrs.get("d", ""))
        if tag not in self.void:
            self.stack.append((tag, attrs.get("id")))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, text):
        for _tag, ident in self.stack:
            if ident in self.wanted:
                self.text[ident].append(text)

    def report(self):
        return {"body": self.body, "svg_count": self.svg,
                "ecdf_step_paths": sum(" H" in path and " V" in path and " L" not in path for path in self.paths),
                "text": {key: "".join(values).strip() for key, values in self.text.items()}}


INTERACTIONS = r'''<script>
(()=>{const records=[],$=id=>document.getElementById(id);const snap=(name,condition)=>records.push({name,pass:!!condition,page:$("pageinfo").textContent});const set=(id,value)=>{const el=$(id);el.value=value;el.dispatchEvent(new Event('change'));};
snap('default_is_complete_car',document.body.dataset.run==='humble54_pipeline_timing_full_car01'&&$('metrics').textContent.includes('1,377 / 1,854'));
$('next').click();snap('car_next_page',$('pageinfo').textContent==='26–50 / 1,854');$('previous').click();snap('car_previous_page',$('pageinfo').textContent==='1–25 / 1,854');
for(const [run,commands,first] of [['full_car01','1,377 / 1,854','681 / 927'],['full_person01','1,377 / 1,857','680 / 928'],['run04','151 / 504','76 / 252'],['run03','0 / 504','0 / 252']]){
set('run','humble54_pipeline_timing_'+run);set('denominator','commands');set('population','commands');snap(run+'_command_denominator',$('coverage').textContent.includes(commands)&&$('metrics').textContent.includes(commands));set('denominator','rgb');set('population','first');snap(run+'_first_rgb_denominator',$('coverage').textContent.includes(first)&&$('metrics').textContent.includes(first));}
for(const run of ['run01','run02']){set('run','humble54_pipeline_timing_'+run);snap(run+'_missing_not_zero',$('metrics').textContent.includes('— / —')&&document.querySelectorAll('svg').length===0&&$('previous').disabled&&$('next').disabled);}
document.body.dataset.interactionProbe=JSON.stringify(records);})();
</script>'''


def launch(url, profile, *, screenshot=None):
    args = [str(CHROME), "--headless=new", "--disable-gpu", "--disable-extensions", "--no-first-run",
            "--no-default-browser-check", "--user-data-dir=" + str(profile), "--dump-dom",
            "--virtual-time-budget=1000", "--window-size=1440,2200"]
    if screenshot:
        args.append("--screenshot=" + str(screenshot))
    result = subprocess.run(args + [url], capture_output=True, timeout=45)
    assert result.returncode == 0, result.stderr.decode("utf8", errors="replace")
    return result.stdout


def main():
    page = OUT / "index.html"
    source = Path(__file__).with_name("build_view.py")
    assert digest(source) == EXPECTED_SOURCE and digest(page) == EXPECTED_OUTPUT
    old_names = ("browser_validation01.json", "browser_interaction_validation01.json", "browser_default01.png", "browser_default01.dom.html")
    preserved = {name: digest(OUT / name) for name in old_names}
    cases = [("default_car", "", "full_car01", "commands", "commands", "1,377 / 1,854"),
             ("person_url", "?run=humble54_pipeline_timing_full_person01", "full_person01", "commands", "commands", "1,377 / 1,857"),
             ("car_first", "?run=humble54_pipeline_timing_full_car01&denominator=rgb&population=first", "full_car01", "rgb", "first", "681 / 927"),
             ("person_first", "?run=humble54_pipeline_timing_full_person01&denominator=rgb&population=first", "full_person01", "rgb", "first", "680 / 928"),
             ("failed", "?run=humble54_pipeline_timing_run01", "run01", "commands", "commands", "— / —")]
    reports = []
    with tempfile.TemporaryDirectory(prefix="timing_view_browser02_") as temporary:
        temporary = Path(temporary)
        for name, query, run, denominator, population, expected in cases:
            raw = launch(page.as_uri() + query, temporary / name,
                         screenshot=OUT / "browser_default02.png" if name == "default_car" else None)
            dom = raw.decode("utf8", errors="replace")
            if name == "default_car":
                (OUT / "browser_default02.dom.html").write_text(dom, encoding="utf8")
            parsed = Rendered()
            parsed.feed(dom)
            report = parsed.report()
            report.update(name=name, dom_sha256=hashlib.sha256(raw).hexdigest(), dom_bytes=len(raw))
            body = report["body"]
            assert body.get("data-rendered") == "true" and not body.get("data-error")
            assert body.get("data-run") == "humble54_pipeline_timing_" + run
            assert body.get("data-denominator") == denominator and body.get("data-population") == population
            assert expected in report["text"]["metrics"] and expected in report["text"]["coverage"]
            if name == "failed":
                assert report["svg_count"] == 0 and "0 / 0" not in report["text"]["metrics"]
                assert "NOT_OBSERVED_INCOMPLETE_EXECUTION" in report["text"]["status"]
            else:
                assert report["svg_count"] == 2 and report["ecdf_step_paths"] == 1
            report["pass"] = True
            reports.append(report)
        staged = temporary / "interaction.html"
        staged.write_text(page.read_text(encoding="utf8").replace("</body>", INTERACTIONS + "</body>"), encoding="utf8")
        dom = launch(staged.as_uri(), temporary / "interactions").decode("utf8", errors="replace")
        matched = re.search(r'data-interaction-probe="([^"]*)"', dom)
        assert matched
        interactions = json.loads(html.unescape(matched.group(1)))
        assert len(interactions) == 13 and all(row["pass"] for row in interactions), interactions
    assert {name: digest(OUT / name) for name in old_names} == preserved
    assert digest(source) == EXPECTED_SOURCE and digest(page) == EXPECTED_OUTPUT
    shared = {"verified_utc": datetime.now(timezone.utc).isoformat(), "source_sha256": EXPECTED_SOURCE,
              "output_sha256": EXPECTED_OUTPUT, "scope": "WINDOWS_OFFLINE_BROWSER_ONLY_AFTER_ROOT_IDLE_NOTICE",
              "previous_browser_evidence_preserved": preserved, "formal_progress": "0/280_UNCHANGED", "physical_e2e": "NOT_OBSERVED"}
    browser = {**shared, "cases": reports, "screenshot_sha256": digest(OUT / "browser_default02.png")}
    interaction = {**shared, "scope": "EXACT_HTML_TEMP_COPY_WITH_EVENT_PROBE_AFTER_ROOT_IDLE_NOTICE", "checks": interactions}
    (OUT / "browser_validation02.json").write_text(json.dumps(browser, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    (OUT / "browser_interaction_validation02.json").write_text(json.dumps(interaction, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"browser_cases": len(reports), "interaction_checks": len(interactions), "source_sha256": EXPECTED_SOURCE,
                      "output_sha256": EXPECTED_OUTPUT, "browser_receipt_sha256": digest(OUT / "browser_validation02.json"),
                      "interaction_receipt_sha256": digest(OUT / "browser_interaction_validation02.json")}, ensure_ascii=True))


if __name__ == "__main__":
    main()
