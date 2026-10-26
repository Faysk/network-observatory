"""Conservative, deterministic category/platform suggestions from router observations.

No ML, lookup HTTP, port scanning, fingerprinting or per-device probes.
A hostname/type is a *hint*, not proof; vendors of MAC interface blocks must
not be treated as device models. Manual overrides are handled separately. Historical and vendor hints are not verified models.
"""
from __future__ import annotations

import re
import unicodedata

CLASSIFICATION_VERSION = "router-rules-v4"
CATEGORIES = frozenset((
    "smartphone", "tablet", "laptop", "desktop", "game_console", "smart_tv",
    "streaming_box", "printer", "camera", "robot_vacuum", "network_device",
    "iot", "computer", "android_device", "unknown",
))
PLATFORMS = frozenset(("android", "ios", "windows", "linux", "macos", "unknown"))
QUALITY = ("unknown", "low", "medium", "high")


def _normalize(text):
    if not isinstance(text, str):
        return ""
    # Bounded, Unicode-normalized matching; never emit raw labels inside evidence.
    return unicodedata.normalize("NFKC", text[:256]).casefold().strip()


# Rule name, regex, category, platform, strength.
# Strong means an explicit product family was named, NOT verified ownership/model.
# Names like 'wlan0', 'MSFT 5.0', LAN/Wi-Fi and OUI vendor alone are not categories.
RULES = tuple((
    name, re.compile(pattern), category, platform, strength
) for name, pattern, category, platform, strength in (
    ("playstation", r"(?:^|\W)(?:ps5|ps4|playstation(?:[-_ ]?[345])?)(?:$|\W)", "game_console", None, "strong"),
    ("xbox", r"(?:^|\W)xbox(?:[-_ ]?(?:one|series[-_ ]?[xs]|360))?(?:$|\W)", "game_console", None, "strong"),
    ("nintendo_switch", r"(?:^|\W)(?:nintendo[-_ ]?switch|switch[-_ ]?console)(?:$|\W)", "game_console", None, "strong"),
    ("iphone", r"(?:^|\W)iphone(?:[-_ ]?\d{1,2})?(?:$|\W)", "smartphone", "ios", "strong"),
    ("ipad", r"(?:^|\W)ipad(?:[-_ ]?(?:mini|pro|air|\d{1,2}))?(?:$|\W)", "tablet", "ios", "strong"),
    ("galaxy_tab", r"(?:^|\W)galaxy[-_ ]?tab(?:$|\W)", "tablet", "android", "strong"),
    ("redmi_pad", r"(?:^|\W)redmi[-_ ]?pad(?:$|\W)", "tablet", "android", "strong"),
    ("galaxy_s", r"(?:^|\W)(?:galaxy[-_ ]?)?s(?:2[0-9]|3[0-9])(?:[-_ ]?(?:ultra|plus|fe))?(?=$|[-_ ](?:de|do|da|phone|android)(?:$|[-_ ])|[-_ ]+$)", "smartphone", "android", "strong"),
    ("redmi_phone", r"(?:^|\W)redmi[-_ ]?(?:(?:note[-_ ]?)?[0-9]{1,2}[a-z]?|a[0-9]{1,2})(?:$|\W)", "smartphone", "android", "strong"),
    ("google_pixel", r"(?:^|\W)(?:google[-_ ]?)?pixel[-_ ]?[4-9](?:a|[-_ ]?pro)?(?:$|\W)", "smartphone", "android", "strong"),
    ("roomba", r"(?:^|\W)roomba(?:$|\W)", "robot_vacuum", None, "strong"),
    ("robot_vacuum", r"(?:^|\W)(?:roborock|ecovacs|deebot)(?:$|\W)", "robot_vacuum", None, "strong"),
    ("mi_tv", r"(?:^|\W)(?:mi[-_ ]?tv|xiaomi[-_ ]?tv)(?:$|\W)", "smart_tv", "android", "strong"),
    ("smart_tv", r"(?:^|\W)(?:smart[-_ ]?tv|bravia|android[-_ ]?tv)(?:$|\W)", "smart_tv", None, "strong"),
    ("streaming_box", r"(?:^|\W)(?:chromecast|fire[-_ ]?tv|apple[-_ ]?tv|roku)(?:$|\W)", "streaming_box", None, "strong"),
    ("printer", r"(?:^|\W)(?:printer|deskjet|laserjet|officejet)(?:$|\W)", "printer", None, "strong"),
    ("camera", r"(?:^|\W)(?:onvif[-_ ]?camera|ip[-_ ]?camera|reolink[-_ ]?camera)(?:$|\W)", "camera", None, "strong"),
    ("network_device", r"(?:^|\W)(?:wifi[-_ ]?repeater|access[-_ ]?point|network[-_ ]?switch)(?:$|\W)", "network_device", None, "strong"),
    ("iot_firmware", r"(?:^|\W)(?:esp32|esp8266|tasmota|sonoff|shelly)(?:$|\W)", "iot", None, "strong"),
    ("laptop_model", r"(?:^|\W)(?:macbook|thinkpad|ideapad|vivobook|zenbook)(?:$|\W)", "laptop", None, "strong"),
    ("desktop_model", r"(?:^|\W)(?:imac|optiplex|prodesk)(?:$|\W)", "desktop", None, "strong"),
    ("pc_suffix", r"(?:^|[-_ ])pc$", "desktop", None, "weak"),
))
# macbook is not automatically Windows; laptop_model rule adjusts platform below.
# A registered interface vendor is not a device-model or OS rule.

