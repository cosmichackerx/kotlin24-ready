# kotlin24-ready

**Find what Kotlin 2.4 removes in the Kotlin Gradle plugin from your Gradle build files, without running Gradle.** A zero-dependency static
scanner (Python 3.9+) for `build.gradle(.kts)`, `libs.versions.toml` and the convention-plugin sources under `buildSrc` / `build-logic`: language
version 1.9 (`languageVersion`, `-language-version=1.9`), the Kotlin Multiplatform DSL that was removed (`targetHierarchy`, bare `platform()` in
`kotlin { dependencies { } }`, `compileKotlinTask`, `withWasm()`), deprecated Compose compiler plugin options, the old ABI validation DSL, and
the Kotlin/JS compiler-type argument. It can **fix the mechanical cases** (`--fix`), emits **SARIF** and GitHub annotations, and ships as a **GitHub Action**.

[![CI](https://github.com/cosmichackerx/kotlin24-ready/actions/workflows/ci.yml/badge.svg)](https://github.com/cosmichackerx/kotlin24-ready/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/cosmichackerx/kotlin24-ready?sort=semver)](https://github.com/cosmichackerx/kotlin24-ready/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Why a static scanner? Most of the Kotlin 2.4 build-script breakages are *script compilation errors*: Gradle stops at the first one, so a
project with five of them takes five fix-and-wait cycles. This lists them all at once, in every module, with the section of the
[Kotlin 2.4 compatibility guide](https://kotlinlang.org/docs/compatibility-guide-24.html) each comes from. It does **not** look at the Kotlin
source-language changes in that guide (those are compiler errors in your `.kt` code; the compiler already reports them).

## Install and run

```
pipx install git+https://github.com/cosmichackerx/kotlin24-ready      # or: pip install git+https://github.com/cosmichackerx/kotlin24-ready
kotlin24-ready .                   # scan the current project
kotlin24-ready . --fix             # apply the mechanical fixes, then report what is left
kotlin24-ready . --base origin/main    # PR mode: only what this branch introduces
kotlin24-ready . -f sarif -o kotlin24.sarif --fail-on never
```

From a checkout without installing: `PYTHONPATH=src python -m kotlin24_ready .`

Exit code: 0 clean, 1 findings at or above `--fail-on` (default `error`), 2 usage error. Output formats: `text`, `markdown`, `json`, `github` (annotations), `sarif`.
Options: `--ignore GLOB`, `--disable RULE`, `--only RULE`, `--list-rules`. Suppress one finding with a comment on the same or the previous line: `// kotlin24-ready: ignore target-hierarchy`.

## Example output

```
build-logic/src/main/kotlin/Conv.kt
      1  error   compilation-task-accessors `compileKotlinTask` is removed in Kotlin 2.4

build.gradle.kts
     10  warning js-compiler-type         `js(IR)`: the compiler type argument is deprecated in Kotlin 2.4
     11  error   target-hierarchy         `kotlin.targetHierarchy` (DeprecatedKotlinTargetHierarchyDsl) is removed
     12  error   language-version-1-9     language version 1.9 is not supported by Kotlin 2.4 (`languageVersion` set to `KotlinVersion.KOTLIN_1_9`)
     15  error   dependency-handler-platform `platform()` of KotlinDependencyHandler is removed in Kotlin 2.4
     21  error   compose-compiler-options `enableStrongSkippingMode` is removed; use `featureFlags` (Kotlin 2.4 reports an error)
     22  error   compose-compiler-options `stabilityConfigurationFile` is removed; use `stabilityConfigurationFiles`

2 file(s) scanned for Kotlin 2.4. Kotlin Gradle plugin detected: 2.3.20. 6 error, 1 warning, 0 note; 4 auto-fixable with --fix.
```

(That is `tests/fixtures/legacy-app`.)

## Rules (9)

| Rule | Severity | What it finds | Fix | Fix flag | Verified by |
|---|---|---|---|---|---|
| [`language-version-1-9`](https://kotlinlang.org/docs/compatibility-guide-24.html#drop-support-for-language-version-1-9-and-the-k1-compiler) | error | Kotlin 2.4 no longer supports language version 1.9 (the K1 compiler is gone); the compiler stops with an error | Remove the setting or use language version 2.0 or newer. |  | real Kotlin Gradle plugin 2.4.20 |
| [`dependency-handler-platform`](https://kotlinlang.org/docs/compatibility-guide-24.html#remove-deprecated-task-compilation-and-dsl-apis-from-the-kotlin-gradle-plugin) | error | `platform()` / `enforcedPlatform()` of `KotlinDependencyHandler` (inside `kotlin { ... dependencies { } }`) are removed | Write `project.dependencies.platform(...)` (or `enforcedPlatform`) instead; the bare call no longer compiles. | `--fix` | real Kotlin Gradle plugin 2.4.20 |
| [`target-hierarchy`](https://kotlinlang.org/docs/compatibility-guide-24.html#remove-deprecated-task-compilation-and-dsl-apis-from-the-kotlin-gradle-plugin) | error | `kotlin.targetHierarchy` (DeprecatedKotlinTargetHierarchyDsl) is removed | Use `applyDefaultHierarchyTemplate()` or `applyHierarchyTemplate { ... }`. | `--fix` | real Kotlin Gradle plugin 2.4.20 |
| [`compilation-task-accessors`](https://kotlinlang.org/docs/compatibility-guide-24.html#remove-deprecated-task-compilation-and-dsl-apis-from-the-kotlin-gradle-plugin) | error | `KotlinCompilation.compileKotlinTask` and `compileKotlinTaskProvider` are removed | Use `compileTaskProvider` (a TaskProvider). |  | real Kotlin Gradle plugin 2.4.20 |
| [`hierarchy-builder-removed`](https://kotlinlang.org/docs/compatibility-guide-24.html#remove-deprecated-task-compilation-and-dsl-apis-from-the-kotlin-gradle-plugin) | error | `KotlinHierarchyBuilder.withWasm()`, `withoutCompilations()` and `filterCompilations()` are removed | Use `withWasmJs()` / `withWasmWasi()` and the other `with...` selectors; select compilations with `withCompilations { ... }`. |  | real Kotlin Gradle plugin 2.4.20 |
| [`compose-compiler-options`](https://kotlinlang.org/docs/compatibility-guide-24.html#deprecate-obsolete-compose-compiler-gradle-plugin-options) | error | Deprecated Compose compiler Gradle plugin options now fail the build (enableStrongSkippingMode, enableIntrinsicRemember, enableNonSkippingGroupOptimization, generateFunctionKeyMetaClasses, stabilityConfigurationFile, ComposeFeatureFlag.StrongSkipping / IntrinsicRemember) | Use `featureFlags` for the feature options and `stabilityConfigurationFiles` (a list) instead of `stabilityConfigurationFile`. | `--fix` | real Kotlin Gradle plugin 2.4.20 |
| [`abi-validation-legacy`](https://kotlinlang.org/docs/compatibility-guide-24.html#remove-redundant-abi-validation-gradle-dsl-elements) | error | Removed ABI validation DSL elements: `abiValidation { legacyDump { } }`, `abiValidation { enabled }`, `klib { enabled }`, `klib.keepUnsupportedTargets`, the classes `AbiValidationMultiplatformExtension` / `AbiValidationVariantSpec` and `enabled` inside `configure<AbiValidation…>` | Put the report settings directly in `abiValidation { }` (calling the block enables the feature); use `keepLocallyUnsupportedTargets` instead of `klib.keepUnsupportedTargets`. |  | real Kotlin Gradle plugin 2.4.20 |
| `kotlin-options` | error | `kotlinOptions { }` / `kotlinOptions.x` on a Kotlin compile task (`tasks.withType<KotlinCompile>`), a compilation or the `kotlin { }` extension fails the build. The `android { kotlinOptions }` form still builds on 2.4.20 and is left to agp9-ready | Use `compilerOptions { }`. |  | real Kotlin Gradle plugin 2.4.20 (also fails on 2.3.20) |
| [`kotlin-js-plugin`](https://kotl.in/t6m3vu) | error | The `org.jetbrains.kotlin.js` plugin (`kotlin("js")`, `kotlin-js`) no longer applies | Use `kotlin("multiplatform")` with a `js { }` target. |  | real Kotlin Gradle plugin 2.4.20 |
| `agp-minimum` | error | The Android Gradle Plugin is older than 8.5.2 in a project that uses the Kotlin plugin: Kotlin Gradle plugin 2.4.20 refuses to apply (nested builds with their own settings file are a warning) | Raise AGP to 8.5.2 or newer. |  | observed in the study (2 projects), **not in the oracle** (AGP 8.1.3 also fails on Gradle 9.8 for other reasons, so an oracle case cannot isolate the Kotlin check) |
| [`js-compiler-type`](https://kotlinlang.org/docs/compatibility-guide-24.html#deprecate-legacy-kotlin-js-compiler-type-selection-apis) | warning | `js(IR)`, `js(LEGACY)`, `js(BOTH)` and `KotlinJsCompilerType` are deprecated in Kotlin 2.4 (the legacy compiler type constants are removed) | Drop the argument: `js { ... }`. | `--fix` | documentation only |
| [`kotlin-android-sourcesets`](https://kotlinlang.org/docs/compatibility-guide-24.html#deprecate-sourcesets-in-the-kotlin-android-extension) | warning | `kotlin { sourceSets { } }` on the Kotlin Android extension is deprecated in Kotlin 2.4 | Configure source sets in the Android Gradle plugin's `android { sourceSets { } }` block. |  | documentation only |

`error`: the Kotlin Gradle plugin 2.4 removes the API or turns its deprecation into an error. `warning`: deprecated in 2.4, or the detection is a heuristic.
Several of the removed APIs were already *error-level deprecated* in 2.3 (see "How it is verified"), so the same findings can break a 2.3.x build.

## Fixes

`--fix` rewrites only what has one unambiguous replacement, and each is re-checked against a real plugin in the oracle (the file builds afterwards):

* `platform(` / `enforcedPlatform(` inside `kotlin { dependencies { } }` → `project.dependencies.platform(` (Kotlin DSL)
* `targetHierarchy.default()` → `applyDefaultHierarchyTemplate()`
* `stabilityConfigurationFile.set(x)` → `stabilityConfigurationFiles.add(x)`
* `js(IR) {` → `js {` (Kotlin DSL; the oracle checks that the result builds, not the warning)

Everything else (language version, `featureFlags`, ABI validation, compilation task accessors) needs a decision from you and is only reported.

## GitHub Action

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0          # only needed for pr-mode
- uses: cosmichackerx/kotlin24-ready@v0.1.1
  with:
    path: .
    fail-on: error          # error | warning | never
    pr-mode: true           # on pull requests report only what the PR introduces
    comment: true           # one sticky comment, updated in place (needs pull-requests: write; skipped for forks)
    sarif-file: kotlin24.sarif
```

Inputs: `path`, `fail-on`, `disable`, `ignore`, `summary` (job summary), `pr-mode`, `base`, `comment`, `github-token`, `sarif-file`. The action runs the scanner from
its own checkout with the runner's Python; it does not install anything and makes no network calls except the sticky comment.

## pre-commit

```yaml
repos:
  - repo: https://github.com/cosmichackerx/kotlin24-ready
    rev: v0.1.4
    hooks:
      - id: kotlin24-ready        # report; fails the commit on errors
      # - id: kotlin24-ready-fix  # or: apply the mechanical fixes (the commit then stops so you can review the diff)
```

The hooks scan the whole project (`pass_filenames: false`) and run only when a `*.gradle(.kts)`, `*.versions.toml` or `buildSrc` / `build-logic` source changed.
CI checks the hooks with `pre-commit try-repo` against the fixtures (clean passes, legacy fails, the fix hook rewrites it).

## PR mode

`--base REF` scans the base revision in a temporary checkout and reports only the findings a change introduces (matched by rule, file and line text, so
inserting lines above a finding does not make it "new"; renames are followed). The summary line says how many were already there and how many were resolved.

## How it is verified

`tests/oracle/run_oracle.py` writes tiny projects, runs the scanner, then runs **real Gradle 9.8.0 with the real Kotlin Gradle plugin 2.4.20** and checks that
"the scanner reports an error" equals "Gradle fails" for every case, including the *negative* cases (the replacement API must build and must not be flagged).
Cases with `--fix` are rewritten and built again. CI runs it on every push. The same cases are run on 2.3.20 as an informational job (it never fails the build). Result of that run:

* already **fail on 2.3.20**: `platform()` in a KMP source set, `targetHierarchy`, `compileKotlinTask` / `compileKotlinTaskProvider`, `withWasm` / `withoutCompilations` / `filterCompilations`, `abiValidation { legacyDump { } }`;
* build on 2.3.20 and **fail on 2.4.20** (the real 2.4 breakage): language version 1.9, every listed Compose compiler option, `abiValidation { enabled }`, `klib { enabled }`, `klib { keepUnsupportedTargets }`.

What this does and does not prove:

* It proves the listed constructs fail (or build) on **one** plugin version, 2.4.20, in the minimal project shape of each case. It does not prove every spelling is found: detection is text matching on comment- and string-blanked source, not a Kotlin parse.
* `js-compiler-type` and `kotlin-android-sourcesets` are **documentation only**: 2.4.20 builds `js(IR)` without a failure, and the Android `sourceSets` case is a heuristic (it can miss or over-report).
* Where the guide and the plugin disagree the plugin wins: the guide lists `KotlinJvmCompile.moduleName` and `KotlinCompilation.defaultSourceSetName` as removed, but
  2.4.20 still accepts both in the oracle project (`moduleName` even fails on 2.3.20 and builds on 2.4.20), so they are **not** rules.
* Not covered: the Kotlin/Native task API removals (`konanHome`, `languageSettings`, ...), `KaptExtension.processors`, `KotlinTest.*` internals, Kotlin source-language changes.

## Docs watch (keeps the rule table honest)

A weekly workflow (`.github/workflows/kotlin-watch.yml`, `scripts/watch/watch_kotlin_docs.py`, standard library only) reads the Kotlin 2.4
compatibility guide and probes for the 2.5 and 2.6 guides. It opens one deduplicated issue when a new guide appears, a section of the 2.4 guide is not in
`scripts/watch/known_sections.txt`, an API name in a Gradle or Build tools API section is neither mentioned by a rule nor listed in `scripts/watch/triaged.txt`, or a rule anchor no
longer exists. The baseline lists were written when the watcher started: they mean "known", not "reviewed" (`triaged.txt` names the 32 known gaps, such as the Kotlin/Native
task properties). Section ids and the `Component:` line are a proxy; the guide is prose.

## How it relates to other tools

* The Kotlin compiler / Gradle report the first script error only, and only for code paths a build runs. This lists all of them statically.
* [`agp9-ready`](https://github.com/cosmichackerx/agp9-ready) does the same for Android Gradle Plugin 9; run both when you move an Android project to AGP 9 and Kotlin 2.4.
* [`gradle10-ready`](https://github.com/cosmichackerx/gradle10-ready) is the same idea for what Gradle 10 removes from build scripts.

## Limitations (read these)

* Text matching, not parsing. A string that builds a property name dynamically, a `build.gradle` script applied from another file, or a version catalog bundle is not followed.
* `dependency-handler-platform` is Kotlin DSL only; in Groovy the call resolves differently and is not checked.
* Property references without a receiver (`compileKotlinTask` inside `compilations.all { }`) are not flagged; qualified uses are.
* Rules apply wherever the file is scanned, whatever Kotlin version the project uses today; the detected plugin version only appears in the summary.
* Only Gradle build scripts and `buildSrc` / `build-logic` sources are read; `.kt` application code is not.

## Roadmap

See the open issues. Planned: Kotlin/Native task API rules, a pre-commit hook, a Kotlin 2.5 pass when the guide appears, version-catalog `kotlin` version check.

## Related tools

Small, independent tools by the same author, for build and CI hygiene and for migrations with a deadline. Each works on its own; none requires another.

**Gradle and Android migrations**

* [gradle-version-catalog-lint](https://github.com/cosmichackerx/gradle-version-catalog-lint): Lints `libs.versions.toml`: unused libraries, plugins and versions, dynamic or SNAPSHOT versions, hard-coded dependencies.
* [gradle10-ready](https://github.com/cosmichackerx/gradle10-ready): Static scan of Gradle build scripts for what Gradle 10 removes (space assignment, multi-string dependencies, Kotlin DSL delegates). `--fix`, PR mode.
* [agp9-ready](https://github.com/cosmichackerx/agp9-ready): Static scan of Gradle files for what Android Gradle Plugin 9 and 10 break (built-in Kotlin, legacy variant API, opt-outs), including `buildSrc`. `--fix`, PR mode.
* [android-target-ready](https://github.com/cosmichackerx/android-target-ready): Static scanner for the targetSdk 36 / 37 migration in app code and manifests (edge-to-edge, predictive back, large screens).
* [android-target-lint](https://github.com/cosmichackerx/android-target-lint): The same targetSdk migration checks as real Android Lint rules (a lint jar with type resolution).

**CI and repository hygiene**

* [node24-ready](https://github.com/cosmichackerx/node24-ready): Finds GitHub Actions still on the removed Node 20 runtime, also inside composite actions and reusable workflows, and the smallest node24 upgrade.
* [dependabot-gaps](https://github.com/cosmichackerx/dependabot-gaps): Finds manifests your `dependabot.yml` does not cover, and dead or overlapping entries.
* [sha256-ready](https://github.com/cosmichackerx/sha256-ready): Finds code that assumes 40-character Git hashes before Git 3.0 makes SHA-256 repositories the default.
* [agent-context-diff](https://github.com/cosmichackerx/agent-context-diff): Diffs `AGENTS.md`, `CLAUDE.md`, Cursor rules and MCP configs between git refs (new servers, widened permissions, hidden Unicode).

## License

MIT
