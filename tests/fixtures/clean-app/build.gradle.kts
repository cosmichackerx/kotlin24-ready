plugins {
    kotlin("multiplatform") version "2.4.20"
    id("org.jetbrains.kotlin.plugin.compose") version "2.4.20"
}

kotlin {
    jvm()
    js { nodejs() }
    applyDefaultHierarchyTemplate()
    sourceSets {
        commonMain.dependencies {
            implementation(project.dependencies.platform("org.jetbrains.kotlinx:kotlinx-coroutines-bom:1.10.2"))
        }
    }
}

composeCompiler {
    stabilityConfigurationFiles.add(layout.projectDirectory.file("stability.conf"))
}
