# Changelog

## 0.1.3 - 2026-10-03

Three gaps found by the [recall study](https://github.com/cosmichackerx/kotlin24-ready-study) (public KMP/Compose repositories built with Kotlin Gradle plugin 2.4.20):

* New rule `kotlin-options`: `kotlinOptions { }` on a compile task, compilation or the `kotlin { }` extension (oracle: fails on 2.4.20). `android { kotlinOptions }` is deliberately not flagged: it builds on 2.4.20.
* New rule `kotlin-js-plugin`: `org.jetbrains.kotlin.js` / `kotlin("js")` / `kotlin-js` (oracle: fails on 2.4.20).
* `abi-validation-legacy` also covers the removed classes `AbiValidationMultiplatformExtension` / `AbiValidationVariantSpec` and `enabled` in `configure<AbiValidationExtension> { }`.
* Oracle: 36 cases against 2.4.20, 0 disagreements.

## 0.1.2 - 2026-10-03

* Fix: `kotlin-android-sourcesets` no longer fires on Kotlin Multiplatform modules whose plugin comes from a convention-plugin alias (79 false positives in a scan of 84 public KMP/Compose repositories; none left). The heuristic now treats `commonMain`, `androidMain`, `applyDefaultHierarchyTemplate`, `kmp` and similar as KMP signals.
* CI: oracle matrix entry for Kotlin Gradle plugin 2.5.0-Beta1 (informational: 29 cases, 0 disagreements at the time of writing).

## 0.1.1 - 2026-10-03

* Weekly docs watcher (`scripts/watch/watch_kotlin_docs.py`, `.github/workflows/kotlin-watch.yml`): a new Kotlin compatibility guide (2.5, 2.6 probes), new sections in the 2.4 guide, Gradle / Build tools API names that no rule mentions, stale rule anchors. One deduplicated issue.
* pre-commit hooks `kotlin24-ready` and `kotlin24-ready-fix`, checked in CI with `pre-commit try-repo`.
* `action.yml` description shortened to the Marketplace limit of 125 characters, with a CI check (name, description length, branding).

## 0.1.0 - 2026-10-03

First release.

* 9 rules for the Kotlin Gradle plugin changes in Kotlin 2.4: language version 1.9, `KotlinDependencyHandler.platform()`, `targetHierarchy`, compilation task accessors, removed hierarchy builder selectors, Compose compiler plugin options, ABI validation DSL, `js(IR)`, Kotlin Android `sourceSets`.
* `--fix` for four mechanical cases; text, markdown, JSON, GitHub annotation and SARIF output; PR mode (`--base`) and a sticky pull request comment; GitHub Action.
* Oracle against real Gradle 9.8.0 and the Kotlin Gradle plugin 2.4.20.
