"""
AI-powered datasheet extraction using Gemini.

Sends datasheet text (first few pages) to Gemini and asks for structured
extraction of packages and pin assignments. Much more reliable than regex
for non-TI datasheets and unusual formats.

Uses urllib only (no pip dependencies). Gemini-only, no fallback.
"""

import json
import ssl
import urllib.request
import urllib.error
import logging

from ..core.models import PackageInfo, PinInfo

logger = logging.getLogger(__name__)


def _get_ssl_context():
    """Create an SSL context that works on macOS with bundled Python.

    macOS bundled Python (e.g. from KiCad, platformio) often lacks proper
    CA certificates. We try certifi first, then fall back to an unverified
    context rather than failing completely.
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    # Try the system default
    ctx = ssl.create_default_context()
    try:
        # Test if default context can load any certs
        ctx.load_default_certs()
        return ctx
    except Exception:
        pass
    # Last resort: unverified (still encrypted, just no cert validation)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

# Maximum text to send to the LLM
_MAX_TEXT_CHARS = 30000

_EXTRACTION_PROMPT = """You are an expert component datasheet parser for KiCad EDA. Extract structured information from this datasheet for part number "{part_number}".

TASK:
1. Find ALL available package options for "{part_number}" specifically
2. Extract pin assignments for the smallest/most common package variant

PACKAGE RULES:
- Normalize package names to standard KiCad format with pin count: "SOIC-8", "QFN-24", "PDIP-28", "TQFP-32", "SOT-23-5", "WSON-6", "HVSSOP-8", "LQFP-48", etc.
- NEVER use raw datasheet format like "D (SOIC, 8)" or "28-lead PDIP" - always normalize to "SOIC-8" or "PDIP-28"
- For package_code, use the manufacturer's letter code: "D", "P", "DBV", "DGN", etc.
- Look for the "Device Information", "Package Information", or "Ordering Information" table - this is the authoritative source for available packages
- If the datasheet covers multiple parts in a family (e.g. UC184x/284x/384x, ATmega48/88/168/328), ONLY return packages available for "{part_number}" specifically - match the exact part number or its wildcard group (e.g. UC384x covers UC3845)

PIN RULES:
- Use pin type from ONLY these values: input, output, bidirectional, power_in, power_out, passive, open_collector, open_emitter, no_connect
- IMPORTANT: If the package has a thermal/exposed pad, include it as an ADDITIONAL pin with name "EP" and type "power_in". The exposed pad is typically connected to GND.
- Only return pins for ONE package variant (the smallest pin count package)
- Use exact pin names from the datasheet (VCC, GND, PA0, etc.)
- CRITICAL: Every pin MUST have a unique pin number. No two pins may share the same number. Double-check the pin table if numbers seem duplicated.

Datasheet text:
{text}"""

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "packages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "pin_count": {"type": "integer"},
                    "package_code": {"type": "string"},
                    "dimensions": {"type": "string"},
                },
                "required": ["name", "pin_count"],
            },
        },
        "pins": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "number": {"type": "string"},
                    "name": {"type": "string"},
                    "type": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["number", "name"],
            },
        },
        "description": {"type": "string"},
    },
    "required": ["packages", "pins"],
}


def _call_gemini(api_key, model, prompt, schema=None):
    """Call Gemini API with structured JSON output."""
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "{model}:generateContent?key={key}".format(model=model, key=api_key)
    )
    gen_config = {"responseMimeType": "application/json"}
    if schema:
        gen_config["responseSchema"] = schema
    else:
        gen_config["responseSchema"] = _RESPONSE_SCHEMA
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": gen_config,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    ctx = _get_ssl_context()
    with urllib.request.urlopen(req, timeout=45, context=ctx) as resp:
        body = json.loads(resp.read())

    text = body["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


def _build_page_text(page_texts):
    """Build prioritised text from page_texts for LLM consumption.

    Prioritises first 2 pages and pages with pin tables.
    Returns combined text string, or "" if no pages.
    """
    priority_pages = []
    pin_pages = []
    other_pages = []

    for page_num, text in page_texts:
        text_upper = text.upper()
        if page_num <= 2:
            priority_pages.append((page_num, text))
        elif ("PIN" in text_upper and ("NAME" in text_upper or "FUNCTION" in text_upper or "DESCRIPTION" in text_upper)):
            pin_pages.append((page_num, text))
        else:
            other_pages.append((page_num, text))

    ordered = priority_pages + pin_pages + other_pages
    text_parts = []
    char_count = 0
    for page_num, text in ordered:
        if char_count + len(text) > _MAX_TEXT_CHARS:
            remaining = _MAX_TEXT_CHARS - char_count
            if remaining > 500:
                text_parts.append("--- Page {} ---\n{}".format(page_num, text[:remaining]))
            break
        text_parts.append("--- Page {} ---\n{}".format(page_num, text))
        char_count += len(text)

    return "\n\n".join(text_parts) if text_parts else ""


_PACKAGE_PIN_PROMPT = """You are an expert component datasheet parser for KiCad EDA. Extract pin assignments for part number "{part_number}" specifically for the "{package_name}" package ({pin_count} signal pins).

