#!/usr/bin/env python3
"""Layer 2: Real-time disaster watch (one-shot fetch skeleton)."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, List

import requests

EARTHQUAKE_LIST_URL = "https://www.jma.go.jp/bosai/quake/data/list.json"
TSUNAMI_LIST_URL = "https://www.jma.go.jp/bosai/tsunami/data/list.json"
WARNING_URL = "https://www.jma.go.jp/bosai/warning/data/warning/{area_code}.json"


def _fetch_json_sync(url: str, timeout: int = 10) -> Any:
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


async def fetch_earthquake_list() -> List[Dict[str, Any]]:
    data = await asyncio.to_thread(_fetch_json_sync, EARTHQUAKE_LIST_URL)
    return data if isinstance(data, list) else []


async def fetch_tsunami_list() -> List[Dict[str, Any]]:
    data = await asyncio.to_thread(_fetch_json_sync, TSUNAMI_LIST_URL)
    return data if isinstance(data, list) else []


async def fetch_warning(area_code: str) -> Dict[str, Any]:
    url = WARNING_URL.format(area_code=area_code)
    data = await asyncio.to_thread(_fetch_json_sync, url)
    return data if isinstance(data, dict) else {"raw": data}


def _parse_max_intensity(maxi: Any) -> int:
    if maxi is None:
        return 0
    text = str(maxi)
    m = re.search(r"(\d+)", text)
    if m:
        return int(m.group(1))

    # JMA shorthand fallback
    if "5" in text:
        return 5
    if "4" in text:
        return 4
    if "3" in text:
        return 3
    if "2" in text:
        return 2
    if "1" in text:
        return 1
    return 0


def analyze_earthquake_event(event: Dict[str, Any]) -> Dict[str, Any]:
    intensity = _parse_max_intensity(event.get("maxi"))
    if intensity >= 5:
        severity = 5
    elif intensity >= 4:
        severity = 4
    elif intensity >= 3:
        severity = 3
    elif intensity >= 2:
        severity = 2
    else:
        severity = 1

    return {
        "eid": event.get("eid") or event.get("id") or "",
        "occurred_at": event.get("at") or event.get("time") or "",
        "epicenter_name": event.get("anm") or event.get("name") or "",
        "magnitude": event.get("mag") or event.get("magnitude"),
        "max_intensity": event.get("maxi") or "",
        "severity": severity,
        "trigger_evacuation": severity >= 3,
    }


def analyze_tsunami_event(warning: Dict[str, Any]) -> Dict[str, Any]:
    text = (
        str(warning.get("ttl") or warning.get("title") or warning.get("headline") or "")
        + " "
        + str(warning.get("comment") or "")
    )

    if "大津波" in text:
        level = 3
        level_text = "大津波警報"
    elif "津波警報" in text:
        level = 2
        level_text = "津波警報"
    else:
        level = 1
        level_text = "津波注意報"

    return {
        "id": warning.get("eid") or warning.get("id") or "",
        "level": level,
        "level_text": level_text,
        "issued_at": warning.get("at") or warning.get("time") or "",
        "trigger_evacuation": True,
    }


async def _main() -> None:
    print("[Layer2] one-shot fetch test")

    try:
        eq = await fetch_earthquake_list()
        print(f"earthquake list: {len(eq)}件")
        if eq:
            latest = analyze_earthquake_event(eq[0])
            print("latest earthquake:", json.dumps(latest, ensure_ascii=False))
    except Exception:
        print("earthquake list: 接続失敗")

    try:
        tsu = await fetch_tsunami_list()
        print(f"tsunami list: {len(tsu)}件")
        if tsu:
            sample = analyze_tsunami_event(tsu[0])
            print("latest tsunami:", json.dumps(sample, ensure_ascii=False))
    except Exception:
        print("tsunami list: 接続失敗")

    try:
        warn = await fetch_warning("130000")
        header = warn.get("title") or warn.get("head") or warn.get("headline") or str(type(warn).__name__)
        print(f"warning(130000) header: {header}")
    except Exception:
        print("warning(130000): 接続失敗")


if __name__ == "__main__":
    asyncio.run(_main())
