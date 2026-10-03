"""Rule catalogue. Every rule cites the Kotlin 2.4 compatibility guide."""
from __future__ import annotations

from dataclasses import dataclass

GUIDE = "https://kotlinlang.org/docs/compatibility-guide-24.html"


@dataclass(frozen=True)
class Rule:
    id: str
    severity: str  # error = removed or turned into an error in the Kotlin Gradle plugin 2.4, warning = deprecated or the detection is heuristic
    summary: str
    fix: str
    url: str
    fixable: bool = False
    oracle: bool = True  # True: reproduced against a real Kotlin Gradle plugin in tests/oracle. False: taken from the documentation only


RULES: dict = {r.id: r for r in [
    Rule("language-version-1-9", "error",
         "Kotlin 2.4 no longer supports language version 1.9 (the K1 compiler is gone); the compiler stops with an error",
         "Remove the setting or use language version 2.0 or newer.",
         GUIDE + "#drop-support-for-language-version-1-9-and-the-k1-compiler"),
    Rule("dependency-handler-platform", "error",
         "`platform()` / `enforcedPlatform()` of `KotlinDependencyHandler` (inside `kotlin { ... dependencies { } }`) are removed",
         "Write `project.dependencies.platform(...)` (or `enforcedPlatform`) instead; the bare call no longer compiles.",
         GUIDE + "#remove-deprecated-task-compilation-and-dsl-apis-from-the-kotlin-gradle-plugin", True),
    Rule("target-hierarchy", "error",
         "`kotlin.targetHierarchy` (DeprecatedKotlinTargetHierarchyDsl) is removed",
         "Use `applyDefaultHierarchyTemplate()` or `applyHierarchyTemplate { ... }`.",
         GUIDE + "#remove-deprecated-task-compilation-and-dsl-apis-from-the-kotlin-gradle-plugin", True),
    Rule("compilation-task-accessors", "error",
         "`KotlinCompilation.compileKotlinTask` and `compileKotlinTaskProvider` are removed",
         "Use `compileTaskProvider` (a TaskProvider).",
         GUIDE + "#remove-deprecated-task-compilation-and-dsl-apis-from-the-kotlin-gradle-plugin"),
    Rule("hierarchy-builder-removed", "error",
         "`KotlinHierarchyBuilder.withWasm()`, `withoutCompilations()` and `filterCompilations()` are removed",
         "Use `withWasmJs()` / `withWasmWasi()` and the other `with...` selectors; select compilations with `withCompilations { ... }`.",
         GUIDE + "#remove-deprecated-task-compilation-and-dsl-apis-from-the-kotlin-gradle-plugin"),
    Rule("compose-compiler-options", "error",
         "Deprecated Compose compiler Gradle plugin options now fail the build (enableStrongSkippingMode, enableIntrinsicRemember, enableNonSkippingGroupOptimization, generateFunctionKeyMetaClasses, stabilityConfigurationFile, ComposeFeatureFlag.StrongSkipping / IntrinsicRemember)",
         "Use `featureFlags` for the feature options and `stabilityConfigurationFiles` (a list) instead of `stabilityConfigurationFile`.",
         GUIDE + "#deprecate-obsolete-compose-compiler-gradle-plugin-options", True),
    Rule("abi-validation-legacy", "error",
         "Removed ABI validation DSL elements: `abiValidation { legacyDump { } }`, `abiValidation { enabled }`, `klib { enabled }` and `klib.keepUnsupportedTargets`",
         "Put the report settings directly in `abiValidation { }` (calling the block enables the feature); use `keepLocallyUnsupportedTargets` instead of `klib.keepUnsupportedTargets`.",
         GUIDE + "#remove-redundant-abi-validation-gradle-dsl-elements"),
    Rule("js-compiler-type", "warning",
         "`js(IR)`, `js(LEGACY)`, `js(BOTH)` and `KotlinJsCompilerType` are deprecated in Kotlin 2.4 (the legacy compiler type constants are removed)",
         "Drop the argument: `js { ... }`.",
         GUIDE + "#deprecate-legacy-kotlin-js-compiler-type-selection-apis", True, oracle=False),
    Rule("kotlin-android-sourcesets", "warning",
         "`kotlin { sourceSets { } }` on the Kotlin Android extension is deprecated in Kotlin 2.4",
         "Configure source sets in the Android Gradle plugin's `android { sourceSets { } }` block.",
         GUIDE + "#deprecate-sourcesets-in-the-kotlin-android-extension", oracle=False),
]}