PLATFORM_TYPES = (
    ("android_dhcp", re.compile(r"^android[-_ ]?dhcp(?:[-_. ][\w.]+)?$"), "android", "medium"),
    ("windows_explicit", re.compile(r"(?:^|\W)windows(?:[-_ ]?(?:10|11))?(?:$|\W)"), "windows", "medium"),
    ("macos_explicit", re.compile(r"(?:^|\W)macos(?:$|\W)"), "macos", "medium"),
    ("linux_explicit", re.compile(r"(?:^|\W)linux(?:$|\W)"), "linux", "medium"),
    ("ios_explicit", re.compile(r"(?:^|\W)ios(?:$|\W)"), "ios", "medium"),
)


def _texts(client):
    for field in ("names", "device_types"):
        raw = client.get(field)
        if not isinstance(raw, (list, tuple)):
            continue
        for value in raw[:16]:
            text = _normalize(value)
            if text:
                yield field, text


def _classify_current(client, *, identity=None):
    """Return a JSON-safe inference with no raw name/MAC/IP duplicated in evidence."""
    if not isinstance(client, dict):
        client = {}
    identity = identity if isinstance(identity, dict) else {}
    evidence = []
    claims = []
    platform_claims = []
    seen = set()
    name_suggestion = None
    normalized_names = []
    msft_dhcp_reported = False
    android_dhcp_reported = False

    for field, value in _texts(client):
        if field == "names":
            normalized_names.append(value)
        # Neither raw MAC names nor interface labels are display-name suggestions.
        if field == "names" and name_suggestion is None and value not in ("wlan0", "wifi", "eth0", "unknown") and not re.fullmatch(r"[0-9a-f:.-]{12,17}", value):
            name_suggestion = next((name[:120] for name in client.get("names", []) if isinstance(name, str) and _normalize(name) == value), None)
        for rule, regex, category, platform, strength in RULES:
            if not regex.search(value):
                continue
            key = (field, rule)
            if key in seen:
                continue
            seen.add(key)
            # A laptop family may imply macOS for MacBook only. Other laptop
            # families do not establish OS. iMac has explicit platform below.
            if rule == "laptop_model":
                platform = "macos" if re.search(r"(?:^|\W)macbook(?:$|\W)", value) else None
            elif rule == "desktop_model" and re.search(r"(?:^|\W)imac(?:$|\W)", value):
                platform = "macos"
            evidence.append({"field": field, "rule": rule, "source": "huawei_http_report", "confidence": "medium" if strength == "strong" else "low"})
            claims.append((category, strength, field))
            if platform:
                platform_claims.append(platform)
        if field == "device_types" and "msft 5.0" in value:
            msft_dhcp_reported = True
        for rule, regex, platform, strength in PLATFORM_TYPES:
            if regex.search(value) and (field, rule) not in seen:
                seen.add((field, rule))
                evidence.append({"field": field, "rule": rule, "source": "huawei_http_report", "confidence": strength})
                platform_claims.append(platform)
                if rule == "android_dhcp" and field == "device_types":
                    android_dhcp_reported = True
        if "msft 5.0" in value and (field, "dhcp_msft_signature") not in seen:
            seen.add((field, "dhcp_msft_signature"))
            evidence.append({"field": field, "rule": "dhcp_msft_signature", "source": "huawei_http_report", "confidence": "low"})

    # Public OUI is only the assignee of the interface address block.
    if identity.get("oui_vendor") is not None and identity.get("mac_type") == "global":
        evidence.append({"field": "mac", "rule": "ieee_block_assignee", "source": identity.get("oui_source") or "ieee_public_assignment", "confidence": "low"})

    # Predator is a hardware family spanning laptops and desktops. The
    # hostname alone does not determine the form factor; require an explicitly
    # reported Microsoft DHCP signature OR a vendor-qualified product name.
    # The DHCP string by itself is never evidence of Windows or even a PC.
    predator = any(re.search(r"(?:^|[-_ ])predator(?:$|[-_ ])", name)
                   for name in normalized_names)
    vendor_qualified = any(re.search(r"(?:^|[-_ ])acer[-_ ]predator(?:$|[-_ ])", name)
                           for name in normalized_names)
    if predator and (msft_dhcp_reported or vendor_qualified):
        claims.append(("computer", "strong", "names"))
        evidence.append({"field": "names/device_types",
                         "rule": "predator_computer_family_with_context",
                         "source": "huawei_http_report", "confidence": "medium"})

    categories = set(category for category, _, _ in claims)
    platforms = set(platform_claims)
    conflicts = []
    if len(categories) > 1:
        conflicts.append("conflicting_device_category_hints")
    if len(platforms) > 1:
        conflicts.append("conflicting_platform_hints")

    if len(categories) == 1:
        category = next(iter(categories))
        if len(conflicts) and "conflicting_device_category_hints" in conflicts:
            category = "unknown"
        strong_fields = {field for _, strength, field in claims if strength == "strong"}
        confidence = ("high" if len(strong_fields) >= 2 else
                      "medium" if any(strength == "strong" for _, strength, _ in claims) else "low")
    else:
        category = "unknown"
        confidence = "unknown"

    if "conflicting_device_category_hints" in conflicts:
        category, confidence = "unknown", "unknown"
    elif "conflicting_platform_hints" in conflicts and confidence != "unknown":
        confidence = "low"  # conflicting OS hints reduce category certainty

    platform = next(iter(platforms)) if len(platforms) == 1 else "unknown"
    if platform not in PLATFORMS: platform = "unknown"

    # Android DHCP is genuine platform evidence, but Android powers phones,
    # tablets, TVs and embedded boxes. Use an intentionally broad category
    # only when there is no specific device-category evidence or conflict.
    if (category == "unknown" and not claims and not conflicts
            and platform == "android" and android_dhcp_reported):
        category = "android_device"
        confidence = "low"

    return {
        "category": category,
        "platform_family": platform,
        "display_name_suggestion": name_suggestion,
        "confidence": confidence,
        "evidence": evidence,
        "conflicts": conflicts,
        "classification_version": CLASSIFICATION_VERSION,
        "category_semantics": "heuristic_suggestion_not_verified_identity",
    }


