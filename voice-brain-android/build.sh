#!/usr/bin/env bash
# Build the APK from the terminal (no Android Studio needed after the first run).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

# JDK 21 toolchain (Studio's JBR is Java 25, which Gradle 8.7 cannot run on)
if [ -d "$HOME/.local/share/mise/installs/java/temurin-21.0.12+101.0.LTS" ]; then
  export JAVA_HOME="$HOME/.local/share/mise/installs/java/temurin-21.0.12+101.0.LTS"
fi
export PATH="$JAVA_HOME/bin:$PATH"

./gradlew assembleDebug "$@"
echo
echo "✅ APK: app/build/outputs/apk/debug/app-debug.apk"
echo "   Install over USB: ~/Android/Sdk/platform-tools/adb install -r app/build/outputs/apk/debug/app-debug.apk"
