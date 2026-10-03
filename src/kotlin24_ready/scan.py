"""File discovery, project context and the rule detectors."""
from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass, field

from .lexer import blank_comments, blank_strings, ignore_directives
from .rules import RULES

SKIP_DIRS = {".git", ".gradle", ".idea", "build", "out", "node_modules", ".kotlin", ".svn", "dist", "target"}


@dataclass
class Finding:
    rule: str
    severity: str
    file: str
    line: int
    col: int
    message: str
    snippet: str
    edit: tuple | None = None  # (start, end, replacement) in the original file text

    @property
    def url(self) -> str:
        return RULES[self.rule].url


@dataclass
@dataclass
class Result:
    findings: list = field(default_factory=list)
    files_scanned: int = 0
    kgp: str | None = None
    pr: dict | None = None  # set in PR mode (--base): {base, existing, resolved}


SOURCE_EXT = (".kt", ".java", ".groovy")


CONVENTION_DIRS = {"buildSrc", "build-logic", "buildLogic"}
SOURCE_EXT = (".kt", ".java", ".groovy")


def kind_of(name: str, rel: str | None = None):
    if name.endswith(".gradle.kts"):
        return "kotlin"
    if name.endswith(".gradle"):
        return "groovy"
    if name.endswith(".versions.toml"):
        return "catalog"
    if rel is not None and name.endswith(SOURCE_EXT):
        parts = rel.split("/")[:-1]
        if any(seg in CONVENTION_DIRS for seg in parts):
            return "source"  # convention-plugin sources of buildSrc / build-logic
    return None


def discover(root: str, ignore: list):
    root = os.path.abspath(root)
    if os.path.isfile(root):
        yield root, os.path.basename(root)
        return
    for dp, dns, fns in os.walk(root):
        dns[:] = sorted(d for d in dns if d not in SKIP_DIRS)
        for fn in sorted(fns):
            full = os.path.join(dp, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if kind_of(fn, rel) is None:
                continue
            if any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(fn, g) for g in ignore):
                continue
            yield full, rel


# ---------------------------------------------------------------- small parsers

def parse_properties(text: str) -> dict:
    """key -> (value, offset of the key, offset of line start, offset after the line incl. newline)."""
    out, off = {}, 0
    for ln in text.split("\n"):
        s = ln.strip()
        if s and not s.startswith(("#", "!")):
            m = re.match(r"([^=:\s]+)\s*[=:]\s*(.*)$", s)
            if m:
                out[m.group(1)] = (m.group(2).strip(), off + ln.index(m.group(1)), off, off + len(ln) + 1)
        off += len(ln) + 1
    return out


def parse_catalog(text: str) -> dict:
    """Minimal TOML reader for version catalogs: {section: {key: {attr: value, '_off': offset}}}; one-line entries only."""
    out, sec, off = {}, None, 0
    for ln in text.split("\n"):
        s = ln.strip()
        m = re.match(r"\[([\w.-]+)\]$", s)
        if m:
            sec = m.group(1)
            out.setdefault(sec, {})
        elif sec and s and not s.startswith("#"):
            m = re.match(r"""([\w.-]+)\s*=\s*(.*)$""", s)
            if m:
                key, rest = m.group(1), m.group(2)
                ent = {"_off": off + ln.index(key)}
                q = re.match(r"""["']([^"']*)["']""", rest)
                if q:
                    ent["value"] = q.group(1)
                else:
                    for k, v in re.findall(r"""([\w.]+)\s*=\s*["']([^"']*)["']""", rest):
                        ent[k] = v
                out[sec][key] = ent
        off += len(ln) + 1
    return out


def vtuple(v: str):
    nums = re.findall(r"\d+", v.split("-")[0])
    return tuple(int(n) for n in nums) if nums else None


def version_lt(v: str, bound: str) -> bool:
    a, b = vtuple(v), vtuple(bound)
    return bool(a and b and a < b)

