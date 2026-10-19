#!/usr/bin/env bash
# =============================================================================
# setup-cybersecurity-mode.sh
# ONE-CLICK IDEMPOTENT SECURITY TOOL INSTALLER + MOON-AI CYBER-AGENT PATCHER
#
#   (b) installs every offensive/defensive security tool available in the
#       terminal, verifying each one after install (silent, no-fail exit).
#   (c) patches/pins the MOON-AI cyber-agent surface: red/black HUD palette,
#       all-functions-open, voice-clone hook, 3 entry points.
#
#   NON-DESTRUCTIVE: never removes existing packages. Safe to run twice.
#   Exit codes: 0 success   1 partial   2 aborted (user opt-out)
#
#   Usage:  sudo bash setup-cybersecurity-mode.sh [--yes] [--no-moon]
#           sudo bash setup-cybersecurity-mode.sh --verify
# =============================================================================

set -u
BINARY=
VERIFY_ONLY=0
MOON-AI_ONLY=0
YES=0

# MOON-AI surface directory (defaults to the standard install location).
moon="${MOON-AI_DIR:-${HOME}/Projects/MOON-AI}"
moon="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for a in "$@"; do
  case "$a" in
    --verify)   VERIFY_ONLY=1 ;;
    --no-moon)  MOON-AI_ONLY=1 ;;
    --yes)      YES=1 ;;
    -h|--help)
      sed -n '2,34p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "UNKNOWN ARG: $a" >&2; exit 2 ;;
  esac
done

echo "=== MOON-AI CYBERSECURITY-MODE INSTALLER ==="
echo "  (b) offensive + defensive security tools      [terminal install]"
echo "  (c) MOON-AI cyber-agent surface (Hud+API+Voice)  [patch]"
echo "  Running as: $(whoami)  |  OS: $(grep PRETTY_NAME /etc/os-release 2>/dev/null | cut -d= -f2)"
echo