PIN RULES:
- Use pin type from ONLY these values: input, output, bidirectional, power_in, power_out, passive, open_collector, open_emitter, no_connect
- IMPORTANT: If the package has a thermal/exposed pad, include it as an ADDITIONAL pin beyond the {pin_count} signal pins, with name "EP" and type "power_in". The exposed pad is typically connected to GND.
- Use exact pin names from the datasheet (VCC, GND, PA0, etc.)
- CRITICAL: Every pin MUST have a unique pin number. No two pins may share the same number. Double-check the pin table if numbers seem duplicated.

Datasheet text:
{text}"""

_PIN_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "pins": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "number": {"type": "string"},
                    "name": {"type": "string"},
                    "type": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["number", "name"],
            },
        },
        "description": {"type": "string"},
    },
    "required": ["pins"],
}


def extract_with_gemini(part_number, page_texts, api_key, model,
                        status_callback=None):
    """Extract package and pin information using Gemini.

    Args:
        part_number: the component part number
        page_texts: list of (page_num, text) from parser
        api_key: the Gemini API key
        model: Gemini model ID string
        status_callback: optional fn(message) for progress updates

    Returns:
        (packages, pins, description) where:
        - packages: list of PackageInfo
        - pins: list of PinInfo
        - description: str
    """
    combined_text = _build_page_text(page_texts)
    if not combined_text:
        return ([], [], "")

    prompt = _EXTRACTION_PROMPT.format(
        part_number=part_number,
        text=combined_text,
    )

    if status_callback:
        status_callback("Extracting with Gemini...")

    result = _call_gemini(api_key, model, prompt)

    packages = []
    for pkg_data in result.get("packages", []):
        name = pkg_data.get("name", "")
        pin_count = pkg_data.get("pin_count", 0)
        if name and pin_count:
            packages.append(PackageInfo(
                name=name,
                pin_count=pin_count,
                ti_code=pkg_data.get("package_code", ""),
                dimensions=pkg_data.get("dimensions", ""),
            ))

    pins = _parse_pins(result.get("pins", []))
    description = result.get("description", "")

    return (packages, pins, description)


def extract_pins_for_package(part_number, page_texts, api_key, model,
                             package_name, pin_count, status_callback=None):
    """Re-query Gemini for pins specific to a chosen package.

    Args:
        part_number: the component part number
        page_texts: list of (page_num, text) from parser
        api_key: the Gemini API key
        model: Gemini model ID string
        package_name: e.g. "SOIC-8"
        pin_count: expected number of pins
        status_callback: optional fn(message) for progress updates

    Returns:
        list of PinInfo
    """
    combined_text = _build_page_text(page_texts)
    if not combined_text:
        return []

    prompt = _PACKAGE_PIN_PROMPT.format(
        part_number=part_number,
        package_name=package_name,
        pin_count=pin_count,
        text=combined_text,
    )

    if status_callback:
        status_callback("Extracting pins for {} with Gemini...".format(package_name))

    result = _call_gemini(api_key, model, prompt, schema=_PIN_RESPONSE_SCHEMA)
    return _parse_pins(result.get("pins", []))


_TYPE_MAP = {
    "input": "input",
    "output": "output",
    "bidirectional": "bidirectional",
    "power_in": "power_in",
    "power_out": "power_out",
    "passive": "passive",
    "open_collector": "open_collector",
    "open_emitter": "open_emitter",
    "no_connect": "no_connect",
}


def _sanitize_pin_name(name):
    """Clean up common pin name artifacts from PDF/Gemini extraction."""
    # Replace ± with - (common PDF mangling of inverting input names)
    name = name.replace("\u00b1", "-")
    # Replace Unicode minus (U+2212) with ASCII hyphen
    name = name.replace("\u2212", "-")
    # Replace en-dash with hyphen
    name = name.replace("\u2013", "-")
    # Strip leading/trailing whitespace
    return name.strip()


def _parse_pins(pin_data_list):
    """Parse raw pin dicts from Gemini into PinInfo objects.

    Deduplicates pin numbers: if two different-named pins share a number,
    the first occurrence wins. Same-name pins sharing a number are merged
    (legitimate multi-pad pins like GND).
    """
    pins = []
    seen_numbers = {}  # number -> index in pins list
    for pin_data in pin_data_list:
        number = str(pin_data.get("number", ""))
        name = _sanitize_pin_name(pin_data.get("name", ""))
        if number and name:
            pin_type = _TYPE_MAP.get(
                pin_data.get("type", "").lower().replace(" ", "_"),
                "passive",
            )
            if number in seen_numbers:
                existing = pins[seen_numbers[number]]
                if existing.name.upper() == name.upper():
                    # Same name, same number - legitimate duplicate (e.g. GND on multiple pads)
                    continue
                else:
                    # Different name, same number - Gemini error, skip the duplicate
                    logger.warning(
                        "Duplicate pin number %s: '%s' conflicts with '%s', keeping '%s'",
                        number, name, existing.name, existing.name,
                    )
                    continue
            seen_numbers[number] = len(pins)
            pins.append(PinInfo(
                number=number,
                name=name,
                pin_type=pin_type,
                description=pin_data.get("description", ""),
            ))
    return pins