class Project:
    """What the rules need to know about the whole build: the Kotlin Gradle plugin version."""

    def __init__(self):
        self.catalog: dict = {}
        self.kgp: str | None = None

    def catalog_version(self, ent: dict):
        if "version" in ent:
            return ent["version"]
        ref = ent.get("version.ref")
        if ref:
            return self.catalog.get("versions", {}).get(ref, {}).get("value")
        return None

    def detect_kgp(self, texts: dict):
        for k, ent in self.catalog.get("plugins", {}).items():
            if ent.get("id", "").startswith("org.jetbrains.kotlin."):
                v = self.catalog_version(ent)
                if v and vtuple(v):
                    self.kgp = v
                    return
        for k, ent in self.catalog.get("libraries", {}).items():
            if ent.get("module") == "org.jetbrains.kotlin:kotlin-gradle-plugin":
                v = self.catalog_version(ent)
                if v and vtuple(v):
                    self.kgp = v
                    return
        for k in ("kotlin", "kotlin-version", "kotlinVersion"):
            v = self.catalog.get("versions", {}).get(k, {}).get("value")
            if v and vtuple(v):
                self.kgp = v
                return
        for text in texts.values():
            m = re.search(r"""org\.jetbrains\.kotlin:kotlin-gradle-plugin:(\d[\w.\-]*)""", text) or \
                re.search(r"""\bkotlin\s*\(\s*["'][\w\-]+["']\s*\)\s*version\s*["'](\d[\w.\-]*)["']""", text) or \
                re.search(r"""\bid\s*\(?\s*["']org\.jetbrains\.kotlin\.[\w.\-]+["']\s*\)?\s*version\s*["'](\d[\w.\-]*)["']""", text)
            if m:
                self.kgp = m.group(1)
                return


class Ctx:
    def __init__(self, rel: str, text: str, kind: str, project: Project):
        self.rel, self.text, self.kind, self.p = rel, text, kind, project
        self.kotlin = kind == "kotlin" or (kind == "source" and rel.endswith(".kt"))
        code = kind in ("kotlin", "groovy", "source")
        self.code = blank_comments(text, self.kotlin) if code else text
        self.nostr = blank_strings(text, self.kotlin) if code else text
        self.out: list = []

    def line(self, off: int) -> int:
        return self.text.count("\n", 0, off) + 1

    def snippet(self, off: int) -> str:
        s = self.text.rfind("\n", 0, off) + 1
        e = self.text.find("\n", off)
        return self.text[s:e if e >= 0 else len(self.text)].strip()[:160]

    def line_span(self, off: int):
        s = self.text.rfind("\n", 0, off) + 1
        e = self.text.find("\n", off)
        return s, (len(self.text) if e < 0 else e + 1)

    def add(self, rule: str, off: int, message: str | None = None, edit=None, severity: str | None = None):
        r = RULES[rule]
        ln = self.line(off)
        col = off - (self.text.rfind("\n", 0, off) + 1) + 1
        self.out.append(Finding(rule, severity or r.severity, self.rel, ln, col, message or r.summary, self.snippet(off), edit))


def blocks(nostr: str, name_re: str):
    """Yield (name_offset, body_start, body_end) for every `name { ... }` block; braces are matched on string-blanked text."""
    for m in re.finditer(r"(?<![\w.])(?:%s)\s*\{" % name_re, nostr):
        depth, i = 1, m.end()
        while i < len(nostr) and depth:
            depth += {"{": 1, "}": -1}.get(nostr[i], 0)
            i += 1
        yield m.start(), m.end(), i - 1


def block_spans(nostr: str, name_re: str):
    for _, a, b in blocks(nostr, name_re):
        yield a, b




# ---------------------------------------------------------------- detectors

CODE_KINDS = ("kotlin", "groovy", "source")


def _inner(nostr: str, start: int, end: int, name_re: str):
    """Spans (absolute) of `name { ... }` blocks found inside nostr[start:end]."""
    for n, a, b in blocks(nostr[start:end], name_re):
        yield start + n, start + a, start + b


def language_version(c: Ctx):
    if c.kind not in CODE_KINDS:
        return
    for m in re.finditer(r"""\blanguageVersion\b[^\n]*?KotlinVersion\s*\.\s*KOTLIN_1_(\d+)""", c.code):
        c.add("language-version-1-9", m.start(), f"language version 1.{m.group(1)} is not supported by Kotlin 2.4 (`languageVersion` set to `KotlinVersion.KOTLIN_1_{m.group(1)}`)")
    for m in re.finditer(r"""\blanguageVersion\b\s*(?:=|\.set\s*\()\s*["']1\.(\d+)["']""", c.code):
        c.add("language-version-1-9", m.start(), f"language version 1.{m.group(1)} is not supported by Kotlin 2.4 (`languageVersion` = \"1.{m.group(1)}\")")
    for m in re.finditer(r"""-language-version(?:=|["']\s*,\s*["'])1\.(\d+)""", c.code):
        c.add("language-version-1-9", m.start(), f"`-language-version=1.{m.group(1)}` is not supported by Kotlin 2.4")


