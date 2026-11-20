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
# WebView DOM is not exposed to uiautomator's accessibility dump on the CI
# emulator (proven: run 44675362098 dump contains the WebView node only), so
# find the page's Build button by its exact CSS color instead: #0b7285 teal,
# the only solid-teal element on the page (button.primary in web/index.html).
pip install pillow==12.3.0 --quiet
adb exec-out screencap -p > "$RUNNER_TEMP/nada-pre-tap.png"
TAP=$(python3 - "$RUNNER_TEMP/nada-pre-tap.png" <<'PY'
import sys
from PIL import Image
im = Image.open(sys.argv[1]).convert('RGB')
w, h = im.size
px = im.load()
xs, ys = [], []
for y in range(h):
    for x in range(w):
        r, g, b = px[x, y]
        if abs(r - 11) <= 2 and abs(g - 114) <= 2 and abs(b - 133) <= 2:
            xs.append(x); ys.append(y)
if xs:
    print((min(xs) + max(xs)) // 2, (min(ys) + max(ys)) // 2)
PY
)
if [ -z "$TAP" ]; then
  echo "ERROR: teal Build button (#0b7285) not found on screen; see nada-pre-tap.png in diagnostics"
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
