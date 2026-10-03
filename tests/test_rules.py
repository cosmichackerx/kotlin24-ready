import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from kotlin24_ready.scan import Project, scan_text  # noqa: E402


def run(text, kind="kotlin", rel="build.gradle.kts", **kw):
    return scan_text(rel, text, kind, Project(), **kw)


def ids(fs):
    return sorted(f.rule for f in fs)


def test_language_version_variants():
    assert ids(run('kotlin { compilerOptions { languageVersion.set(KotlinVersion.KOTLIN_1_9) } }')) == ["language-version-1-9"]
    assert ids(run('kotlin { compilerOptions { languageVersion = KotlinVersion.KOTLIN_1_8 } }')) == ["language-version-1-9"]
    assert ids(run('compilerOptions { languageVersion = "1.9" }')) == ["language-version-1-9"]
    assert ids(run("freeCompilerArgs += '-language-version=1.9'", "groovy", "build.gradle")) == ["language-version-1-9"]
    assert ids(run('freeCompilerArgs.addAll("-language-version", "1.9")')) == ["language-version-1-9"]


def test_language_version_negatives():
    assert run('kotlin { compilerOptions { languageVersion.set(KotlinVersion.KOTLIN_2_0) } }') == []
    assert run('kotlin { compilerOptions { apiVersion.set(KotlinVersion.KOTLIN_1_9) } }') == []
    assert run('// languageVersion = "1.9"\nval s = "x"') == []
    assert run('freeCompilerArgs.add("-language-version=2.1")') == []


def test_platform_only_inside_kotlin_dependencies():
    bad = 'kotlin { sourceSets { commonMain.dependencies { implementation(platform("g:a:1")) } } }'
    fs = run(bad)
    assert ids(fs) == ["dependency-handler-platform"] and fs[0].edit
    assert run('dependencies { implementation(platform("g:a:1")) }') == []
    assert run('kotlin { sourceSets { commonMain.dependencies { implementation(project.dependencies.platform("g:a:1")) } } }') == []
    assert ids(run('kotlin { sourceSets { val m by getting { dependencies { api(enforcedPlatform("g:a:1")) } } } }')) == ["dependency-handler-platform"]
    assert run(bad, "groovy", "build.gradle") == []  # Kotlin DSL only


def test_target_hierarchy_fix():
    fs = run("kotlin {\n  targetHierarchy.default()\n}")
    assert ids(fs) == ["target-hierarchy"] and fs[0].edit[2] == "applyDefaultHierarchyTemplate()"
    fs = run("kotlin { targetHierarchy.default { common { } } }")
    assert ids(fs) == ["target-hierarchy"] and not fs[0].edit
    assert run("kotlin { applyDefaultHierarchyTemplate() }") == []


def test_compilation_accessors_and_hierarchy_builder():
    assert ids(run('val t = kotlin.jvm().compilations["main"].compileKotlinTask')) == ["compilation-task-accessors"]
    assert ids(run('x.compilations.all { compileKotlinTaskProvider.configure { } }')) == []  # no receiver dot: not flagged (documented limit)
    assert ids(run('c.compileKotlinTaskProvider.get()')) == ["compilation-task-accessors"]
    assert run('c.compileTaskProvider.get()') == []
    assert ids(run('common { group("x") { withWasm() } }')) == ["hierarchy-builder-removed"]
    assert ids(run('common { group("x") { filterCompilations { true } } }')) == ["hierarchy-builder-removed"]
    assert run('common { group("x") { withWasmJs(); withWasmWasi() } }') == []


def test_compose_options():
    assert ids(run('composeCompiler { enableStrongSkippingMode = true }')) == ["compose-compiler-options"]
    assert ids(run('composeCompiler { enableIntrinsicRemember.set(true)\n generateFunctionKeyMetaClasses = true }')) == ["compose-compiler-options"] * 2
    fs = run('composeCompiler { stabilityConfigurationFile.set(file("s.conf")) }')
    assert fs[0].edit and fs[0].edit[2] == "stabilityConfigurationFiles.add("
    assert ids(run('composeCompiler { featureFlags.add(ComposeFeatureFlag.StrongSkipping) }')) == ["compose-compiler-options"]
    assert run('composeCompiler { stabilityConfigurationFiles.add(file("s.conf")) }') == []
    assert run('val enableStrongSkippingMode = 1') == []  # outside composeCompiler { }


def test_abi_validation():
    assert ids(run('kotlin { abiValidation { legacyDump { referenceDumpDir.set(file("api")) } } }')) == ["abi-validation-legacy"]
    assert ids(run('kotlin { abiValidation { klib { enabled = true\n keepUnsupportedTargets = false } } }')) == ["abi-validation-legacy"] * 2
    assert ids(run('kotlin { abiValidation { enabled = true\n klib { } } }')) == ["abi-validation-legacy"]
    assert run('kotlin { abiValidation { }\n x { enabled = true } }') == []
    assert ids(run('abiValidation { filters { excluded { byNames.add("a") } } }')) == []