def dependency_handler(c: Ctx):
    if c.kind != "kotlin":
        return
    seen = set()
    for ka, kb in block_spans(c.nostr, "kotlin"):
        for _, da, db in _inner(c.nostr, ka, kb, r"(?:[\w.]+\.)?dependencies"):
            for m in re.finditer(r"(?<![\w.])(enforcedPlatform|platform)\s*\(", c.nostr[da:db]):
                off = da + m.start()
                if off in seen:
                    continue
                seen.add(off)
                name = m.group(1)
                c.add("dependency-handler-platform", off, f"`{name}()` of KotlinDependencyHandler is removed in Kotlin 2.4",
                      (off, off + len(name), "project.dependencies." + name))


def target_hierarchy(c: Ctx):
    if c.kind not in CODE_KINDS:
        return
    for m in re.finditer(r"(?<![\w])targetHierarchy\b", c.nostr):
        edit = None
        d = re.compile(r"targetHierarchy\s*\.\s*default\s*\(\s*\)").match(c.nostr, m.start())
        if d and c.kind == "kotlin":
            edit = (m.start(), d.end(), "applyDefaultHierarchyTemplate()")
        c.add("target-hierarchy", m.start(), None, edit)


def compilation_accessors(c: Ctx):
    if c.kind not in CODE_KINDS:
        return
    for m in re.finditer(r"\.\s*(compileKotlinTaskProvider|compileKotlinTask)\b", c.nostr):
        c.add("compilation-task-accessors", m.start(1), f"`{m.group(1)}` is removed in Kotlin 2.4")


def hierarchy_builder(c: Ctx):
    if c.kind not in CODE_KINDS:
        return
    for m in re.finditer(r"(?<![\w])(withWasm\s*\(|withoutCompilations\s*\(|filterCompilations\s*[({])", c.nostr):
        name = re.match(r"\w+", m.group(1)).group(0)
        c.add("hierarchy-builder-removed", m.start(1), f"`{name}()` is removed in Kotlin 2.4")


_COMPOSE_OPTS = "enableStrongSkippingMode|enableIntrinsicRemember|enableNonSkippingGroupOptimization|generateFunctionKeyMetaClasses|stabilityConfigurationFile"


def compose_options(c: Ctx):
    if c.kind not in CODE_KINDS:
        return
    for m in re.finditer(r"\bComposeFeatureFlag\s*\.\s*(StrongSkipping|IntrinsicRemember)\b", c.nostr):
        c.add("compose-compiler-options", m.start(), f"`ComposeFeatureFlag.{m.group(1)}` is deprecated with an error in Kotlin 2.4 (the feature is on by default)")
    spans = list(block_spans(c.nostr, "composeCompiler"))
    if c.kind == "source" and re.search(r"ComposeCompilerGradlePluginExtension|composeCompiler", c.nostr):
        spans.append((0, len(c.nostr)))
    seen = set()
    for a, b in spans:
        for m in re.finditer(r"(?<![\w.])(%s)\b" % _COMPOSE_OPTS, c.nostr[a:b]):
            off = a + m.start()
            if off in seen:
                continue
            seen.add(off)
            name = m.group(1)
            edit = None
            if name == "stabilityConfigurationFile":
                s = re.compile(r"stabilityConfigurationFile\s*\.\s*set\s*\(").match(c.nostr, off)
                if s:
                    edit = (off, s.end(), "stabilityConfigurationFiles.add(")
            msg = "`stabilityConfigurationFile` is removed; use `stabilityConfigurationFiles`" if name == "stabilityConfigurationFile" \
                else f"`{name}` is removed; use `featureFlags` (Kotlin 2.4 reports an error)"
            c.add("compose-compiler-options", off, msg, edit)


