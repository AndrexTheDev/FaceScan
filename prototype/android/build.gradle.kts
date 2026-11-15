// Root-Gradle-Datei. Plugins werden nur deklariert, in den Modulen aktiviert.
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.android) apply false
    alias(libs.plugins.kotlin.compose) apply false
}
