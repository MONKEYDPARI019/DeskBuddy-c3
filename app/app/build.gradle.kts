plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.deskbuddy.app"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.deskbuddy.app"
        minSdk = 26
        targetSdk = 34
        versionCode = 7
        versionName = "0.6.0"
    }

    // One fixed key, so a new APK installs over the old one (no uninstall, settings kept).
    // CI reads it from the repository secrets (see docs/development.md); the keystore itself is
    // never in the repository. Without the secrets (a local build) release APKs use the debug key.
    val keystoreFile = System.getenv("DESKBUDDY_KEYSTORE")?.let { file(it) }?.takeIf { it.isFile }
    signingConfigs {
        if (keystoreFile != null) {
            create("release") {
                storeFile = keystoreFile
                storePassword = System.getenv("DESKBUDDY_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("DESKBUDDY_KEY_ALIAS") ?: "deskbuddy"
                keyPassword = System.getenv("DESKBUDDY_KEY_PASSWORD") ?: System.getenv("DESKBUDDY_KEYSTORE_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = if (keystoreFile != null) signingConfigs.getByName("release")
                            else signingConfigs.getByName("debug")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
    }
    composeOptions {
        // must match the Kotlin version in the root build.gradle.kts (1.9.24)
        kotlinCompilerExtensionVersion = "1.5.14"
    }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.06.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.activity:activity-compose:1.9.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    testImplementation("junit:junit:4.13.2")
}