def abi_validation(c: Ctx):
    if c.kind not in CODE_KINDS:
        return
    for a, b in block_spans(c.nostr, "abiValidation"):
        body = list(c.nostr[a:b])
        for ln, la, lb in _inner(c.nostr, a, b, "legacyDump"):
            c.add("abi-validation-legacy", ln, "`abiValidation { legacyDump { } }` is removed; put its properties directly in `abiValidation { }`")
            body[la - a - 1:lb - a + 1] = " " * (lb - la + 2)
        for kn, ka, kb in _inner(c.nostr, a, b, "klib"):
            for m in re.finditer(r"(?<![\w.])(enabled|keepUnsupportedTargets)\b", c.nostr[ka:kb]):
                msg = "`abiValidation { klib { enabled } }` is removed" if m.group(1) == "enabled" else "`klib.keepUnsupportedTargets` is removed; use `keepLocallyUnsupportedTargets`"
                c.add("abi-validation-legacy", ka + m.start(), msg)
            body[ka - a - 1:kb - a + 1] = " " * (kb - ka + 2)
        for m in re.finditer(r"(?<![\w.])enabled\b", "".join(body)):
            c.add("abi-validation-legacy", a + m.start(), "`abiValidation { enabled }` is removed; calling `abiValidation { }` turns the feature on")


def abi_removed_types(c: Ctx):
    if c.kind not in CODE_KINDS:
        return
    for m in re.finditer(r"\bAbiValidation(?:MultiplatformExtension|VariantSpec)\b", c.nostr):
        c.add("abi-validation-legacy", m.start(), f"`{m.group(0)}` was removed; use `AbiValidationExtension` / `abiValidation {{ }}`")
    for a, b in block_spans(c.nostr, r"(?:extensions\s*\.\s*)?configure\s*<[^>]*AbiValidation\w*>"):
        for m in re.finditer(r"(?<![\w.])enabled\b", c.nostr[a:b]):
            c.add("abi-validation-legacy", a + m.start(), "`enabled` of the ABI validation extension is removed; calling `abiValidation { }` turns the feature on")


_KO_CONTEXT = (r"(?:tasks\s*\.\s*)?withType\s*(?:<[^>]*Kotlin[^>]*>\s*(?:\(\s*\))?|\(\s*[\w.]*Kotlin[\w.]*(?:\.class)?\s*\))\s*(?:\.\s*(?:configureEach|all|matching\s*\([^)]*\)\s*\.\s*configureEach)\s*)?"
               r"|compilations\s*\.\s*(?:all|configureEach)|(?:tasks\s*\.\s*)?(?:named|register)\s*[<(][^{]*Kotlin[^{]*|kotlin")


def kotlin_options(c: Ctx):
    """`kotlinOptions` on a Kotlin compile task, compilation or the `kotlin { }` extension fails on 2.4.20 (checked against the real plugin).
    The Android `android { kotlinOptions { } }` form still builds there (it only breaks on AGP 9 built-in Kotlin: see agp9-ready), so it is not flagged."""
    if c.kind not in CODE_KINDS:
        return
    seen = set()
    for a, b in block_spans(c.nostr, _KO_CONTEXT):
        for m in re.finditer(r"(?<![\w])kotlinOptions\b", c.nostr[a:b]):
            off = a + m.start()
            if off not in seen:
                seen.add(off)
                c.add("kotlin-options", off)


def kotlin_js_plugin(c: Ctx):
    if c.kind in CODE_KINDS or c.kind == "catalog":
        pat = r"""org\.jetbrains\.kotlin\.js(?![\w.\-])|\bkotlin\s*\(\s*["']js["']\s*\)|["']kotlin-js["']|\bplugin\s*:\s*["']kotlin-(?:platform-)?js["']"""
        for m in re.finditer(pat, c.code):
            c.add("kotlin-js-plugin", m.start())


def js_compiler_type(c: Ctx):
    if c.kind not in CODE_KINDS:
        return
    for m in re.finditer(r"(?<![\w.])js\s*\(\s*(?:compiler\s*=\s*)?(?:KotlinJsCompilerType\s*\.\s*)?(IR|LEGACY|BOTH)\s*\)", c.code):
        edit = None
        if m.group(1) == "IR" and c.kind == "kotlin":
            brace = re.compile(r"\s*\{").match(c.code, m.end())
            edit = (m.start(), m.end(), "js" if brace else "js()")
        c.add("js-compiler-type", m.start(), f"`js({m.group(1)})`: the compiler type argument is deprecated in Kotlin 2.4", edit)
    for m in re.finditer(r"\bKotlinJsCompilerType\b", c.nostr):
        c.add("js-compiler-type", m.start())


