#!/usr/bin/env bash
# Build the signed release APK, install it on the emulator, launch it with
# autosave, and capture runtime evidence (screenshots + MediaStore query).
# Invoked as one line from the emulator CI step: android-emulator-runner runs
# each script line in its own shell, so all state must live inside this file.
set -euo pipefail
cd "$GITHUB_WORKSPACE"
echo "$SIGNING_KEYSTORE_B64" | base64 -d > "$RUNNER_TEMP/keystore.jks"
export SIGNING_KEYSTORE_PATH="$RUNNER_TEMP/keystore.jks"
gradle -p android :app:assembleRelease
unset SIGNING_KEYSTORE_PATH
APK=$(ls android/app/build/outputs/apk/release/*.apk | head -1)
echo "release APK: $APK"
adb install -r "$APK"
adb shell am start -n com.vanipy.nada/.MainActivity --ez autosave true
sleep 3
adb exec-out screencap -p > "$RUNNER_TEMP/nada-runtime-1.png"
sleep 2
adb exec-out screencap -p > "$RUNNER_TEMP/nada-runtime-2.png"
adb shell content query --uri content://media/external_primary/audio/media \
  --projection _display_name:relative_path:_size \
  --where "_display_name='twinkle_twinkle.mid'" || true
adb uninstall com.vanipy.nada
