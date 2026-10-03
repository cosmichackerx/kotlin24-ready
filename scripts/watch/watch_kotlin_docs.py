#!/usr/bin/env python3
"""Diff the Kotlin compatibility guides against the kotlin24-ready rule table.

Pages read (kotlinlang.org/docs, plain HTML with heading ids): compatibility-guide-24, and the probes compatibility-guide-25 and -26
(missing today; a 200 means a new Kotlin release guide appeared).

It reports, as ONE deduplicated issue payload:
  * a compatibility guide that did not exist before;
  * a section id of a guide that is not in `known_sections.txt`;
  * API names (code spans) in the sections whose component is Gradle or Build tools API that no rule mentions and that are not in
    `triaged.txt` (the guide lists removed Gradle plugin APIs there);
  * rule anchors (the rule table cites the 2.4 guide) that no longer exist in the page.

Standard library only. Exit codes: 0 nothing new, 3 something to look at, 2 usage/network error.
Section ids and the "Component:" line are a proxy; the guide is prose and is not machine-readable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from typing import Dict, List, Optional, Set, Tuple

BASE = "https://kotlinlang.org/docs/compatibility-guide-%s.html"
CURRENT = "24"
PROBES = ("25", "26")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
KNOWN = os.path.join(HERE, "known_sections.txt")
TRIAGED = os.path.join(HERE, "triaged.txt")
COMPONENT = re.compile(r"Component:\s*(Gradle|Build tools API)", re.I)


class _Page(HTMLParser):
    """Collects h3 sections: id, title, plain text and <code> spans."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sections: Dict[str, dict] = {}
        self._cur: Optional[dict] = None
        self._in_h3 = False
        self._in_code = False
        self._code: List[str] = []
        self._title: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("h2", "h3"):
            self._cur = None
            if tag == "h3" and dict(attrs).get("id"):
                self._cur = {"title": "", "text": [], "code": []}
                self.sections[dict(attrs)["id"]] = self._cur
                self._in_h3, self._title = True, []
        elif tag == "code" and self._cur is not None:
            self._in_code, self._code = True, []

    def handle_data(self, data):
        if self._in_h3:
            self._title.append(data)
        elif self._cur is not None:
            self._cur["text"].append(data)
            if self._in_code:
                self._code.append(data)

    def handle_endtag(self, tag):
        if tag == "h3" and self._in_h3 and self._cur is not None:
            self._cur["title"] = re.sub(r"\s+", " ", "".join(self._title)).strip()
            self._in_h3 = False
        elif tag == "code" and self._in_code:
            self._in_code = False
            if self._cur is not None:
                self._cur["code"].append("".join(self._code).strip())


def parse(html: str) -> Dict[str, dict]:
    p = _Page()
    p.feed(html)
    for s in p.sections.values():
        s["text"] = re.sub(r"\s+", " ", "".join(s["text"]))
    return p.sections


def is_api(token: str) -> bool:
    """Code spans that look like an API member: Class.member, member(), camelCase or PascalCase identifiers (not options like -Xfoo)."""
    t = token.strip()
    if not t or t.startswith(("-", "@", "kotlin ", "plugins")) or " " in t:
        return False
    return bool(re.fullmatch(r"[A-Za-z_][\w.]*(\(\))?", t)) and (any(ch.isupper() for ch in t[1:]) or "." in t)


def api_names(sections: Dict[str, dict]) -> Dict[str, Set[str]]:
    out: Dict[str, Set[str]] = {}
    for sid, s in sections.items():
        if COMPONENT.search(s["text"]):
            out[sid] = {c.rstrip("()") for c in s["code"] if is_api(c)}
    return out


def load_list(path: str) -> Set[str]:
    try:
        with open(path, encoding="utf-8") as fh:
            return {ln.split("\t")[0].strip() for ln in fh if ln.strip() and not ln.startswith("#")}
    except OSError:
        return set()


def rule_text() -> str:
    parts = []
    for f in ("rules.py", "scan.py"):
        with open(os.path.join(ROOT, "src", "kotlin24_ready", f), encoding="utf-8") as fh:
            parts.append(fh.read())
    return "\n".join(parts)


def rule_anchors() -> List[str]:
    with open(os.path.join(ROOT, "src", "kotlin24_ready", "rules.py"), encoding="utf-8") as fh:
        return sorted(set(re.findall(r"GUIDE \+ \"#([\w\-]+)\"", fh.read())))


def covered(name: str, text: str) -> bool:
    last = name.split(".")[-1]
    return re.search(r"(?<![\w])%s(?![\w])" % re.escape(last), text) is not None


