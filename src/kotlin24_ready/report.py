"""Renderers: text, markdown, json, github annotations, sarif."""
from __future__ import annotations

import json

from . import __version__
from .rules import RULES
from .scan import Result

ORDER = {"error": 0, "warning": 1, "note": 2}
URL = "https://github.com/cosmichackerx/kotlin24-ready"


def counts(r: Result) -> dict:
    c = {"error": 0, "warning": 0, "note": 0}
    for f in r.findings:
        c[f.severity] += 1
    return c


def summary_line(r: Result) -> str:
    c = counts(r)
    fx = sum(1 for f in r.findings if f.edit)
    kgp = f" Kotlin Gradle plugin detected: {r.kgp}." if r.kgp else " Kotlin Gradle plugin version not found."
    if len(r.builds) > 1:
        kgp += f" {len(r.builds)} Gradle builds (settings files) found; the version is the root build's."
    if r.pr:
        p = r.pr
        return (f"{r.files_scanned} file(s) scanned for Kotlin 2.4.{kgp} {c['error']} error, {c['warning']} warning, {c['note']} note introduced since {p['base']}; "
                f"{fx} auto-fixable with --fix. Not shown: {p['existing']} that were already there; {p['resolved']} resolved.")
    return (f"{r.files_scanned} file(s) scanned for Kotlin 2.4.{kgp} "
            f"{c['error']} error, {c['warning']} warning, {c['note']} note; {fx} auto-fixable with --fix.")


def render_text(r: Result) -> str:
    out: list = []
    if not r.findings:
        out.append("No new Kotlin 2.4 findings." if r.pr else "No Kotlin 2.4 findings.")
    last = None
    for f in sorted(r.findings, key=lambda f: (f.file, f.line)):
        if f.file != last:
            out.append(f"\n{f.file}")
            last = f.file
        out.append(f"  {f.line:>5}  {f.severity:<7} {f.rule:<24} {f.message}")
        if f.snippet:
            out.append(f"         > {f.snippet}")
    out += ["", summary_line(r)]
    return "\n".join(out).lstrip("\n") + "\n"


def render_markdown(r: Result) -> str:
    out = ["## kotlin24-ready", "", summary_line(r), ""]
    if r.findings:
        out += ["| Severity | Rule | Where | Message |", "|---|---|---|---|"]
        for f in sorted(r.findings, key=lambda f: (ORDER[f.severity], f.file, f.line)):
            out.append(f"| {f.severity} | [`{f.rule}`]({f.url}) | `{f.file}:{f.line}` | {f.message.replace('|', chr(92) + '|')} |")
    else:
        out.append("No new findings." if r.pr else "No findings.")
    return "\n".join(out) + "\n"


def render_json(r: Result) -> str:
    return json.dumps({
        "tool": "kotlin24-ready", "version": __version__, "kotlinTarget": "2.4", "kgpDetected": r.kgp,
        **({"builds": [{"root": b or ".", "kgp": v} for b, v in r.builds.items()]} if len(r.builds) > 1 else {}),
        "filesScanned": r.files_scanned, "summary": counts(r),
        **({"pullRequest": r.pr} if r.pr else {}),
        "findings": [{"rule": f.rule, "severity": f.severity, "file": f.file, "line": f.line, "column": f.col,
                      "message": f.message, "snippet": f.snippet, "fixable": bool(f.edit), "docs": f.url} for f in r.findings],
    }, indent=2) + "\n"


def render_github(r: Result) -> str:
    def esc(s: str) -> str:
        return s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    lvl = {"error": "error", "warning": "warning", "note": "notice"}
    return "".join(f"::{lvl[f.severity]} file={f.file},line={f.line},col={f.col},title={f.rule}::{esc(f.message)}\n" for f in r.findings)


def render_sarif(r: Result) -> str:
    level = {"error": "error", "warning": "warning", "note": "note"}
    ids = list(RULES)
    rules = [{"id": i, "name": i, "shortDescription": {"text": RULES[i].summary}, "helpUri": RULES[i].url,
              "help": {"text": RULES[i].fix}, "defaultConfiguration": {"level": level[RULES[i].severity]}} for i in ids]
    results = [{"ruleId": f.rule, "ruleIndex": ids.index(f.rule), "level": level[f.severity], "message": {"text": f.message},
                "locations": [{"physicalLocation": {"artifactLocation": {"uri": f.file, "uriBaseId": "%SRCROOT%"},
                                                    "region": {"startLine": max(1, f.line), "startColumn": max(1, f.col)}}}]} for f in r.findings]
    return json.dumps({"$schema": "https://json.schemastore.org/sarif-2.1.0.json", "version": "2.1.0",
                       "runs": [{"tool": {"driver": {"name": "kotlin24-ready", "version": __version__, "informationUri": URL, "rules": rules}},
                                 "results": results}]}, indent=2) + "\n"


RENDERERS = {"text": render_text, "markdown": render_markdown, "json": render_json, "github": render_github, "sarif": render_sarif}


def meets_threshold(r: Result, fail_on: str) -> bool:
    if fail_on == "never":
        return False
    return any(f.severity == "error" or (fail_on == "warning" and f.severity == "warning") for f in r.findings)