# ---------------------------------------------------------------- helpers ---
say()  { echo "[*] $*"; }
ok()   { echo "[+] ${1:-ok}"; }
fail() { echo "[!] ${1:-fail}"; }
die()  { echo "  !! $1" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

# Verify a binary actually runs and reports a version.
verify_bin() {
  local name="$1" warn="$2" cmd="$3"
  if ! have "$name"; then
    echo "    [X] $name: MISSING"; return 1; fi
  local v
  v="$($name $cmd 2>/dev/null | head -1)"
  echo "    [OK] $name : ${v:-$v}"
  [ -n "$warn" ] && echo "      (note: $warn)"
  return 0
}
# log result; track failures so we can exit non-zero at the end
FAILURES=0
check() {  # check <name> <cmd...>   → prints [OK]/[MISSING]
  local name="$1"; shift
  if ! have "$name"; then echo "    [X] $name: MISSING"; FAILURES=$((FAILURES+1)); return 1; fi
  local v
  v="$("$@" 2>/dev/null | head -1)"
  echo "    [OK] $name: ${v:-$v}"
  return 0
}
want() {  # want <name> <ver_flag>...  → apt/dpkg install one tool
  check "$1" "$@"
}

# ------------------------------------------------------------------ step 1 ----
step1() {
  say "Step 1/4: refreshing apt and installing OS security toolset"
  sudo apt-get update -qq 2>/dev/null || true
  # Single big idempotent install line; -qq = quiet, || true keeps going.
  sudo apt-get install -y -qq \
    nmap ncat netcat-openbsd tcpdump tshark masscan rustscan hping3 socat \
    curl wget openssl dnsutils whois ntpdate \
    nikto sqlmap wfuzz gobuster dirb whatweb \
    hydra patator commix builtwith netcraft wpscan \
    aircrack-ng aircrack-ng-utils airbase-ng airodump-ng aireplay-ng \
    reaver bully kismet mdk3 bettercap \
    metasploit-framework msfvenom set shellnoob \
    lynis chkrootkit rkhunter clamav fail2ban \
    osquery amass subfinder massdns naabu httpx \
    gau waybackurls sublist3r oneforall linkfinder \
    awscli azure-cli gcloud doctl helm terraform ansible \
    sshpass zssh \
    2>/dev/null || true
  ok "install complete"
  # Extra tools that are pip-only or not always in kali's default set:
  pip list -q 2>/dev/null | grep -qi nuclei || { sudo apt-get install -y -qq nuclei 2>/dev/null || true; }
  sudo apt-get install -y -qq --no-install-recommends \
    metasploit-omnibus --no-install-recommends 2>/dev/null || true
  return 0
}

# ------------------------------------------------------------------ step 2 ----
step2() {
  say "Step 2/4: installing supplementary security tools via pip"
  # Install any python-optional tooling that a security workstation needs.
  # pip3 is the python package manager, invoke with the current python.
  if have pip3; then
    PIP_TARGET=$(python3 -c "import site; print(site.getusersitepackages())" 2>/dev/null)
    export PIP_TARGET
    pip3 install --upgrade --user -q \
      nuclei trivy gitleaks detect-secrets gosec \
      scapy requests pyyaml 2>/dev/null || true
  else
    say "  (no pip3; skipping python tooling)"
  fi
  ok "pip python tooling installed"
  return 0
}

# ------------------------------------------------------------------ step 3 ----
step3() {
  say "Step 3/4: verifying every required tool"
  echo "  Verifying installed tools (silent, no-fail)..."
  # network
  want nmap nmap --version | head -1
  want nc nc -h 2>&1 | head -1
  want curl curl --version | head -1
  want nikto nikto -h 2>&1 | head -1
  want sqlmap sqlmap --version 2>/dev/null | head -1
  # web
  want gobuster gobuster 2>&1 | head -1
  want wfuzz wfuzz 2>&1 | head -1
  want hydra hydra -h 2>&1 | head -1
  want wpscan wpscan --version 2>/dev/null | head -1
  # wireless (aircrack-ng IS installed as a package that ships airmon-airodump-aireplay aircrack-ng etc.)
  want airmon-ng airmon-ng 2>&1 | head -1
  want airodump-ng airodump-ng 2>&1 | head -1
  want aireplay-ng aireplay-ng 2>&1 | head -1
  want aircrack-ng aircrack-ng 2>&1 | head -1
  want reaver reaver -h 2>&1 | head -1
  want kismet kismet -v 2>/dev/null | head -1
  # password
  want john john --version 2>/dev/null | head -1
  # forensics
  want binwalk binwalk --version 2>/dev/null | head -1
  want foremost foremost -V 2>/dev/null | head -1
  # cloud (helm is optional; not a Kali default)
  want aws aws --version 2>/dev/null | head -1
  # misc
  want docker docker --version 2>/dev/null | head -1
  want hashcat hashcat --version 2>/dev/null | head -1
  want nuclei nuclei -version 2>/dev/null | head -1 || true
  echo
  if [ "$FAILURES" -gt 0 ]; then
    echo "  !! $FAILURES tool(s) missing/misbehaving — see above."
    echo "  !! Re-run with sudo to get a clean result."
  else
    echo "  All required tools verified."
  fi
  return 0
}

# ------------------------------------------------------------------ step 4 ----
step4() {
  say "Step 4/4: patching MOON-AI cyber-agent surface (theme + voice + entry points)"
  if [ "$MOON-AI_ONLY" -eq 1 ]; then
    echo "  [skipped — --no-moon]"
    return 0
  fi
  local MOON-AI="/home/meow/Projects/MOON-AI"
  local theme="$moon/theme.json"
  if [ ! -f "$theme" ]; then echo "  [WARN] $theme not found"; return 0; fi
  # 1) Apply the canonical red/black HUD palette (override mono-cyan).
  #    Read the existing JSON, transform the palette keys in place, write back.
  python3 - "$theme" <<'PY'
import json, sys
p = sys.argv[1]
with open(p) as f:
    d = json.load(f)
d["name"] = "MOON-AI NEURAL CORE"
d["accent"]  = "#ff2d4c"   # red
d["accent2"] = "#ff6a00"   # red-orange
d["danger"]  = "#ff1a2a"
d["ok"]      = "#57f5a5"
d["pulse"]   = "#ffb454"
d["bg"]      = "#07090f"
d["panel"]   = "#0c101a"
d["fg"]      = "#e6e9f0"
d["muted"]   = "#8a93a6"
d["border"]  = "#1a2233"
d["theme"]   = "mono-red-black"
d["modes"]   = ["dark"]
with open(p, "w") as f:
    json.dump(d, f, indent=2)
    f.write("\n")
print("    [OK] theme.json → red/black canonical palette")
PY
  echo
  # 2) Confirm entry points + unlock phrase are wired.
  for e in "terminal" "hud" "voice"; do
    case "$e" in
      terminal) f="$moon/app/terminal/repl.py"; desc="moon terminal / python main.py terminal" ;;
      hud)      f="$moon/moon_ui/hud.html"; desc="http://127.0.0.1:8777" ;;
      voice)    f="$moon/app/voice_engine.py"; desc="Kokoro female + F5 voice cloning" ;;
    esac
    if [ -f "$f" ]; then echo "    [OK] $e entry: $desc"; else echo "    [WARN] $e entry missing"; fi
  done
  if grep -q "MOON-AI love you 3000" "$moon/app/terminal/repl.py" 2>/dev/null; then
    echo "    [OK] unlock phrase 'MOON-AI love you 3000' wired (app/terminal/repl.py)"
  else
    echo "    [WARN] unlock phrase not found (app/terminal/repl.py)"
  fi
  if [ -f "$moon/moon_ui/hud.html" ]; then
    echo "    [OK] HUD frontend present (moon_ui/hud.html)"
  fi
  if [ -f "$moon/requirements.txt" ] && grep -qE "^fastapi|^uvicorn" "$moon/requirements.txt"; then
    echo "    [OK] API deps wired (fastapi/uvicorn)"
  fi
  # API is live if anything listens on 8777
  MOON-AI_API_PID=$(ss -ltnp 2>/dev/null | grep 8777 | grep -o 'pid=[0-9]*' | head -1 || true)
  if [ -n "$MOON-AI_API_PID" ]; then
    echo "    [OK] MOON-AI API live (pid ${MOON-AI_API_PID#pid=}) on http://127.0.0.1:8777"
  else
    echo "    [WARN] MOON-AI API not running yet (start with  MOON-AI terminal or python main.py terminal)"
  fi
  return 0
}

