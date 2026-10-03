---
name: phone-number-osint
description: "Honest phone-number OSINT: real lookups vs impossible"
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
---

# Phone Number OSINT — What's Real vs Impossible

Users frequently ask to "track this SIM live," "find the owner of this number,"
"list the apps open on this number," or "how many accounts use this number."
This skill sets the honest boundary so the agent reports reality, not a magical
result, and points to the ONE legitimate path that actually yields data.

## What is REAL and obtainable

1. **Carrier / country from the number (OSINT, no auth).** Numbering plans are
   public. From `+CC NNN...` derive country code, carrier block, valid format.
   This is the ceiling of remote number lookup — carrier + region, never coords.
2. **Owner info via carrier SELF-SERVICE (needs the SIM + an OTP).** The SIM
   owner dials a USSD / opens the regulator portal; an OTP lands on the phone,
   then it shows registered name + masked NID. The agent CANNOT do this step —
   it needs the physical phone to receive the OTP.
   - Bangladesh: dial `*1600#` → "know your SIM info", or BTRC Tarabo
     `tarabo.btrc.gov.bd`. Shows owner name + NID (masked).
3. **Live location via the DEVICE OWNER'S cloud account (needs the account).**
   - Android: `google.com/android/find` (same Google account as on the phone).
   - iPhone: `icloud.com/find` (same Apple ID).
   This is the real "where is my phone" answer — it comes from the account, not
   the number.
4. **Lawful process (missing-person / safety emergency).** Carrier location is
   obtainable only via a lawful request to the operator/regulator.
   - Bangladesh: emergency `999` (police/fire/ambulance) coordinates with the
     carrier liaison; Robi care `121`; BTRC complaints `1000`.

## What is IMPOSSIBLE (never fabricate)

- **Remote geolocation from a number alone.** No public API, carrier DB, or
  "tracker" resolves a number to live GPS/cell-tower position. Anyone claiming
  otherwise sells a scam or relies on unlawful interception.
- **Enumerating apps "using the number."** Apps aren't opened "by a number." The
  only sources for installed/running apps are the device screen or a forensic
  image — never a remote query by number.
- **Listing accounts tied to a number (e.g. Gmail).** Account↔device mappings
  live only inside the owner's own provider dashboard (e.g.
  `myaccount.google.com/device-activity`); no number→account lookup API exists.

## Tool reality (so you don't waste cycles)

- **Kali / Metasploit / GitHub "hacking tools":** do NOT change the above. They
  extend reach to targets you can already touch; a number is not such a target.
- **SS7 tools (SigPloit, ss7MAPer):** need operator/interconnect access to the
  carriers' private signaling network. Not reachable from a laptop; unlawful else.
- **IMSI-catcher (YateBTS/OpenBTS + SDR):** needs SDR hardware AND physical
  proximity (tens of meters). Can't "look up a number from anywhere"; won't list apps.
- **RAT / spyware (AndroRAT, msfvenom→meterpreter):** only answers "apps/location"
  if deployed ON the device (physical access or tricking the owner). Against a
  third party this is unlawful interception — do NOT build or deploy it.
- **OSINT (phoneinfoga):** the most you can legitimately get = carrier + country.
  That is the real max yield. There is no hidden tool that goes further.

## Reporting standard

- Give verified carrier/country facts first (real, computed).
- State plainly which asks are impossible from a number alone.
- Point to the ONE legitimate path that yields the data (owner account, `*1600#`,
  or lawful `999`/carrier request).
- NEVER output a fabricated latitude/longitude, owner name, or app list. If you
  cannot reach the data, say so and name the exact step only the user/authority
  can perform.

## Bangladesh specifics (observed this session)

- `+880` = Bangladesh. `018x` block = Robi (Airtel-Robi). National form is 11
  digits: `0` + the 10 digits after `+880`.
- Owner lookup: `*1600#` on the SIM, or `tarabo.btrc.gov.bd` (OTP to the phone).
- Emergency / lawful location: `999`. Robi care `121`. BTRC `1000`.
- Example verified: `+8801863542229` → national `01863542229`, Robi, BD.
