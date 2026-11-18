# Awai Arbitrage debug APK on an AOSP emulator — 2026-11-18 (AWAI-3398)

Follow-up to AWAI-3383; recipe from AWAI-3178 (awai-deai). All times UTC.

## Setup

| | |
|---|---|
| APK | `npm run build:android` from this branch (main `9d144f8` + the two fixes below). `app-universal-debug.apk`, 288,781,205 bytes, SHA-256 `f90cf9f93504967a019ecfd060d7e03033b7015c02b60b80ed9e1bf2957714ab`, package `cloud.itonami.arbitrage`, minSdk 24, targetSdk 37, arm64-v8a only. Debug key; not a release. |
| Toolchain | tauri-cli 3.0.0-alpha.6, Rust 1.99.1, NDK 27.0.12077973, JDK 21 (Temurin 21.0.1), Node 26.0.0, build-tools 36.1.0. |
| Emulator | Dedicated AVD `Awai_Arbitrage_AWAI3398`: AOSP `system-images;android-35;default;arm64-v8a` (`sdk_phone64_arm64`, Android 15, `AE3A.240806.019`, no Google packages), 2 GB RAM, 2 cores, headless, `-wipe-data`. Android System WebView 124.0.6367.219. Host load average 11–17. |
| Requested permissions | Only `cloud.itonami.arbitrage.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION` (AndroidX internal). No `INTERNET`. |

## Results

| Step | Result |
|---|---|
| Install and cold launch | **Pass.** `am start -W` Status ok, COLD, TotalTime 1,165 ms (first APK) / 1,943 ms (fixed APK); `MainActivity` top resumed. The header shows "Awai app", so the `awai_host_info` IPC command answered. |
| First launch layout | **Fail, fixed.** The header sat under the status bar and the text `nullnull` appeared at the bottom. Causes: Android 15 draws edge to edge and the WebView reports no safe-area inset; `render()` passed `null` to `replaceChildren`, which inserts the text "null" (the browser test always had a feed loaded, so it never showed). Fixes: `MainActivity` pads the content view by the system-bar, cutout and IME insets; `render()` drops absent parts. Re-run with the fixed APK: header below the status bar, content above the navigation bar, no stray text ([screenshot](evidence/android-emulator-launch-20261118.png)). |
| File picker in the Android WebView | **Pass.** "Choose File" opened DocumentsUI (`com.android.documentsui/.picker.PickActivity`) ([screenshot](evidence/android-emulator-file-picker-20261118.png)). Picking `sample-proposals-SAMPLE.json` (435 B, pushed to Downloads; every entry is labelled SAMPLE and is not a measurement) gave 「提案 2 件、除外 1 件」 ([screenshot](evidence/android-emulator-imported-20261118.png)); the excluded item is the one without an `arb-` id. |
| Kind filter | **Pass.** Turning on 「手続きの難しさ」 showed 「2 件中 1 件」, the procedural sample only ([screenshot](evidence/android-emulator-filter-20261118.png)). |
| State after force-stop and cold start | **Pass.** TotalTime 954 ms; the page still showed the imported file name and 「2 件中 1 件」. |
| No traffic from the app uid (10148) | **Pass.** No row for uid 10148 in `/proc/net/{tcp,tcp6,udp,udp6}` after import and filtering, and again after the restart. `dumpsys connectivity trafficcontroller` lists `10148 PERMISSION_NONE` in `sUidPermissionMap` (no INTERNET for the uid). `dumpsys netstats detail` has byte counters for other uids (for example uid 1051 rb=4925) and none for 10148; its only line for 10148 is `uid=10148 set=1`, the foreground counter set, which counts no bytes. Positive control: `ping -c 2 8.8.8.8` from the guest got 2/2 replies. |
| Crashes | **Pass.** No `FATAL EXCEPTION` or `ANR in` in logcat for the session. |

## Not covered

A real device, a release key or store build, the public feed (AWAI-3207 child 2), and the in-device disparity filter and Figma-first UI (child 4). The emulator's attached-device list included other sessions' emulators and a physical phone; none of them was used.

## Re-run

Boot an AOSP API 35 arm64 AVD headless, `adb install -r` the APK, `am start -W -n cloud.itonami.arbitrage/.MainActivity`, push a proposal file to `/sdcard/Download`, pick it through "Choose File", tick a kind, force-stop and relaunch, and check `/proc/net/{tcp,tcp6,udp,udp6}` and `sUidPermissionMap` for the app uid.
