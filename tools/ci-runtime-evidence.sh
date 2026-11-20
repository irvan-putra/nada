#!/usr/bin/env bash
# Build the signed release APK, install it on the emulator, and prove the save
# path by driving the real UI: launch the app, tap the page's Build button
# through the accessibility tree (uiautomator dump + input tap), screenshot,
# and require the saved .mid in Music/nada. The production app carries no test
# hooks or automation extras. Invoked as one line from the emulator CI step:
# android-emulator-runner runs each script line in its own shell, so all state
# must live inside this file.
set -euo pipefail
cd "$GITHUB_WORKSPACE"
echo "$SIGNING_KEYSTORE_B64" | base64 -d > "$RUNNER_TEMP/keystore.jks"
export SIGNING_KEYSTORE_PATH="$RUNNER_TEMP/keystore.jks"
gradle -p android :app:assembleRelease
unset SIGNING_KEYSTORE_PATH
APK=$(ls android/app/build/outputs/apk/release/*.apk | head -1)
echo "release APK: $APK"
adb install -r "$APK"
adb shell am start -n com.vanipy.nada/.MainActivity
sleep 6  # let the bundled page finish loading
adb shell uiautomator dump /sdcard/nada-window.xml
adb pull /sdcard/nada-window.xml "$RUNNER_TEMP/nada-window.xml" >/dev/null
TAP=$(python3 - "$RUNNER_TEMP/nada-window.xml" <<'PY'
import re, sys, xml.etree.ElementTree as ET
for node in ET.parse(sys.argv[1]).iter('node'):
    label = ((node.get('text') or '') + ' ' + (node.get('content-desc') or '')).lower()
    if 'build' in label:
        m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', node.get('bounds') or '')
        if m:
            x1, y1, x2, y2 = map(int, m.groups())
            print((x1 + x2) // 2, (y1 + y2) // 2)
            break
PY
)
if [ -z "$TAP" ]; then
  echo "ERROR: Build button not found in the UI accessibility dump:"
  cat "$RUNNER_TEMP/nada-window.xml"
  exit 1
fi
echo "tapping Build button at $TAP"
adb shell input tap $TAP
sleep 3
adb exec-out screencap -p > "$RUNNER_TEMP/nada-runtime-1.png"
sleep 2
adb exec-out screencap -p > "$RUNNER_TEMP/nada-runtime-2.png"
adb shell ls -l /storage/emulated/0/Music/nada/ || true
if ! adb shell ls /storage/emulated/0/Music/nada/ | tr -d '\r' | grep -qx 'twinkle_twinkle.mid'; then
  echo "ERROR: twinkle_twinkle.mid missing from Music/nada after UI-driven save"
  exit 1
fi
adb uninstall com.vanipy.nada
