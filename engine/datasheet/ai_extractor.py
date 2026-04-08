"""
AI-powered datasheet extraction using LLM APIs.

Sends datasheet text (first few pages) to an LLM and asks for structured
extraction of packages and pin assignments. Much more reliable than regex
for non-TI datasheets and unusual formats.

Uses urllib only (no pip dependencies). Supports Gemini, OpenAI, Anthropic.
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
- Include thermal/exposed pads as a pin with name "EP" and type "passive"
- Only return pins for ONE package variant (the smallest pin count package)
- Use exact pin names from the datasheet (VCC, GND, PA0, etc.)

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


def _call_gemini(api_key, model, prompt):
    """Call Gemini API with structured JSON output."""
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "{model}:generateContent?key={key}".format(model=model, key=api_key)
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": _RESPONSE_SCHEMA,
        },
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


def _call_openai(api_key, model, prompt):
    """Call OpenAI API with JSON mode."""
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You extract structured data from datasheets. Always respond with valid JSON matching the requested schema."},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(api_key),
        },
        method="POST",
    )
    ctx = _get_ssl_context()
    with urllib.request.urlopen(req, timeout=45, context=ctx) as resp:
        body = json.loads(resp.read())

    text = body["choices"][0]["message"]["content"]
    return json.loads(text)


def _call_anthropic(api_key, model, prompt):
    """Call Anthropic API."""
    url = "https://api.anthropic.com/v1/messages"
    payload = {
        "model": model,
        "max_tokens": 4096,
        "messages": [
            {"role": "user", "content": prompt + "\n\nRespond with JSON only, no markdown fences."},
        ],
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    ctx = _get_ssl_context()
    with urllib.request.urlopen(req, timeout=45, context=ctx) as resp:
        body = json.loads(resp.read())

    text = body["content"][0]["text"]
    # Strip markdown fences if present
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
    return json.loads(text)


_PROVIDERS = {
    "gemini": _call_gemini,
    "openai": _call_openai,
    "anthropic": _call_anthropic,
}


def extract_with_ai(part_number, page_texts, provider, api_key, model,
                     status_callback=None):
    """Extract package and pin information using an LLM.

    Args:
        part_number: the component part number
        page_texts: list of (page_num, text) from parser
        provider: "gemini", "openai", or "anthropic"
        api_key: the API key
        model: model ID string
        status_callback: optional fn(message) for progress updates

    Returns:
        (packages, pins, description) where:
        - packages: list of PackageInfo
        - pins: list of PinInfo
        - description: str
        Returns ([], [], "") on failure.
    """
    if provider not in _PROVIDERS:
        logger.warning("Unknown AI provider: %s", provider)
        return ([], [], "")

    # Build text by selecting the most relevant pages:
    # 1. Always include first 2 pages (device info, package table, features)
    # 2. Include pages with pin tables (contain "PIN" + "NAME" or pin-like data)
    # 3. Fill remaining budget with subsequent pages
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

    if not text_parts:
        return ([], [], "")

    combined_text = "\n\n".join(text_parts)
    prompt = _EXTRACTION_PROMPT.format(
        part_number=part_number,
        text=combined_text,
    )

    if status_callback:
        status_callback("Extracting with AI ({})...".format(provider))

    try:
        call_fn = _PROVIDERS[provider]
        result = call_fn(api_key, model, prompt)
    except urllib.error.HTTPError as e:
        error_body = ""
        try:
            error_body = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        logger.error("AI API error %s: %s", e.code, error_body)
        if status_callback:
            if e.code == 401 or e.code == 403:
                status_callback("AI extraction failed: invalid API key")
            elif e.code == 429:
                status_callback("AI extraction failed: rate limited")
            else:
                status_callback("AI extraction failed: HTTP {}".format(e.code))
        return ([], [], "")
    except Exception as e:
        logger.error("AI extraction error: %s", e)
        if status_callback:
            status_callback("AI extraction failed: {}".format(str(e)[:100]))
        return ([], [], "")

    # Parse the structured response into our models
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

    pins = []
    for pin_data in result.get("pins", []):
        number = str(pin_data.get("number", ""))
        name = pin_data.get("name", "")
        if number and name:
            pin_type = _TYPE_MAP.get(
                pin_data.get("type", "").lower().replace(" ", "_"),
                "passive",
            )
            pins.append(PinInfo(
                number=number,
                name=name,
                pin_type=pin_type,
                description=pin_data.get("description", ""),
            ))

    description = result.get("description", "")

    return (packages, pins, description)
