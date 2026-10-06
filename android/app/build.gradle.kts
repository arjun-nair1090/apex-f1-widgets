plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
}

android {
    namespace = "club.apex"
    compileSdk = 37
    defaultConfig {
        applicationId = "club.apex"
        minSdk = 26
        targetSdk = 37
        versionCode = 1
        versionName = "1.0"
        buildConfigField("String", "BASE_URL", "\"${providers.gradleProperty("apexBaseUrl").get()}\"")
    }
    buildFeatures { compose = true; buildConfig = true }
    buildTypes {
        release { isMinifyEnabled = true; proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt")) }
    }
}

dependencies {
    implementation("androidx.glance:glance-appwidget:1.2.0")
    implementation("androidx.work:work-runtime-ktx:2.12.0")
    implementation("androidx.activity:activity-compose:1.13.0")
    implementation(platform("androidx.compose:compose-bom:2026.09.00"))
    implementation("androidx.compose.material3:material3")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.11.0")
}
