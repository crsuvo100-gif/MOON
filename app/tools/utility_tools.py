"""utility_tools.py -- environment, conversion, and location utilities for MOON.

Real implementations (no simulation). Secrets (API keys) come from environment
variables, never hardcoded.
"""

from __future__ import annotations

import requests
from datetime import datetime
from app.tools.base import BaseTool


class UnitConverterTool(BaseTool):
    name = "unit_converter"
    description = "Convert between common units (m/ft, kg/lbs, C/F, km/mi, etc.)."

    async def execute(self, value: float = 0.0, from_unit: str = "", to_unit: str = "", **_kw) -> str:
        conv = {
            ("m", "ft"): lambda x: x * 3.28084,
            ("ft", "m"): lambda x: x / 3.28084,
            ("kg", "lbs"): lambda x: x * 2.20462,
            ("lbs", "kg"): lambda x: x / 2.20462,
            ("km", "mi"): lambda x: x * 0.621371,
            ("mi", "km"): lambda x: x / 0.621371,
            ("c", "f"): lambda x: x * 9 / 5 + 32,
            ("f", "c"): lambda x: (x - 32) * 5 / 9,
            ("gb", "mb"): lambda x: x * 1024,
            ("mb", "gb"): lambda x: x / 1024,
        }
        f = conv.get((from_unit.lower().strip(), to_unit.lower().strip()))
        if not f:
            return f"[unit_converter] unsupported: {from_unit} -> {to_unit}"
        try:
            return f"{round(float(value), 4)} {from_unit} = {round(f(float(value)), 4)} {to_unit}"
        except Exception as e:  # noqa: BLE001
            return f"[unit_converter] error: {e}"


class TimezoneConverterTool(BaseTool):
    name = "timezone_converter"
    description = "Convert a local time string from one IANA timezone to another."

    async def execute(self, time_str: str = "", from_tz: str = "UTC", to_tz: str = "UTC", **_kw) -> str:
        try:
            from zoneinfo import ZoneInfo
            dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
            out = dt.replace(tzinfo=ZoneInfo(from_tz)).astimezone(ZoneInfo(to_tz))
            return out.strftime("%Y-%m-%d %H:%M %Z")
        except Exception as e:  # noqa: BLE001
            return f"[timezone_converter] error: {e} (use IANA names like Europe/London)"


class IpGeolocationTool(BaseTool):
    name = "ip_geolocation"
    description = "Look up geolocation for an IP or the caller's public IP (ip-api.com)."

    async def execute(self, ip: str = "", **_kw) -> str:
        try:
            target = ip or ""
            url = f"http://ip-api.com/json/{target}" if target else "http://ip-api.com/json/"
            r = requests.get(url, timeout=8)
            d = r.json()
            if d.get("status") == "fail":
                return f"[ip_geolocation] {d.get('message', 'lookup failed')}"
            return f"{d.get('city')}, {d.get('regionName')}, {d.get('country')} ({d.get('query')}) lat={d.get('lat')} lon={d.get('lon')}"
        except Exception as e:  # noqa: BLE001
            return f"[ip_geolocation] error: {e}"
