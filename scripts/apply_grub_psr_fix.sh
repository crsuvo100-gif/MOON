#!/usr/bin/env bash
# MOON persistent display fix: disable Intel i915 PSR / RC6 / display-C states
# to stop eDP panel flicker on Ice Lake. Run ONCE with sudo:
#   sudo bash /home/meow/Projects/MOON/scripts/apply_grub_psr_fix.sh
# Then the setting applies on the NEXT reboot (this script does NOT reboot).
set -euo pipefail

GRUB=/etc/default/grub
CONF=/etc/X11/xorg.conf.d/20-intel.conf
[ -f "$GRUB" ] || { echo "ERROR: $GRUB not found"; exit 1; }

echo "== backup grub =="
cp -a "$GRUB" "${GRUB}.moon.bak.$(date +%s)"
echo "== add i915 power-management params to GRUB_CMDLINE_LINUX_DEFAULT =="

# Idempotent: if the params are already present, skip.
if grep -q "i915.enable_psr=0" "$GRUB"; then
  echo "i915 params already present — leaving grub line as-is."
else
  # Replace the first GRUB_CMDLINE_LINUX_DEFAULT="..." (whatever its content) with the
  # quiet + i915-disabling params.
  sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT="[^"]*"/GRUB_CMDLINE_LINUX_DEFAULT="quiet i915.enable_psr=0 i915.enable_rc6=0 i915.enable_dc=0 intel_idle.max_cstate=1"/' "$GRUB"
  echo "updated grub cmdline."
  grep -n GRUB_CMDLINE_LINUX_DEFAULT "$GRUB"
fi

echo "== write X11 TearFree drop-in (stops compositor tearing) =="
mkdir -p "$(dirname "$CONF")"
cat > "$CONF" <<'EOF'
Section "Device"
    Identifier "Intel Graphics"
    Driver "modesetting"
    Option "TearFree" "true"
EndSection
EOF
echo "wrote $CONF"

echo "== regenerate boot config =="
if command -v update-grub >/dev/null 2>&1; then
  update-grub
elif command -v grub-mkconfig >/dev/null 2>&1; then
  grub-mkconfig -o /boot/grub/grub.cfg
else
  echo "WARN: no update-grub/grub-mkconfig found; run it manually."
fi

echo "DONE. Reboot at your convenience to apply (sudo reboot)."
echo "To revert: restore ${GRUB}.moon.bak.* and remove $CONF, then update-grub."
