"""Oracle: build tiny projects with a real Kotlin Gradle plugin and compare the outcome with kotlin24-ready.

For every case the scanner is run on the project and Gradle is run for real. A case agrees when
"the scanner reports an error" == "Gradle fails". Cases marked fix are then rewritten with --fix, which
must leave no error and make Gradle pass. Warning-level (documentation-only) findings are listed, not compared.

    python tests/oracle/run_oracle.py --kgp 2.4.20 [--gradle /path/to/gradle] [case ...]
    python tests/oracle/run_oracle.py --kgp 2.3.20 --expect-pass   # the "before" run: informational, shows what already fails on an older plugin
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from kotlin24_ready.scan import apply_fixes, scan  # noqa: E402

SETTINGS = ('pluginManagement { repositories { gradlePluginPortal(); mavenCentral(); google() } }\n'
            'dependencyResolutionManagement { repositories { mavenCentral() } }\nrootProject.name = "o"\n')
COMPOSE = 'id("org.jetbrains.kotlin.plugin.compose") version "%(v)s"'
ABI = '@OptIn(org.jetbrains.kotlin.gradle.dsl.abi.ExperimentalAbiValidation::class)\n'


def jvm(body, plugins=""):
    return 'plugins { kotlin("jvm") version "%(v)s"\n' + plugins + ' }\n' + body + '\n'


def kmp(body, plugins=""):
    return 'plugins { kotlin("multiplatform") version "%(v)s"\n' + plugins + ' }\n' + body + '\n'


# name: (build.gradle.kts template, gradle task, expect_fail, rule, fix)
CASES = {
    "clean-jvm": (jvm('kotlin { jvmToolchain(17) }'), "compileKotlin", False, None, False),
    "lang-enum": (jvm('import org.jetbrains.kotlin.gradle.dsl.KotlinVersion\nkotlin { compilerOptions { languageVersion.set(KotlinVersion.KOTLIN_1_9) } }'), "compileKotlin", True, "language-version-1-9", False),
    "lang-arg": (jvm('kotlin { compilerOptions { freeCompilerArgs.add("-language-version=1.9") } }'), "compileKotlin", True, "language-version-1-9", False),
    "lang-2-0-ok": (jvm('import org.jetbrains.kotlin.gradle.dsl.KotlinVersion\nkotlin { compilerOptions { languageVersion.set(KotlinVersion.KOTLIN_2_0) } }'), "compileKotlin", False, None, False),
    "platform-in-kotlin-block": (kmp('kotlin { jvm()\n sourceSets { commonMain.dependencies { implementation(platform("org.jetbrains.kotlinx:kotlinx-coroutines-bom:1.10.2")) } } }'), "help", True, "dependency-handler-platform", True),
    "platform-top-level-ok": (jvm('dependencies { implementation(platform("org.jetbrains.kotlinx:kotlinx-coroutines-bom:1.10.2")) }'), "help", False, None, False),
    "target-hierarchy": (kmp('kotlin { jvm()\n targetHierarchy.default() }'), "help", True, "target-hierarchy", True),
    "hierarchy-template-ok": (kmp('kotlin { jvm()\n applyDefaultHierarchyTemplate() }'), "help", False, None, False),
    "compile-task": (kmp('kotlin { val j = jvm()\n j.compilations["main"].compileKotlinTask.name }'), "help", True, "compilation-task-accessors", False),
    "compile-task-provider": (kmp('kotlin { val j = jvm()\n j.compilations["main"].compileKotlinTaskProvider.name }'), "help", True, "compilation-task-accessors", False),
    # the compatibility guide lists defaultSourceSetName as removed, but 2.4.20 still accepts it: not a rule
    "default-source-set-name-ok": (kmp('kotlin { val j = jvm()\n j.compilations["main"].defaultSourceSetName }'), "help", False, None, False),
    "compile-task-new-ok": (kmp('kotlin { val j = jvm()\n j.compilations["main"].compileTaskProvider.name }'), "help", False, None, False),
    "with-wasm": (kmp('kotlin { jvm()\n applyDefaultHierarchyTemplate { common { group("w") { withWasm() } } } }'), "help", True, "hierarchy-builder-removed", False),
    "without-compilations": (kmp('kotlin { jvm()\n applyDefaultHierarchyTemplate { common { group("w") { withJvm(); withoutCompilations() } } } }'), "help", True, "hierarchy-builder-removed", False),
    "filter-compilations": (kmp('kotlin { jvm()\n applyDefaultHierarchyTemplate { common { group("w") { withJvm(); filterCompilations { true } } } } }'), "help", True, "hierarchy-builder-removed", False),
    "compose-strong-skipping": (jvm('composeCompiler { enableStrongSkippingMode = true }', COMPOSE), "help", True, "compose-compiler-options", False),
    "compose-intrinsic-remember": (jvm('composeCompiler { enableIntrinsicRemember = true }', COMPOSE), "help", True, "compose-compiler-options", False),
    "compose-non-skipping-group": (jvm('composeCompiler { enableNonSkippingGroupOptimization = true }', COMPOSE), "help", True, "compose-compiler-options", False),
    "compose-key-meta": (jvm('composeCompiler { generateFunctionKeyMetaClasses = true }', COMPOSE), "help", True, "compose-compiler-options", False),
    "compose-stability-file": (jvm('composeCompiler { stabilityConfigurationFile.set(layout.projectDirectory.file("s.conf")) }', COMPOSE), "help", True, "compose-compiler-options", True),
    "compose-feature-flag": (jvm('import org.jetbrains.kotlin.compose.compiler.gradle.ComposeFeatureFlag\ncomposeCompiler { featureFlags.add(ComposeFeatureFlag.StrongSkipping) }', COMPOSE), "help", True, "compose-compiler-options", False),
    "compose-new-ok": (jvm('composeCompiler { stabilityConfigurationFiles.add(layout.projectDirectory.file("s.conf")) }', COMPOSE), "help", False, None, False),
    "abi-legacy-dump": (ABI + jvm('kotlin { abiValidation { legacyDump { referenceDumpDir.set(layout.projectDirectory.dir("api")) } } }').replace('kotlin("jvm")', 'kotlin("jvm")'), "help", True, "abi-validation-legacy", False),
    "abi-klib-enabled": (kmp(ABI + 'kotlin { jvm()\n abiValidation { klib { enabled = true } } }'), "help", True, "abi-validation-legacy", False),
    "abi-klib-keep": (kmp(ABI + 'kotlin { jvm()\n abiValidation { klib { keepUnsupportedTargets = true } } }'), "help", True, "abi-validation-legacy", False),
    "abi-enabled": (jvm(ABI + 'kotlin { abiValidation { enabled = true } }'), "help", True, "abi-validation-legacy", False),
    "abi-new-ok": (jvm(ABI + 'kotlin { abiValidation { } }'), "help", False, None, False),
    "kotlin-options-task": (jvm('import org.jetbrains.kotlin.gradle.tasks.KotlinCompile\ntasks.withType<KotlinCompile>().configureEach { kotlinOptions { jvmTarget = "17" } }'), "help", True, "kotlin-options", False),
    "kotlin-options-extension": (jvm('kotlin { kotlinOptions { jvmTarget = "17" } }'), "help", True, "kotlin-options", False),
    "kotlin-options-compilation": (kmp('kotlin { jvm { compilations.all { kotlinOptions { jvmTarget = "17" } } } }'), "help", True, "kotlin-options", False),
    "compiler-options-ok": (jvm('import org.jetbrains.kotlin.gradle.dsl.JvmTarget\nkotlin { compilerOptions { jvmTarget.set(JvmTarget.JVM_17) } }'), "help", False, None, False),
    "kotlin-js-plugin": ('plugins { kotlin("js") version "%(v)s" }\nkotlin { js { nodejs() } }\n', "help", True, "kotlin-js-plugin", False),
    "abi-removed-multiplatform-extension": (kmp('import org.jetbrains.kotlin.gradle.dsl.abi.AbiValidationMultiplatformExtension\nprintln(AbiValidationMultiplatformExtension::class)'), "help", True, "abi-validation-legacy", False),
    "abi-extension-enabled": (jvm('import org.jetbrains.kotlin.gradle.dsl.abi.AbiValidationExtension\n' + ABI + 'kotlin { extensions.configure<AbiValidationExtension> { enabled = true } }'), "help", True, "abi-validation-legacy", False),
    "module-name-ok": (jvm('import org.jetbrains.kotlin.gradle.tasks.KotlinJvmCompile\ntasks.withType<KotlinJvmCompile>().configureEach { moduleName.set("x") }'), "help", False, None, False),
    # documentation-only: reported as a warning, Gradle still builds
    "js-ir-warning": (kmp('kotlin { js(IR) { nodejs() } }'), "help", False, "js-compiler-type", True),
}


def gradle(gbin, d, task, daemon):
    args = [gbin, task, "--console=plain", "-q"] + ([] if daemon else ["--no-daemon"])
    p = subprocess.run(args, cwd=d, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=1200)
    m = re.search(r"\* What went wrong:\n(.*?)\n\n", p.stdout, re.S)
    return p.returncode, (" ".join(m.group(1).split())[:200] if m else "")


def project(d, text, v):
    os.makedirs(d + "/src/main/kotlin", exist_ok=True)
    open(d + "/settings.gradle.kts", "w").write(SETTINGS)
    open(d + "/build.gradle.kts", "w").write(text % {"v": v})
    open(d + "/gradle.properties", "w").write("org.gradle.jvmargs=-Xmx1g\n")
    open(d + "/src/main/kotlin/A.kt", "w").write("fun f() = 1\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kgp", default="2.4.20")
    ap.add_argument("--gradle", default="gradle")
    ap.add_argument("--daemon", action="store_true")
    ap.add_argument("--expect-pass", action="store_true", help="informational run on an older plugin: print which cases already fail there, never exit 1")
    ap.add_argument("cases", nargs="*")
    a = ap.parse_args()
    bad, ran = 0, 0
    for name, (tpl, task, expect_fail, rule, fix) in CASES.items():
        if a.cases and name not in a.cases:
            continue
        ran += 1
        d = tempfile.mkdtemp(prefix="k24o-")
        try:
            project(d, tpl, a.kgp)
            res = scan(d)
            errs = {f.rule for f in res.findings if f.severity == "error"}
            warns = {f.rule for f in res.findings if f.severity != "error"}
            rc, why = gradle(a.gradle, d, task, a.daemon)
            failed = rc != 0
            if a.expect_pass:
                ok = True  # informational: which cases already fail on the older plugin
                verdict = "builds on this plugin" if not failed else "already fails on this plugin"
            else:
                ok = bool(errs) == failed and (not rule or rule in errs | warns) and (not expect_fail or failed)
                verdict = "agree" if ok else "DISAGREE"
            line = f"{name:<28} gradle={'fail' if failed else 'ok  '} scan_errors={sorted(errs)} warnings={sorted(warns)} -> {verdict}"
            if ok and fix and not a.expect_pass:
                files, edits = apply_fixes(d)
                after = scan(d)
                rc2, why2 = gradle(a.gradle, d, task, a.daemon)
                fixed_ok = edits > 0 and not [f for f in after.findings if f.rule == rule] and rc2 == 0
                line += f" | fix: edits={edits} remaining={len(after.findings)} gradle={'ok' if rc2 == 0 else 'FAIL ' + why2} -> {'fixed' if fixed_ok else 'FIX-BROKEN'}"
                ok = ok and fixed_ok
            print(line + ("" if ok else f"\n    gradle said: {why}"), flush=True)
            bad += 0 if ok else 1
        finally:
            shutil.rmtree(d, ignore_errors=True)
    print(f"{ran} case(s), {bad} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
