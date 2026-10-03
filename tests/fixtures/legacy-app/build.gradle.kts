import org.jetbrains.kotlin.gradle.dsl.KotlinVersion

plugins {
    kotlin("multiplatform") version "2.3.20"
    id("org.jetbrains.kotlin.plugin.compose") version "2.3.20"
}

kotlin {
    jvm()
    js(IR) { nodejs() }
    targetHierarchy.default()
    compilerOptions { languageVersion.set(KotlinVersion.KOTLIN_1_9) }
    sourceSets {
        commonMain.dependencies {
            implementation(platform("org.jetbrains.kotlinx:kotlinx-coroutines-bom:1.10.2"))
        }
    }
}

composeCompiler {
    enableStrongSkippingMode = true
    stabilityConfigurationFile.set(layout.projectDirectory.file("stability.conf"))
}