def android_sourcesets(c: Ctx):
    if c.kind != "kotlin":
        return
    if not re.search(r"com\.android\.(?:application|library|dynamic-feature|test)|\bandroid\s*\{", c.code):
        return
    if re.search(r"multiplatform|\bkmp\b|androidTarget|androidLibrary|kotlin\.mpp|commonMain|commonTest|androidMain|jvmMain|iosMain|applyDefaultHierarchyTemplate|\bsourceSets\s*\{[^{}]*\b(?:common|jvm|ios|js|wasm\w*|native|desktop)\w*(?:Main|Test)\b", c.code, re.I):
        return  # a KMP module's `kotlin { sourceSets }` (also behind a convention-plugin alias) is not the Kotlin Android extension
    for ka, kb in block_spans(c.nostr, "kotlin"):
        for sn, sa, sb in _inner(c.nostr, ka, kb, "sourceSets"):
            c.add("kotlin-android-sourcesets", sn)
            break


DETECTORS = [language_version, dependency_handler, target_hierarchy, compilation_accessors, hierarchy_builder,
             compose_options, abi_validation, abi_removed_types, kotlin_options, kotlin_js_plugin, js_compiler_type, android_sourcesets]

def scan_text(rel: str, text: str, kind: str, project: Project | None = None, disabled=frozenset(), only=frozenset()):
    c = Ctx(rel, text, kind, project or Project())
    for d in DETECTORS:
        d(c)
    ign = ignore_directives(text, c.kotlin) if kind in ("kotlin", "groovy", "source") else {}
    res = []
    for f in c.out:
        if f.rule in disabled or (only and f.rule not in only):
            continue
        s = ign.get(f.line, set())
        if "*" in s or f.rule in s:
            continue
        res.append(f)
    res.sort(key=lambda f: (f.line, f.col, f.rule))
    seen, uniq = set(), []
    for f in res:
        k = (f.rule, f.line, f.col)
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    return uniq




def _read(full: str) -> str:
    with open(full, encoding="utf-8", errors="replace", newline="") as fh:
        return fh.read()


def load_project(root: str, files: list) -> Project:
    p = Project()
    texts = {}
    base = os.path.abspath(root) if os.path.isdir(root) else os.path.dirname(os.path.abspath(root))
    for full, rel in files:
        kind = kind_of(os.path.basename(full), rel)
        if kind in ("kotlin", "groovy"):
            texts[rel] = blank_comments(_read(full), kind == "kotlin")
    cand = os.path.join(base, "gradle", "libs.versions.toml")
    if os.path.isfile(cand):
        p.catalog = parse_catalog(_read(cand))
    for full, rel in files:  # a catalog inside the scan wins when the root has none
        if kind_of(os.path.basename(full), rel) == "catalog" and not p.catalog:
            p.catalog = parse_catalog(_read(full))
    p.detect_kgp(texts)
    return p


def scan(root: str, ignore=(), disabled=(), only=()) -> Result:
    files = list(discover(root, list(ignore)))
    p = load_project(root, files)
    r = Result(kgp=p.kgp)
    for full, rel in files:
        r.files_scanned += 1
        r.findings += scan_text(rel, _read(full), kind_of(os.path.basename(full), rel), p, frozenset(disabled), frozenset(only))
    return r


def apply_fixes(root: str, ignore=(), disabled=(), only=()) -> tuple:
    """Rewrite files in place. Returns (files_changed, edits_applied)."""
    files, edits = 0, 0
    flist = list(discover(root, list(ignore)))
    p = load_project(root, flist)
    for full, rel in flist:
        text = _read(full)
        fs = [f for f in scan_text(rel, text, kind_of(os.path.basename(full), rel), p, frozenset(disabled), frozenset(only)) if f.edit]
        if not fs:
            continue
        last, n = None, 0
        for s, e, rep in sorted({f.edit for f in fs}, reverse=True):
            if last is not None and e > last:
                continue
            text = text[:s] + rep + text[e:]
            last = s
            n += 1
        with open(full, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        files += 1
        edits += n
    return files, edits