def analyse(pages: Dict[str, str], known: Set[str], triaged: Set[str], rtext: str, anchors: List[str]) -> dict:
    res = {"pages": sorted(pages), "new_pages": [], "new_sections": [], "uncovered_apis": [], "stale_anchors": []}
    parsed = {v: parse(h) for v, h in pages.items()}
    for v in sorted(pages):
        if v != CURRENT:
            res["new_pages"].append(v)
        for sid, s in parsed[v].items():
            if f"{v}:{sid}" not in known:
                res["new_sections"].append((v, sid, s["title"]))
    cur = parsed.get(CURRENT, {})
    for sid, names in api_names(cur).items():
        for n in sorted(names):
            if not covered(n, rtext) and n not in triaged:
                res["uncovered_apis"].append((sid, n))
    for a in anchors:
        if a not in cur:
            res["stale_anchors"].append(a)
    return res


def has_news(res: dict) -> bool:
    return any(res[k] for k in ("new_pages", "new_sections", "uncovered_apis", "stale_anchors"))


def render_issue(res: dict) -> Tuple[str, str]:
    key = hashlib.sha256(json.dumps([res[k] for k in ("new_pages", "new_sections", "uncovered_apis", "stale_anchors")], sort_keys=True).encode()).hexdigest()[:10]
    title = f"Kotlin compatibility guide watch: something to review [{key}]"
    L = ["The weekly watch found changes in the Kotlin compatibility guides that the rule table does not cover yet.", ""]
    for v in res["new_pages"]:
        L.append(f"* **New guide**: https://kotlinlang.org/docs/compatibility-guide-{v}.html")
    for v, sid, t in res["new_sections"]:
        L.append(f"* New section in guide {v}: `{sid}` ({t})")
    for sid, n in res["uncovered_apis"]:
        L.append(f"* Gradle/Build tools API `{n}` in `{sid}` is not mentioned by any rule and not in `triaged.txt`")
    for a in res["stale_anchors"]:
        L.append(f"* Rule anchor `#{a}` no longer exists in the 2.4 guide")
    L += ["", "What to do:", "1. decide per row: add a rule (with an oracle case), or",
          "2. record it as known: add `version:id` to `scripts/watch/known_sections.txt` or the API name to `scripts/watch/triaged.txt` with a reason.",
          "Close this issue when the lists cover every row.", "",
          "Section ids and the Component line are a proxy: the guide is prose.", f"\n<!-- kotlin24-ready:watch:{key} -->"]
    return title, "\n".join(L)


def fetch(url: str, timeout: int = 30) -> Tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "kotlin24-ready-watch"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (fixed https URLs)
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""


def fetch_all(getter=fetch) -> Dict[str, str]:
    pages: Dict[str, str] = {}
    st, html = getter(BASE % CURRENT)
    if st != 200 or not html:
        raise OSError(f"{BASE % CURRENT} returned HTTP {st}")
    pages[CURRENT] = html
    for v in PROBES:
        st, html = getter(BASE % v)
        if st == 200 and html:
            pages[v] = html
    return pages


def known_lines(pages: Dict[str, str]) -> List[str]:
    return [f"{v}:{sid}\t{s['title']}" for v in sorted(pages) for sid, s in parse(pages[v]).items()]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pages-dir", help="read <version>.html files (24.html, 25.html) from this directory instead of fetching")
    ap.add_argument("--known", default=KNOWN)
    ap.add_argument("--triaged", default=TRIAGED)
    ap.add_argument("--out", help="write the result JSON (including issue title/body) here")
    ap.add_argument("--print-baseline", action="store_true", help="print known_sections.txt lines for the pages as they are now")
    ap.add_argument("--print-uncovered", action="store_true", help="print the uncovered API names (to seed triaged.txt)")
    a = ap.parse_args(argv)
    try:
        if a.pages_dir:
            pages = {os.path.splitext(f)[0]: open(os.path.join(a.pages_dir, f), encoding="utf-8").read()
                     for f in sorted(os.listdir(a.pages_dir)) if f.endswith(".html")}
        else:
            pages = fetch_all()
    except (OSError, urllib.error.URLError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if a.print_baseline:
        print("\n".join(known_lines(pages)))
        return 0
    if not parse(pages.get(CURRENT, "")):
        print("error: found no sections; the page layout may have changed", file=sys.stderr)
        return 2
    res = analyse(pages, load_list(a.known), load_list(a.triaged), rule_text(), rule_anchors())
    if a.print_uncovered:
        print("\n".join(sorted({n for _, n in res["uncovered_apis"]})))
        return 0
    if has_news(res):
        res["title"], res["body"] = render_issue(res)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=2)
    print(f"guides: {', '.join(res['pages'])}; Gradle/Build tools APIs checked: {sum(len(v) for v in api_names(parse(pages[CURRENT])).values())}")
    for p in res["new_pages"]:
        print("  NEW GUIDE", p)
    for v, sid, t in res["new_sections"]:
        print(f"  NEW SECTION {v}:{sid}: {t}")
    for sid, n in res["uncovered_apis"]:
        print(f"  UNCOVERED API {n} ({sid})")
    for an in res["stale_anchors"]:
        print(f"  STALE ANCHOR #{an}")
    return 3 if has_news(res) else 0


if __name__ == "__main__":
    sys.exit(main())
