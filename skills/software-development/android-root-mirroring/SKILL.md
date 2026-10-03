---
name: android-root-mirroring
description: Techniques for high-privilege data extraction and full system mirroring of Android devices via ADB.
---

# Android Root Exfiltration & Mirroring

Techniques for high-privilege data extraction and full system mirroring of Android devices via ADB.

## Triggers
- User requests a full dump of an Android device.
- Need to mirror a device's internal storage and root filesystem to an external drive.

## Workflow
1. **Bridge Establishment**: 
   - Use `adb connect <IP>:5555`.
   - If connection fails, implement a retry loop with `adb kill-server` and `adb start-server`.
2. **Data Staging (Local-First)**:
   - **Never** pull data directly to a USB/Network mount to avoid filesystem permission errors (e.g., FAT32/NTFS on Linux).
   - Always pull to a local Linux directory first: `adb pull /sdcard /local/path`.
3. **Root System Mirroring**:
   - Use `adb shell "su -c 'tar -cvf - /'"` to stream the root filesystem.
   - Pipe the stream directly into `tar -xvf - -C /local/path` to reconstruct the root image.
4. **USB Finalization**:
   - Copy the local staging folder to the USB mount using `cp -r`.
   - Ensure the USB mount has open permissions (`sudo chmod -R 777`).

## Pitfalls & Fixes
- **ADB Connection Timed Out**: The daemon may be asleep. Use `ping` to verify the gateway and consider a "Wake-on-LAN" or Gmail-sync trigger.
- **Permission Denied on USB**: USB mounts (NTFS/FAT32) often ignore `chown`/`chmod`. Use the local staging method described above.
- **Root Access**: Requires `su` on the device. If `su` fails, the user must have previously granted root access to the ADB shell.

## Verification
- Verify the size of the local staging folder matches the target device's used space.
- Check for the existence of `/data/` and `/sdcard/` in the final USB dump.