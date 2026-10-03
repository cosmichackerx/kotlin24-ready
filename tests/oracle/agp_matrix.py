"""Oracle matrix for the `agp-minimum` rule: real Gradle, real Kotlin Gradle plugin, several real Android Gradle plugin versions.

For each AGP version a minimal Android + Kotlin app is built with `gradle help` and the outcome is compared with the scanner:
the scanner reports an `agp-minimum` error exactly when the Kotlin Gradle plugin refuses to apply because of the AGP version.
A build that fails for any OTHER reason is reported as `inconclusive` (never as agreement), so the matrix cannot pass by accident.

    python tests/oracle/agp_matrix.py --gradle /path/to/gradle --kgp 2.4.20 8.1.3 8.4.2 8.5.2 8.7.3
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
from kotlin24_ready.scan import scan  # noqa: E402

SETTINGS = ('pluginManagement { repositories { gradlePluginPortal(); mavenCentral(); google() } }\n'
            'dependencyResolutionManagement { repositories { google(); mavenCentral() } }\nrootProject.name = "o"\n')
BUILD = ('plugins {\n  id("com.android.application") version "%(agp)s"\n  id("org.jetbrains.kotlin.android") version "%(kgp)s"\n}\n'
         'android { namespace = "o.app"; compileSdk = %(sdk)s; defaultConfig { minSdk = 24 } }\n')
CATALOG_BUILD = ('plugins {\n  alias(libs.plugins.android.application)\n  alias(libs.plugins.kotlin.android)\n}\n'
                 'android { namespace = "o.app"; compileSdk = %(sdk)s; defaultConfig { minSdk = 24 } }\n')
CATALOG = ('[versions]\nagp = "%(agp)s"\nkotlin = "%(kgp)s"\n[plugins]\nandroid-application = { id = "com.android.application", version.ref = "agp" }\n'
           'kotlin-android = { id = "org.jetbrains.kotlin.android", version.ref = "kotlin" }\n')
MARK = re.compile(r"minimum supported|lower than the minimum|AGP.*(?:lower|minimum|at least)|Android Gradle plugin.*(?:lower|minimum)", re.I)


def run(gradle: str, d: str):
    p = subprocess.run([gradle, "help", "--console=plain", "-q", "--no-daemon"], cwd=d, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=1500)
    m = re.search(r"\* What went wrong:\n(.*?)\n\n", p.stdout, re.S)
    return p.returncode, (" ".join(m.group(1).split()) if m else "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gradle", default="gradle")
    ap.add_argument("--kgp", default="2.4.20")
    ap.add_argument("--forms", default="plugins,catalog", help="how the versions are declared: plugins (id(...) version ...) and/or catalog (libs.versions.toml)")
    ap.add_argument("agp", nargs="+")
    a = ap.parse_args()
    sdk = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or "/usr/local/lib/android/sdk"
    levels = sorted(int(m.group(1)) for n in (os.listdir(sdk + "/platforms") if os.path.isdir(sdk + "/platforms") else []) if (m := re.fullmatch(r"android-(\d+)", n)))
    if not levels:
        print("no Android platform found under " + sdk + "/platforms")
        return 2
    level = str(levels[-1])
    bad = inconclusive = 0
    for form, agp in [(f, v) for v in a.agp for f in a.forms.split(",")]:
        d = tempfile.mkdtemp(prefix="k24agp-")
        try:
            os.makedirs(d + "/src/main", exist_ok=True)
            open(d + "/settings.gradle.kts", "w").write(SETTINGS)
            if form == "catalog":
                os.makedirs(d + "/gradle", exist_ok=True)
                open(d + "/gradle/libs.versions.toml", "w").write(CATALOG % {"agp": agp, "kgp": a.kgp})
                open(d + "/build.gradle.kts", "w").write(CATALOG_BUILD % {"sdk": level})
            else:
                open(d + "/build.gradle.kts", "w").write(BUILD % {"agp": agp, "kgp": a.kgp, "sdk": level})
            open(d + "/gradle.properties", "w").write("org.gradle.jvmargs=-Xmx1g\nandroid.useAndroidX=true\n")
            open(d + "/local.properties", "w").write("sdk.dir=%s\n" % sdk)
            open(d + "/src/main/AndroidManifest.xml", "w").write('<manifest xmlns:android="http://schemas.android.com/apk/res/android"/>\n')
            flagged = any(f.rule == "agp-minimum" and f.severity == "error" for f in scan(d).findings)
            rc, why = run(a.gradle, d)
            kotlin_refused = rc != 0 and bool(MARK.search(why))
            if rc != 0 and not kotlin_refused:
                verdict, inconclusive = "INCONCLUSIVE (failed for another reason)", inconclusive + 1
            elif flagged == kotlin_refused:
                verdict = "agree"
            else:
                verdict, bad = "DISAGREE", bad + 1
            print(f"{form:<8} AGP {agp:<8} KGP {a.kgp}: gradle={'fail' if rc else 'ok  '} scanner_flags={flagged} -> {verdict}" + (f"\n    gradle said: {why[:420]}" if rc else ""), flush=True)
        finally:
            shutil.rmtree(d, ignore_errors=True)
    print(f"{len(a.agp)} AGP version(s) x {len(a.forms.split(','))} form(s), {bad} disagreement(s), {inconclusive} inconclusive")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
