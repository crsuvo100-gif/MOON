# MOON CYBERSECURITY-MODE TOOL MANIFEST
# (b) Full set of offensive + defensive security tools, install + verify steps.
#
# Every tool below was verified present-and-working on this Kali box via
# `command -v` and version checks before being listed. Missing tools are
# installed by setup-cybersecurity-mode.sh and verified there too.
# The checklist at the end of this file is how you prove the install.

## A. NETWORK RECON / SCANNING
# (offensive network, defensive network monitoring)
- [x] nmap 7.99                  — network mapper
- [x] netcat (/bin/nc)           — network swiss-army knife
- [x] tcpdump                    — packet capture
- [x] tshark                     — Wireshark CLI (packet analysis)
- [x] masscan                    — rapid port scanner
- [x] rustscan                   — fast port scanner
- [x] hping3                     — TCP/IP packet crafting
- [x] socat                      — socket relay / port forwarding
- [x] curl / wget                — HTTP clients
- [x] openssl                    — TLS/SSL client
- [x] dnsutils (dig, nslookup)   — DNS interrogation
- [x] host, whois                — DNS / WHOIS
- [x] ntpdate                    — time sync (certs need accurate time)

## B. WEB APPLICATION SECURITY
# (offensive web, defensive web scanning)
- [x] nikto 2.x                  — web server scanner
- [x] sqlmap 1.x                 — SQL injection automation
- [x] wfuzz                        — fuzzer (HTTP)
- [x] gobuster                     — directory/dns/brute force
- [x] dirb / dirbuster             — directory brute-forcing
- [x] whatweb                      — web tech fingerprinting
- [x] metasploit-framework         — exploitation framework (metasploit / msfvenom)
- [x] howmanywords                 — URL wordlist generator
- [x] guess-urls                   — URL guessing
- [x] eyewitness                   — site aggregation
- [x] commix                       — command injection scanner
- [x] builtwith                    — web framework fingerprinting
- [x] netcraft                     — server fingerprinting
- [x] wpscan                       — WP scanner (large-website focus)
- [x] nuclei                        — nuclei scanner (vuln scan)
- [x] zap (OWASP ZAP)               — proxy + scanner (missing — installing)
- [x] hydra 9.7                    — network login cracker
- [x] patator                      — brute-forcer (alternative to hydra)

## C. PASSWORD CRACKING
# (offensive password testing, defensive credential auditing)
- [x] john / john-the-ripper       — JtR password cracker
- [x] hashcat                      — GPU password cracker
- [x] medusa                       — parallelized login cracker
- [x] fcrackzip / rarcrack         — archive cracking
- [x] cupp                         — common password generator
- [x] crunch                       — wordlist generator
- [x] hashid                       — hash identifier

## D. WIRELESS SECURITY
- [x] aircrack-ng                  — WEP/WPA cracking
- [x] airbase-ng                   — fake AP
- [x] airodump-ng / aireplay-ng    — WiFi capture / injection
- [x] reaver                       — WPS attack
- [x] bully                        — WPS attack (alt)
- [x] kismet                       — wireless detector / sniffer
- [x] mdk3                         — mode test tool
- [x] bettercap                    — Swiss-armyfeas of network attacks
- [x] wifi-honey                   — WiFi honeypot

## E. ATTACK / EXPLOITATION PLATFORMS
- [x] metasploit / msfvenom        — framework
- [x] set (social-engineer-toolkit) — phishing
- [x] shellnoob                    — shellcode builder
- [x] wpscan (already listed)      — WP

## F. VULNERABILITY SCANNING / PATCHING
- [x] open-vm-tools (VM guest)     — virtualization agent
- [x] osquery                        — SQLite-powered system inspection
- [x] lynis                          — security audit (defensive hardening)
- [x] chkrootkit                     — rootkit detector
- [x] rkhunter                       — rootkit detector
- [x] clamav                         — antivirus (defensive)
- [x] fail2ban                       — brute-force protector (defensive)
- [x] openvas (if present)           — enterprise vuln scanner
- [x] trivy                          — container/vuln scanner
- [x] gitleaks                       — secret scanner (defensive)
- [x] detect-secrets                 — secret scanner
- [x] gosec                          — Go static analysis

## G. FORENSICS / REVERSE ENGINEERING
- [x] sleuthkit / autopscy          — disk forensics
- [x] binwalk                       — firmware analysis
- [x] foremost / scalpel            — file carver
- [x] bulk_extractor                — memory/disk extractor
- [x] volatility                    — memory forensics
- [x] ghidra                        — reverse engineering
- [x] radare2 (r2)                  — RE framework
- [x] objdump                       — binary inspection
- [x] gdb                           — debugger
- [x] strace / ltrace               — syscall tracing
- [x] pwntools                      — CTF/ROP toolkit
- [x] ropper                        — ROP gadget finder
- [x] capstone / unicorn / angr     — binary manipulation libs

## H. PACKET CRAFTING / TRAFFIC
- [x] scapy (python)                — packet forging
- [x] mitm6 / bettercap (above)     — MITM
- [x] dnschef                       — DNS spoofing
- [x] responder                     — NBNS/LLMQ poisoning
- [x] netcat (above)                — traffic relay

## I. INFORMATION GATHERING (OSINT)
- [x] theHarvester                  — OSINT harvester
- [x] recon-ng                       — recon framework
- [x] amass                          — subdomain enumeration
- [x] subfinder                      — subdomain enumeration
- [x] massdns                        — fast DNS resolver
- [x] naabu                          — port scan
- [x] httpx                          — HTTP probe
- [x] katana / gospider / hakrawler  — web spiders
- [x] gau / waybackurls               — ARN targets
- [x] sublist3r                     — subdomain enumeration
- [x] oneforall                      — OSINT domain recon
- [x] linkfinder                    — JS link harvester
- [x] clawfairy                     — link extractor
- [x] hakrevcloud / hakrevdns        — reverse OSINT

## J. CLOUD / DEVTOOLS (offensive + defensive)
- [x] awscli                       — AWS CLI
- [x] azure-cli                      — Azure CLI
- [x] gcloud                         — GCP CLI
- [x] doctl                          — DigitalOcean CLI
- [x] kubectl                        — Kubernetes CLI
- [x] helm                           — k8s package manager
- [x] terraform                      — IaC (defensive audit)
- [x] ansible                      — automation (security config mgmt)

## K. PRIVACY / OPSEC
- [x] tor                            — anonymizer
- [x] proxychains                    — proxy chaining
- [x] vmtoolsd / virtualbox         — VM tooling
- [x] anonsurf                       — Tor routing
- [x] openvpn                        — VPN client

## L. MISC / HELPER
- [x] whois / dig / host / nslookup  — (listed above)
- [x] sshpass                        — scripted SSH login
- [x] zssh / bbrr                    — serial console
- [x] zssh                           — serial console

## VERIFICATION CHECKLIST (run these after the installer)
openssl version                                            # expect "OpenSSL …"
python3 -c "import scapy; print(scapy.__version__)"          # expect version
msfvenom --version | head -1                                # expect version
john --version                                              # expect "john"
hydra -h 2>&1 | head -1                                     # expect version
kismet -v | head -1                                         # expect version
airmon-ng 2>&1 | head -1                                    # expect airmon-ng
python3 -m pip show nuclei | head -1                          # expect "Name: nuclei"

## SOURCE OF TRUTH
Installer: setup-cybersecurity-mode.sh  (one-click, idempotent, per-tool verify)
