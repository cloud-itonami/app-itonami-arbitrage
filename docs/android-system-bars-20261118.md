# Awai Arbitrage: system bars and 16 KB alignment on Android — 2026-11-18 (AWAI-3441)

Applies the AWAI-3393 procedure (same form as awai-os `apps/x402`):

- `src-tauri/build.rs` passes `-Wl,-z,max-page-size=16384` for Android targets only.
- `MainActivity` pads the content view by the system-bar, cutout and IME insets
  (Android 15 draws edge to edge for targetSdk 35+, and the WebView reports no
  safe-area inset), colours the decor with the page background (#f7f7f5 light /
  #121212 dark), sets the bar icons for light / dark, turns off the 3-button
  navigation contrast scrim, and repeats this on `onConfigurationChanged` (`uiMode`
  is in the manifest's `configChanges`).

## Checks

| Check | Result |
|---|---|
| Clean debug APK (outputs and intermediates removed first; `CARGO_BUILD_JOBS=4 nice -n 10`) | SHA-256 `5f72de01cdc3245fd75f53a7a0765d499faa64dbe6be8955b37d5df271d4d21a`, 148,008,605 bytes |
| `llvm-readelf -lW` on `libitonami_arbitrage_lib.so` | every LOAD `Align 0x4000` |
| `zipalign -c -P 16 -v 4` | Verification successful |
| `aapt dump permissions` | no `android.*` permission |
| AOSP API 35 arm64 emulator (dedicated AVD, removed afterwards), light | page below the status bar and above the navigation bar, dark icons ([screenshot](evidence/android-system-bars-light-20261118.png)) |
| same, after `cmd uimode night yes` | dark decor, light icons, no overlap ([screenshot](evidence/android-system-bars-dark-20261118.png)) |
| sockets for the app uid in `/proc/net/{tcp,tcp6,udp,udp6}` | none |
| logcat FATAL / ANR | none |

Toolchain: tauri-cli 3.0.0-alpha.6, Rust 1.99.1, NDK 27.0.12077973, JDK 21, build-tools 36.1.0.
Not covered: a real device (the 16 KB compatibility dialog only shows on a device such as the moto g05).
