plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
}

android {
    namespace = "com.andrexthedev.facescan"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.andrexthedev.facescan"
        minSdk = 29          // Android 10 – Deckung ~98 %
        targetSdk = 35
        versionCode = 4
        versionName = "0.3.0-test"
        // MediaPipe 0.10.14 liefert kein x86_64-JNI. Auf x86_64-Geräten
        // mit 32-Bit-Support muss Android daher die x86-Variante auswählen.
        ndk { abiFilters += setOf("arm64-v8a", "armeabi-v7a", "x86") }
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
        debug {
            // M0: lauffaehiger Prototyp, R8 aus (schnellere Builds, bessere Stacktraces)
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { compose = true }
    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.activity.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.kotlinx.coroutines.android)

    // Kamera (CameraX) + Camera2-Interop fuer manuelle Belichtungssteuerung
    implementation(libs.androidx.camera.core)
    implementation(libs.androidx.camera.camera2)
    implementation(libs.androidx.camera.lifecycle)
    implementation(libs.androidx.camera.view)

    // Wahrnehmung: on-device, Apache-2.0 (Modellkarten vor Einbau pruefen!)
    implementation(libs.mediapipe.tasks.vision)

    // Reine JVM-Unit-Tests (kein Robolectric, keine JSON-Parser – Fixtures sind Kotlin)
    testImplementation(libs.junit)

    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)
    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.androidx.test.ext.junit)
    debugImplementation(libs.androidx.compose.ui.test.manifest)
}
