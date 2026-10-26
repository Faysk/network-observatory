"""Local MAC address enrichment. No network calls or device fingerprinting.

IEEE public assignment information identifies the *assignee of an address block*,
not the product model, owner, operating system or physical device. Locally
administered unicast MACs must NEVER be resolved against vendor OUIs.
"""
from __future__ import annotations

import re
import threading
from pathlib import Path

MAC_HEX = re.compile(r"^[0-9a-fA-F]{12}$")
ASSIGNMENT = re.compile(r"^[0-9A-F]+$")
PREFIX_LENGTHS = {24: 6, 28: 7, 36: 9}
MAX_REGISTRY_BYTES = 8 * 1024 * 1024
MAX_ENTRIES = 100_000
MAX_VENDOR_LENGTH = 160
DEFAULT_FILENAME = "oui-assignments.tsv"


def normalize_mac(value):
    """Return canonical colon-separated EUI-48, or None for malformed input.

    Accept common 12-hex, 00:11:22..., 00-11-22... and 0011.2233.4455.
    Do not mistake an EUI-64, arbitrary punctuation or Unicode digits for EUI-48.
    """
    if not isinstance(value, str):
        return None
    value = value.strip()
    if re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", value):
        hexdigits = value.replace(":", "")
    elif re.fullmatch(r"(?:[0-9a-fA-F]{2}-){5}[0-9a-fA-F]{2}", value):
        hexdigits = value.replace("-", "")
    elif re.fullmatch(r"(?:[0-9a-fA-F]{4}\.){2}[0-9a-fA-F]{4}", value):
        hexdigits = value.replace(".", "")
    elif MAC_HEX.fullmatch(value):
        hexdigits = value
    else:
        return None
    hexdigits = hexdigits.lower()
    return ":".join(hexdigits[i:i+2] for i in range(0, 12, 2))


def mac_address_type(value):
    """IEEE I/G (bit 0) and U/L (bit 1); U/L does not prove randomization."""
    normalized = normalize_mac(value)
    if normalized is None:
        return "unknown" if value is None or value == "" else "invalid"
    raw = bytes.fromhex(normalized.replace(":", ""))
    if raw == b"\x00" * 6 or raw == b"\xff" * 6:
        return "invalid"
    if raw[0] & 1:
        return "multicast"
    if raw[0] & 2:
        return "locally_administered"
    return "global"


class OuiRegistry:
    """Immutable-ish in-memory map; prefix keys are (24/28/36, uppercase hex).

    The supplied TSV is generated offline by tools/import_ieee_oui.py from the
    IEEE public registry. No eager filesystem access at import time.
    """

    def __init__(self, entries=None, version=None, path=None):
        self.entries = dict(entries or {})
        self.version = version
        self.path = path

    @classmethod
    def from_file(cls, path):
        path = Path(path)
        if not path.is_file():
            return cls(path=str(path))
        if path.stat().st_size > MAX_REGISTRY_BYTES:
            raise ValueError("OUI dataset exceeds safe runtime size")
        result = {}
        version = None
        with path.open("r", encoding="utf-8", newline="") as stream:
            for number, line in enumerate(stream, 1):
                if number > MAX_ENTRIES + 12:
                    raise ValueError("OUI dataset exceeds maximum entries")
                line = line.rstrip("\r\n")
                if line.startswith("# version="):
                    version = line[len("# version="):].strip()[:80]
                    continue
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) != 3:
                    raise ValueError("Malformed OUI dataset line")
                bits_text, prefix, vendor = parts
                if bits_text not in ("24", "28", "36"):
                    raise ValueError("Invalid OUI prefix length")
                bits = int(bits_text)
                if len(prefix) != PREFIX_LENGTHS[bits] or not ASSIGNMENT.fullmatch(prefix):
                    raise ValueError("Invalid OUI assignment")
                if not vendor.strip() or len(vendor) > MAX_VENDOR_LENGTH or any(
                    ord(char) < 32 for char in vendor
                ):
                    raise ValueError("Invalid OUI vendor")
                key = (bits, prefix)
                if key in result and result[key] != vendor:
                    raise ValueError("Conflicting assignee for same OUI prefix")
                result[key] = vendor
        return cls(result, version=version, path=str(path))

    def lookup(self, normalized):
        """Most specific match wins. Caller must reject locally administered MAC."""
        key = normalized.replace(":", "").upper()
        for bits in (36, 28, 24):
            vendor = self.entries.get((bits, key[:PREFIX_LENGTHS[bits]]))
            if vendor is not None:
                return vendor, bits
        return None, None


_registry_lock = threading.Lock()
_registry_cache_key = None
_registry_cache = None


def get_registry(directory):
    """Load once per path/mtime/size, using no persistent cache or disk writes."""
    global _registry_cache, _registry_cache_key
    filename = Path(directory) / DEFAULT_FILENAME
    try:
        stat = filename.stat()
        key = (str(filename), stat.st_mtime_ns, stat.st_size)
    except OSError:
        key = (str(filename), None, None)
    with _registry_lock:
        if _registry_cache_key == key and _registry_cache is not None:
            return _registry_cache
        try:
            registry = OuiRegistry.from_file(filename)
        except (OSError, UnicodeError, ValueError):
            # Dataset unavailable/corrupt: never invent a vendor.
            registry = OuiRegistry(path=str(filename))
        _registry_cache_key = key
        _registry_cache = registry
        return registry


def inspect_mac(value, *, registry=None):
    """JSON-compatible read-only envelope, preserving honest uncertainty."""
    normalized = normalize_mac(value)
    kind = mac_address_type(value)
    registry = registry if registry is not None else OuiRegistry()
    vendor = None
    prefix_bits = None
    sources = ["mac_bit_flags"] if normalized is not None else []
    if kind == "global" and registry.entries:
        vendor, prefix_bits = registry.lookup(normalized)
        if vendor is not None:
            sources.append("ieee_public_assignment")
    return {
        "normalized_mac": normalized,
        "mac_type": kind,
        "oui_vendor": vendor,
        "oui_prefix_bits": prefix_bits,
        "oui_dataset_version": registry.version,
        "sources": sources,
        "vendor_semantics": "registered_mac_block_assignee_not_device_model" if vendor else None,
    }