def test_js_compiler_type_fix_and_android_sourcesets():
    fs = run("kotlin { js(IR) { nodejs() } }")
    assert ids(fs) == ["js-compiler-type"] and fs[0].severity == "warning" and fs[0].edit[2] == "js"
    assert run("kotlin { js(IR) }")[0].edit[2] == "js()"
    assert run("kotlin { js { nodejs() } }") == []
    android = 'plugins { id("com.android.library") }\nkotlin { sourceSets { getByName("main").kotlin.srcDir("x") } }'
    assert ids(run(android)) == ["kotlin-android-sourcesets"]
    assert run(android.replace("com.android.library", "com.android.library") + '\nkotlin { androidTarget() }') == []
    assert run('kotlin { sourceSets { } }') == []  # not an Android module
    # false positives found by the study: KMP libraries applied through a convention-plugin alias
    kmp_alias = 'plugins { alias(libs.plugins.generic.kmp.library) }\nandroid { namespace = "x" }\nkotlin { sourceSets { commonMain { dependencies { } } } }'
    assert run(kmp_alias) == []
    assert run('plugins { alias(libs.plugins.myKotlinMultiplatformLibrary) }\nandroid { namespace = "x" }\nkotlin { sourceSets { val m by getting { } } }') == []


def test_ignore_comment_and_disable():
    t = 'kotlin {\n  // kotlin24-ready: ignore target-hierarchy\n  targetHierarchy.default()\n}'
    assert run(t) == []
    assert run("kotlin { targetHierarchy.default() }", disabled=frozenset({"target-hierarchy"})) == []
    assert ids(run("kotlin { targetHierarchy.default()\n composeCompiler { enableStrongSkippingMode = true } }", only=frozenset({"target-hierarchy"}))) == ["target-hierarchy"]


def test_convention_plugin_sources():
    src = 'import org.jetbrains.kotlin.gradle.dsl.KotlinVersion\nproject.extensions.configure<K>() { composeCompiler { enableStrongSkippingMode.set(true) }\n languageVersion.set(KotlinVersion.KOTLIN_1_9)\n val t = c.compileKotlinTask }'
    fs = scan_text("build-logic/src/main/kotlin/A.kt", src, "source", Project())
    assert ids(fs) == ["compilation-task-accessors", "compose-compiler-options", "language-version-1-9"]


def test_kotlin_options():
    assert ids(run('tasks.withType<KotlinCompile>().configureEach { kotlinOptions { jvmTarget = "17" } }')) == ["kotlin-options"]
    assert run('android { kotlinOptions { jvmTarget = "17" } }') == []  # builds on 2.4.20 (agp9-ready covers AGP 9)
    assert ids(run('kotlin { kotlinOptions { jvmTarget = "17" } }')) == ["kotlin-options"]
    assert ids(run('androidTarget { compilations.all { kotlinOptions { jvmTarget = "11" } } }')) == ["kotlin-options"]
    assert ids(run("tasks.withType(KotlinCompile).configureEach { kotlinOptions { jvmTarget = '17' } }", "groovy", "build.gradle")) == ["kotlin-options"]
    assert ids(run('tasks.withType<org.jetbrains.kotlin.gradle.tasks.KotlinCompile> {\n kotlinOptions.jvmTarget = "11"\n}')) == ["kotlin-options"]
    assert ids(run('tasks.withType<KotlinCompile> { kotlinOptions.freeCompilerArgs += "-Xfoo" }', "source", "buildSrc/A.kt")) == ["kotlin-options"]
    assert run('kotlin { compilerOptions { jvmTarget.set(JvmTarget.JVM_17) } }') == []
    assert run('// kotlinOptions { }\nval s = "kotlinOptions"') == []
    assert run('val x = myKotlinOptions') == []


def test_kotlin_js_plugin():
    assert ids(run('plugins { id("org.jetbrains.kotlin.js") version "2.3.0" }')) == ["kotlin-js-plugin"]
    assert ids(run('plugins { kotlin("js") }')) == ["kotlin-js-plugin"]
    assert ids(run("apply plugin: 'kotlin-js'", "groovy", "build.gradle")) == ["kotlin-js-plugin"]
    assert ids(run('kotlin-js = { id = "org.jetbrains.kotlin.js", version.ref = "kotlin" }', "catalog", "gradle/libs.versions.toml")) == ["kotlin-js-plugin"]
    assert run('plugins { kotlin("multiplatform") }') == []
    assert run('plugins { id("org.jetbrains.kotlin.jvm") }') == []
    assert run('implementation("org.jetbrains.kotlin-wrappers:kotlin-js:1")') == []


def test_abi_removed_types_and_extension_enabled():
    src = 'import org.jetbrains.kotlin.gradle.dsl.abi.AbiValidationMultiplatformExtension\nimport org.jetbrains.kotlin.gradle.dsl.abi.AbiValidationVariantSpec'
    assert ids(run(src)) == ["abi-validation-legacy", "abi-validation-legacy"]
    cfg = 'extensions.configure<AbiValidationExtension> {\n enabled = true\n applyFilters()\n}'
    assert ids(run(cfg)) == ["abi-validation-legacy"]
    assert run('extensions.configure<AbiValidationExtension> {\n applyFilters()\n}') == []
    assert run('extensions.configure<Other> {\n enabled = true\n}') == []
