"""Derive band evidence only from stations and radios in the same snapshot.

WLAN numbers name virtual interfaces, not frequency bands, physical radios or
antenna chains. This module never invents SSIDs or missing signal readings.
"""
import math
import re

INTERFACE = re.compile(r"^wlan(?:[1-9]|1[0-6])$")
BANDS = ("2.4GHz", "5GHz")


def station_links(stations, wifi):
    if not isinstance(stations, list):
        return []
    wifi = wifi if isinstance(wifi, dict) else {}
    result, seen = [], set()
    for station in stations[:128]:
        if not isinstance(station, dict):
            continue
        interface = station.get("interface")
        if not isinstance(interface, str) or not INTERFACE.fullmatch(interface) or interface in seen:
            continue
        seen.add(interface)
        meta = wifi.get(interface, {})
        meta = meta if isinstance(meta, dict) else {}
        band = meta.get("band") if meta.get("band") in BANDS else None
        channel = meta.get("channel")
        if type(channel) is not int or not 1 <= channel <= 233:
            channel = None
        result.append({"interface": interface, "band": band, "channel": channel})
    return result


def band_rssi(payload):
    """Sample mean by reported interface band; no traffic or radio noise."""
    wifi = payload.get("wifi")
    wifi = wifi if isinstance(wifi, dict) else {}
    stations = payload.get("stations")
    stations = stations if isinstance(stations, list) else []
    totals = {band: [] for band in BANDS}
    for station in stations[:128]:
        if not isinstance(station, dict):
            continue
        interface = station.get("interface")
        meta = wifi.get(interface, {}) if isinstance(interface, str) else {}
        band = meta.get("band") if isinstance(meta, dict) else None
        value = station.get("rssi_dbm")
        if band in totals and type(value) in (int, float) and math.isfinite(value) and -200 <= value <= 0:
            totals[band].append(value)
    return {
        "rssi_24_dbm": sum(totals["2.4GHz"]) / len(totals["2.4GHz"]) if totals["2.4GHz"] else None,
        "rssi_5_dbm": sum(totals["5GHz"]) / len(totals["5GHz"]) if totals["5GHz"] else None,
    }