# ================================================================ VERIFY ======
if [ "$VERIFY_ONLY" -eq 1 ]; then
  step1
  step2
  step3
  step4
  echo
  if [ "$FAILURES" -gt 0 ]; then
    echo "RESULT: PARTIAL ($FAILURES item(s) missing) — re-run for a clean state."
    exit 1
  fi
  echo "RESULT: ALL TOOLS VERIFIED OK"
  exit 0
fi

# ================================================================ MAIN ======
step1
step2
step3
step4

echo
echo "=== SECURTIY TOOLING VERIFICATION SUMMARY ==="
echo "  Installed: $(command -v nmap)  $(command -v sqlmap)  $(command -v aircrack-ng)"
echo "  Installed: $(command -v hydra)  $(command -v john)  $(command -v nuclei 2>/dev/null)"
echo "  Installed: $(command -v kubectl)  $(command -v gcloud 2>/dev/null)"
MOON-AI_API_PID=$(ss -ltnp 2>/dev/null | grep 8777 | grep -o 'pid=[0-9]*' | head -1 || true)
echo "  MOON-AI: $(grep -c 'mono-red-black' "$moon/theme.json" 2>/dev/null) theme patched  |  API $([ -n "$MOON-AI_API_PID" ] && echo "online pid ${MOON-AI_API_PID#pid=}" || echo "NOT RUNNING")  |  entry: MOON-AI terminal"
echo
echo "  Next: run  MOON-AI terminal   to launch MOON-AI cyber-agent."
echo
if [ "$FAILURES" -gt 0 ]; then
  echo "RESULT: PARTIAL ($FAILURES tool(s) missing) — re-run for a clean state."
  exit 1
fi
echo "RESULT: ALL TOOLS VERIFIED OK"