def meaningful_name(value):
    return isinstance(value,str) and bool(value.strip()) and _normalize(value) not in ('wlan0','wifi','eth0','unknown','none','undefined','0','--') and not re.fullmatch(r'[0-9a-f:.-]{12,17}',_normalize(value))

def classify_client(client, *, identity=None, history=None):
    identity=identity if isinstance(identity,dict) else {};client=client if isinstance(client,dict) else {}
    result=_classify_current(client,identity=identity)
    name_values=client.get('names');type_values=client.get('device_types')
    names=[_normalize(v) for v in (name_values[:16] if isinstance(name_values,(list,tuple)) else []) if meaningful_name(v)]
    types=[_normalize(v) for v in (type_values[:16] if isinstance(type_values,(list,tuple)) else []) if isinstance(v,str)]
    vendor=_normalize(identity.get('oui_vendor'));global_mac=identity.get('mac_type')=='global'
    # Tuya is a provider of smart-home/IoT communication modules deployed in
    # many third-party products. Its registered OUI is a useful broad IoT hint,
    # not evidence of a plug, light, camera, model or ownership. Do not apply
    # to locally administered MACs or overwrite a more specific classification.
    if (not result['conflicts'] and result['category']=='unknown' and global_mac
            and vendor.rstrip('.') in ('tuya smart inc', 'tuya smart')):
        result.update(category='iot', confidence='low')
        result['evidence'].append({
            'field':'mac', 'rule':'tuya_iot_module_assignee_hint',
            'source':identity.get('oui_source') or 'ieee_public_assignment',
            'confidence':'low',
        })
    if not result['conflicts'] and result['category']=='unknown' and global_mac and vendor.startswith('nintendo'):
        result.update(category='game_console',confidence='low')
        result['evidence'].append({'field':'mac','rule':'nintendo_console_family_hint','source':identity.get('oui_source') or 'ieee_public_assignment','confidence':'low'})
    if not result['conflicts'] and result['category']=='unknown' and global_mac and vendor in ('intel corporate','intel corporation') and names and 'msft 5.0' in types:
        result.update(category='computer',confidence='low')
        result['evidence'].append({'field':'mac/device_types/names','rule':'intel_and_microsoft_dhcp_named_host','source':'combined_router_and_public_assignment','confidence':'low'})
    if result['category']=='android_device' and any(re.search(r'(?:^|[-_ ])s(?:[3-9]|1[0-9])(?:$|[-_ ])',name) for name in names):
        result.update(category='smartphone',confidence='medium')
        result['evidence'].append({'field':'names/device_types','rule':'legacy_galaxy_name_with_android_dhcp','source':'huawei_http_report','confidence':'medium'})
    if not names and result['category'] in ('unknown','android_device') and not result['conflicts']:
        candidates=[]
        for previous in (history or [])[:8]:
            hint=classify_client(previous,identity=identity)
            if hint['category'] not in ('unknown','android_device'):candidates.append((previous,hint))
        categories={hint['category'] for _,hint in candidates}
        if len(categories)==1:
            previous,hint=candidates[0]
            if result['platform_family'] not in ('unknown',hint['platform_family']) and hint['platform_family']!='unknown':
                result['conflicts'].append('historical_platform_conflict')
            else:
                result.update(category=hint['category'],confidence='low',platform_family=hint['platform_family'] if result['platform_family']=='unknown' else result['platform_family'],display_name_suggestion=hint['display_name_suggestion'],display_name_source='history',historical_observed_at=previous.get('observed_at'))
                result['evidence'].append({'field':'historical_names/device_types','rule':'last_known_category','source':'retained_router_observation','confidence':'low','observed_at':previous.get('observed_at')})
        elif len(categories)>1:result['conflicts'].append('conflicting_historical_categories')
    return result
