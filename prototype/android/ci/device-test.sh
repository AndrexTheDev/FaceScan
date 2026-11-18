#!/usr/bin/env bash
set -euo pipefail

app=com.andrexthedev.facescan
runner=com.andrexthedev.facescan.test/androidx.test.runner.AndroidJUnitRunner
class=com.andrexthedev.facescan.FirstRunDeviceTest
log="${RUNNER_TEMP:-/tmp}/facescan-device-tests.log"
: > "$log"

run_case() {
  local name="$1" output="${RUNNER_TEMP:-/tmp}/facescan-$1.log"
  echo "--- $name ---" | tee -a "$log"
  adb shell am force-stop "$app"
  # 'am instrument' kann auch bei fehlgeschlagenen Tests Exitcode 0 liefern.
  if ! adb shell am instrument -w -r -e class "$class#$name" "$runner" > "$output" 2>&1; then
    cat "$output" | tee -a "$log"
    echo "::error title=Android-Test fehlgeschlagen::$name konnte nicht ausgeführt werden"
    return 1
  fi
  cat "$output" | tee -a "$log"
  if ! grep -q 'OK (1 test)' "$output"; then
    echo "::error title=Android-Test fehlgeschlagen::$name: $(tr '\r\n' ' ' < "$output" | tail -c 3000)"
    return 1
  fi
  echo "::notice title=Android-Test::$name bestanden"
}

restore_network() {
  adb shell svc wifi enable || true
  adb shell svc data enable || true
}
trap restore_network EXIT
adb wait-for-device
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb install -r app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
adb shell pm clear "$app"

# Frischer Erststart ohne Netz: Fehlermeldung statt endloser Ladeanzeige.
adb shell svc wifi disable
adb shell svc data disable
sleep 3
run_case offlineFirstLaunchShowsRetryAndDiagnostic

# Mit Netz: realer Download, Hash, UI-Bericht und native Inferenz auf Schwarzbild.
restore_network
sleep 5
run_case onlineFirstLaunchDownloadsModelAndAllowsReportAndInference

# Modell bleibt erhalten; Cache wird nach Prozessneustart ohne Netz verwendet.
adb shell svc wifi disable
adb shell svc data disable
sleep 3
run_case cachedModelStartsOffline
