---
name: linux-system-optimization
description: Optimizing Linux systems for LLM deployment, focusing on memory management and persistent service orchestration.
---

# Linux System Optimization for LLMs

This skill manages the preparation of Linux environments (Kali, Ubuntu, Debian) to support large language models when physical RAM is limited.

## Memory Expansion (Swap)
When RAM is insufficient for model weights, increasing swap space is the primary mitigation strategy to prevent OOM (Out-Of-Memory) kills.

### High-Performance Swap Creation
1. **Disable existing swap**: `sudo swapoff -a`
2. **Create the swap file**: Use `fallocate` for speed, but fallback to `dd` if the filesystem doesn't support it or if \"Text file busy\" errors occur.
   - Fast: `sudo fallocate -l <SIZE>G /swapfile`
   - Reliable: `sudo dd if=/dev/zero of=/swapfile bs=1M count=<SIZE_IN_MB>`
3. **Secure permissions**: `sudo chmod 600 /swapfile`
4. **Format swap**: `sudo mkswap /swapfile`
5. **Activate**: `sudo swapon /swapfile`
6. **Persist on boot**: Add `/swapfile none swap sw 0 0` to `/etc/fstab`.

**Pitfalls:**
- **Text File Busy**: If `fallocate` or `rm` fails with \"Text file busy\", the swap file is currently active. Run `sudo swapoff /swapfile` first.
- **Sudo timeouts**: Large `dd` operations can time out in some agent environments; execute in smaller chunks or with extended timeouts.

## Persistent Service Orchestration
For AI agents that must remain active (e.g., Discord bots, API gateways), use `systemd` rather than `nohup` or `tmux`.

### Systemd Unit Implementation
Create a unit file in `/etc/systemd/system/<name>.service` with the following requirements:
- `After=network.target`: Ensures the bot doesn't start before the internet is available.
- `Restart=always`: Guarantees autonomy and recovery from crashes.
- `WorkingDirectory`: Must be absolute to resolve relative imports in Python.
- `StandardOutput/Error`: Append to log files for telemetry.

### Verification Workflow
1. `sudo systemctl daemon-reload`
2. `sudo systemctl enable <name>`
3. `sudo systemctl restart <name>`
4. `sudo systemctl status <name>`

## User Utility Integration
Embed service management into the user's shell environment via aliases to remove the friction of remembering `systemctl` flags.

**Recommended Aliases:**
- `<name>-wake`: Status check + confirmation message.
- `<name>-logs`: `tail -f` on the service log file.
- `<name>-restart`: Restart command.
