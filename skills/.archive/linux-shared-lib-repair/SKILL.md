---
name: linux-shared-lib-repair
description: App crashes on missing .so SONAME after a library upgrade.
---

# Linux shared-library repair (missing .so / SONAME mismatch)

## Trigger
An app (Electron/VS Code, a C++ binary, a Python module with a `.node`/`.so`
extension, etc.) fails to start with:
`Error: libXXX.so.NN: cannot open shared object file: No such file or directory`
This most often happens **after a system upgrade bumped a core library's ABI
version** (e.g. Node, OpenSSL, ICU, glibc add-ons) while a vendored native
module still `NEEDED` the old SONAME. The app was built against the old ABI and
no longer finds it.

## Golden rule
**Satisfy the SONAME the loader wants, scoped to that app only.** Never globally
replace or overwrite a system `.so`. Prefer a user-local versioned symlink +
`LD_LIBRARY_PATH` over touching `/usr/lib` or `ld.so.cache`.

## Diagnostic sequence (verify, don't guess)
1. Reproduce and capture the *exact* missing SONAME from the error
   (`libnode.so.115`, `libssl.so.3`, ...).
2. Find the binary/module that needs it:
   - For Electron/Node apps: the native module is usually under
     `.../node_modules/<pkg>/build/Release/*.node` or
     `.../node_modules/<pkg>/lib/*.node`. Use
     `find /usr/lib/<app> -name '*.node' 2>/dev/null`.
   - For a normal ELF: the binary itself.
3. Confirm what it actually needs:
   `objdump -p <module> | grep NEEDED`
   → look for the `libXXX.so.NN` line.
4. See what version the system *does* have:
   `find / -name 'libXXX.so*' 2>/dev/null`
   `objdump -p <found-lib> | grep SONAME`  → note its real SONAME.
5. Decide: if the installed lib's SONAME differs only by version
   (needed `115`, have `137`), it's an **ABI-version gap**.

## Fix — scoped symlink + LD_LIBRARY_PATH (preferred)
```sh
# user-writable location (avoid /opt which may be root-owned)
mkdir -p ~/.local/libnode-fix
ln -sf /usr/lib/x86_64-linux-gnu/libXXX.so.NN  ~/.local/libnode-fix/libXXX.so.MM
# where .MM is the SONAME the app wants, target is the installed lib
```
Then launch the app with that dir prepended:
```sh
LD_LIBRARY_PATH=~/.local/libnode-fix /path/to/app --no-sandbox
```
Verify the loader resolves it:
```sh
ldd <module> | grep -i libXXX
# expect: libXXX.so.MM => ~/.local/libnode-fix/libXXX.so.MM (resolved)
```

### Alternate (system-wide) — only if the symlink approach is impractical
Drop the symlink into a system lib dir and rebuild the cache:
```sh
sudo ln -sf /usr/lib/x86_64-linux-gnu/libXXX.so.NN /usr/lib/x86_64-linux-gnu/libXXX.so.MM
sudo ldconfig
```
Use this only when many apps or services need it; it's less reversible.

## The ABI-mismatch caveat (IMPORTANT)
A symlink makes the *loader* happy but does **not** guarantee the symbols match.
If the ABI really changed (e.g. major V8/Node ABI bump), the app may still
crash at runtime with an `undefined symbol` or a renderer crash.
- **Always verify the actual launch**, not just that `ldd` resolves:
  - For GUI apps, confirm a window renders (see below).
  - Watch the process tree: a healthy Electron app spawns `zygote`,
    `gpu-process`, `renderer`, and `node.mojom.NodeService` (extension host).
- If it still crashes after resolving the SONAME, the *real* fix is to
  **reinstall the app built against the current library** (e.g. re-run the
  distro package manager, or downgrade the offending library). Don't keep
  stacking symlinks — that hides breakage.

## Launch verification with computer_use
GUI apps leave no stdout telling you they rendered. Confirm with a screenshot:
1. `computer_use action=list_windows` → find the app's window id / pid.
2. `computer_use action=capture pid=... window_id=...` → vision confirms the
   window painted (not blank/crashed).
For a CLI tool, just check the exit code / output.

## Anti-patterns
- Don't `apt remove`/`reinstall` the system lib blindly — you may break 20
  other things. The scoped symlink is reversible and isolated.
- Don't paste `export LD_LIBRARY_PATH=...` into `~/.bashrc` permanently for a
  one-off; scope it to the launch command or a wrapper script.
- Don't assume `code` = the Microsoft binary on Kali — `/usr/bin/code` is a
  wrapper that execs `code-oss` (see references/code-oss-libnode115.md).

## References
- `references/code-oss-libnode115.md` — full worked transcript: Code-OSS
  (Kali) crashing on `libnode.so.115` after a Node 24 upgrade, fixed via a
  `~/.local/libnode-fix/libnode.so.115 -> libnode.so.137` symlink + scoped
  `LD_LIBRARY_PATH`, verified by window screenshot.
