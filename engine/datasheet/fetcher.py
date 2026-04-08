"""
Datasheet fetcher: download datasheets from manufacturer websites.

Strategy:
1. Try manufacturer-specific URL patterns based on part number prefix
2. If that fails, try TI's /lit/gpn/ (works for any TI part regardless of prefix)
3. If that fails, try other manufacturer generic endpoints
4. All strategies produce candidate URLs that are tested with PDF header validation

No external dependencies — uses only urllib (stdlib).
"""

import os
import re
import hashlib
import urllib.request
import urllib.error
import urllib.parse
import ssl

from ..core.config import CACHE_DIR, strip_ti_suffix


# SSL context that doesn't verify (some manufacturer sites have cert issues)
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


def _cache_path(url):
    """Deterministic cache path for a URL."""
    h = hashlib.md5(url.encode()).hexdigest()[:12]
    name = url.split("/")[-1]
    if not name.endswith(".pdf"):
        name = h + ".pdf"
    else:
        name = h + "_" + name
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, name)


_MAX_PDF_SIZE = 50 * 1024 * 1024  # 50 MB limit


def _download(url, dest):
    """Download a URL to a local file. Returns True on success."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) schemagic/1.0",
        })
        with urllib.request.urlopen(req, context=_SSL_CTX, timeout=4) as resp:
            if resp.status != 200:
                return False
            # Read with size limit to prevent excessive memory usage
            data = resp.read(_MAX_PDF_SIZE + 1)
            if len(data) > _MAX_PDF_SIZE:
                return False
            if len(data) < 1000:  # too small to be a real PDF
                return False
            # Basic PDF header check
            if not data[:5].startswith(b"%PDF-"):
                return False
            with open(dest, "wb") as f:
                f.write(data)
            return True
    except (urllib.error.URLError, urllib.error.HTTPError, OSError,
            TimeoutError, ConnectionError):
        return False


def _try_urls(urls, status_callback=None):
    """Try a list of URLs, return (url, local_path) for the first that works."""
    for i, url in enumerate(urls):
        dest = _cache_path(url)
        if os.path.isfile(dest) and os.path.getsize(dest) > 1000:
            if status_callback:
                status_callback("Found cached datasheet")
            return url, dest
        if status_callback:
            # Show a short version of the URL
            domain = url.split("/")[2] if "/" in url else url
            status_callback("Trying {} ({}/{})...".format(domain, i + 1, len(urls)))
        if _download(url, dest):
            return url, dest
    return None, None


def _dedup(urls):
    """Deduplicate a list of URLs while preserving order."""
    seen = set()
    result = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            result.append(u)
    return result


# ---------------------------------------------------------------------------
# Manufacturer-specific fetchers
# ---------------------------------------------------------------------------

def _ti_urls(part_number):
    """Generate candidate TI URLs. /lit/gpn/ is the most reliable — it handles
    any TI part number including -Q1 automotive qualifiers and unusual prefixes.
    """
    full = part_number.lower().strip()
    base = strip_ti_suffix(part_number)[0].lower()
    # Also try stripping -Q1 style qualifiers (but keep full as primary)
    no_qual = re.sub(r"-q\d+$", "", full, flags=re.I)

    # Strip voltage suffixes: LP5907MFX-1.2 → LP5907MFX, LM2596S-12 → LM2596S
    no_volt = re.sub(r"-\d+\.?\d*$", "", full)
    # Strip package+voltage: LP5907MFX-1.2 → LP5907
    no_pkg_volt = strip_ti_suffix(no_volt.upper())[0].lower() if no_volt != full else base
    # Further strip: remove trailing letter variants (S, A, B, AI) for base family
    # e.g., LM2596S → LM2596, INA226AI → INA226
    family = re.sub(r"[a-z]{1,2}$", "", no_pkg_volt) if no_pkg_volt != full else ""
    # Also try stripping from the base (package-stripped) name
    family2 = re.sub(r"[a-z]{1,2}$", "", base) if base != full else ""

    urls = [
        # /lit/gpn/ is TI's universal resolver — try it first
        f"https://www.ti.com/lit/gpn/{full}",
        f"https://www.ti.com/lit/ds/symlink/{full}.pdf",
    ]

    # Build candidate list (most specific to least)
    candidates = []
    if no_qual != full:
        candidates.append(no_qual)
    if base != full:
        candidates.append(base)
    if no_volt != full:
        candidates.append(no_volt)
    if no_pkg_volt != full and no_pkg_volt != base:
        candidates.append(no_pkg_volt)
    if family and family != no_pkg_volt and len(family) >= 5:
        candidates.append(family)
    if family2 and family2 != base and family2 not in candidates and len(family2) >= 5:
        candidates.append(family2)

    # Deduplicate preserving order
    seen = {full}
    for c in candidates:
        if c not in seen:
            seen.add(c)
            urls.append(f"https://www.ti.com/lit/gpn/{c}")
            urls.append(f"https://www.ti.com/lit/ds/symlink/{c}.pdf")

    return _dedup(urls)


def _strip_adi_suffix(part_number):
    """Strip ADI/Linear/Maxim package and ordering suffixes.

    ADI suffixes: -R7, -RL, -R2 (reel), -EP, -KGD, ARDZ, etc.
    Linear Tech: CS8, EGN, IS8, MPBF, etc.
    Maxim: G+, G+T, X+, X+T10, etc.

    Returns list of candidate base part numbers (most specific first).
    """
    pn = part_number.strip().upper()
    candidates = [pn]

    # Maxim: strip package + reel suffixes (G+T, X+T10, G+, etc.)
    # G=TDFN, X=WLP, E=bumped die — these are package codes, not part of base
    m = re.match(r"^(MAX\d+\w*?)([GXEUW]\+(?:T\d*)?|\+T?\d*)$", pn)
    if m:
        candidates.append(m.group(1))
        # Also try without trailing digits (e.g., MAX17049 from MAX17049G+T)
        base = m.group(1)
        if re.match(r"^MAX\d+$", base):
            candidates.append(base)

    # ADI proper: strip package codes (ARDZ, ACPZ, ARMZ, etc.)
    # Common ADI package suffixes: ARZ, ARDZ, ACPZ, ARMZ, ARUZ, AKSZ, BCPZ, etc.
    m = re.match(r"^((?:AD|ADP|ADM|ADG|ADL|ADA|ADR|ADN|ADUM)\w*?)([A-Z]{2,4}Z(?:-\d+\.?\d*)?)$", pn)
    if m and len(m.group(1)) >= 4:
        candidates.append(m.group(1))

    # Linear Tech: strip package + temp codes (CS8, EGN, IS8, etc.)
    m = re.match(r"^(LT[CM]?\d{3,5}\w?)(?:[CEI][A-Z]?\d?|M[PS]?(?:BF)?|(?:EGN|MPBF|EMSE|HMS)).*$", pn)
    if m:
        candidates.append(m.group(1))

    # Generic: strip trailing -X.X (voltage suffix for fixed output parts)
    m = re.match(r"^(.+?)-(\d+\.?\d*)$", pn)
    if m:
        candidates.append(m.group(1))

    # Deduplicate preserving order
    seen = set()
    result = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result


def _adi_urls(part_number):
    """Generate candidate Analog Devices URLs.

    ADI URL naming is complex:
    - ADI proper: lowercase base part (e.g., adp2302.pdf, ad8605.pdf)
    - Combined datasheets with underscores: adp2302_2303.pdf, ad8605_8606_8608.pdf
    - Linear Tech: numeric code + revision suffix (e.g., 1763fh.pdf, 3780fc.pdf)
    - Maxim: lowercase with dashes (e.g., max17048-max17049.pdf)

    Since ADI's naming is unpredictable, this generates a few likely candidates
    and relies on the web search fallback for the rest.
    """
    pn = part_number.strip()
    candidates = _strip_adi_suffix(pn)
    base = "https://www.analog.com/media/en/technical-documentation/data-sheets"

    urls = []
    for c in candidates:
        c_lower = c.lower()
        c_upper = c.upper()
        urls.append(f"{base}/{c_lower}.pdf")
        urls.append(f"{base}/{c_upper}.pdf")

        # Linear Tech numeric pattern: LT1763 → try 1763fb.pdf, 1763fh.pdf, etc.
        m = re.match(r"^LT[CM]?(\d{3,5}\w?)$", c.upper())
        if m:
            num = m.group(1).lower()
            for suffix in ["fb", "fc", "fd", "fe", "ff", "fh"]:
                urls.append(f"{base}/{num}{suffix}.pdf")

        # Maxim: MAX17048 → max17048.pdf
        if c_upper.startswith("MAX"):
            urls.append(f"{base}/{c_lower}.pdf")

    return _dedup(urls)


def _microchip_urls(part_number):
    """Generate candidate Microchip URLs."""
    pn = part_number.upper().replace("-", "")
    full = part_number.upper().strip()
    # Try the two most common Microchip URL patterns; web search handles the rest
    urls = [
        f"https://ww1.microchip.com/downloads/en/DeviceDoc/{pn}.pdf",
        f"https://ww1.microchip.com/downloads/en/DeviceDoc/{full}.pdf",
    ]
    return _dedup(urls)


def _onsemi_urls(part_number):
    """Generate candidate ON Semiconductor URLs."""
    pn = part_number.upper().replace("-", "")
    urls = [
        f"https://www.onsemi.com/download/data-sheet/pdf/{pn}-D.PDF",
    ]
    return urls


def _stm_urls(part_number):
    """Generate candidate STMicroelectronics URLs."""
    pn = part_number.strip()
    urls = [
        f"https://www.st.com/resource/en/datasheet/{pn.lower()}.pdf",
    ]
    return urls


# ---------------------------------------------------------------------------
# Manufacturer detection
# ---------------------------------------------------------------------------

# Patterns are checked in order. Each entry: (regex, manufacturer_name, url_fn)
# The regex should match known prefixes for that manufacturer.
_MFR_PATTERNS = [
    # TI — extensive prefix list covering major product families
    (r"^(TPS|TLV|LM[0-9R]|OPA|INA|ADS|BQ[0-9]|SN[0-9]|SN74|TCA|TXS|"
     r"CD[0-9]|DRV|UCC|MC[0-9]|LP[0-9]|LMR|TLC|REF[0-9]|DAC[0-9]|"
     r"MSP|TMS|ISO[0-9]|AMC|TMP[0-9]|TMUX|TCAN|CSD|TPA|THVD|TPL|PCM|"
     r"LMH|LMG|THS|OPT|HDC|ADS1|ADS8|TXB|SN65|TAS|LMK|TI[0-9]|"
     r"TLIN|TIOL|BUF|IWR|AWR|LDC|DCP|TLK|DP[0-9]|XTR|DAC[0-9])",
     "TI", _ti_urls),

    # Analog Devices (includes Linear Technology and Maxim acquisitions)
    (r"^(AD[0-9GPMS]|ADP|ADM|ADG|ADL|ADA|ADR|ADN|ADUM|"
     r"LT[0-9C]|LTC|LTM|LTP|"
     r"MAX[0-9]|HMC|ADXL|ADIS|SSM|ADV)",
     "Analog Devices", _adi_urls),

    # Microchip (includes Atmel acquisition)
    (r"^(MCP|PIC|dsPIC|ATSAMD|AT[0-9MTSX]|ATSAM|MIC[0-9]|"
     r"SST|EQCO|PAC[0-9]|EMC[0-9]|MTA|KSZ)",
     "Microchip", _microchip_urls),

    # ON Semiconductor (now onsemi)
    (r"^(NCV|NCP|FAN[0-9]|NB[0-9]|NCS|NIS|NJM|NSR|NVMFS|FDP|NUD|"
     r"FUSB|NLU|CAT|NTB|FPF|ACS)",
     "ON Semiconductor", _onsemi_urls),

    # STMicroelectronics
    (r"^(STM|ST[A-Z][0-9]|L[0-9]{3}|TS[0-9]{3}|VL[0-9]|LSM|LIS|"
     r"STPS|STW|STD|STP[A-Z0-9]|VIPER|PM[0-9]|STSPIN|VN[HQ0-9]|L298)",
     "STMicroelectronics", _stm_urls),

    # Allegro Microsystems
    (r"^(A[0-9]{3,4}|ACS[0-9]|ALS[0-9]|ARG[0-9])",
     "Allegro", lambda pn: []),  # relies on web search

    # InvenSense / TDK
    (r"^(MPU|ICM|ICS|IAM)",
     "InvenSense", lambda pn: []),  # relies on web search

    # NXP
    (r"^(TJA|TJF|TEA|S32|MK[A-Z0-9]|PCF|PCA|SAA)",
     "NXP", lambda pn: [
         "https://www.nxp.com/docs/en/data-sheet/{}.pdf".format(pn.upper()),
         "https://www.nxp.com/docs/en/data-sheet/{}.pdf".format(pn.upper().replace("-", "")),
     ]),
]


def guess_manufacturer(part_number):
    """Guess the manufacturer from the part number prefix."""
    pn = part_number.upper().strip()
    for pattern, mfr, _ in _MFR_PATTERNS:
        if re.match(pattern, pn, re.I):
            return mfr
    return ""


def _search_datasheet_urls(part_number):
    """Search the web for datasheet PDF URLs using DuckDuckGo.

    Returns a list of candidate PDF URLs found in search results, prioritized
    by manufacturer domains. Falls back gracefully if search is unavailable.
    """
    try:
        query = f"{part_number} datasheet pdf"
        search_url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode(
            {"q": query}
        )
        req = urllib.request.Request(search_url, headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        })
        with urllib.request.urlopen(req, context=_SSL_CTX, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # DDG wraps result URLs in uddg= parameters
        raw = re.findall(r"uddg=([^&\"]+)", html)
        decoded = [urllib.parse.unquote(u) for u in raw]

        # Deduplicate preserving order
        seen = set()
        unique = []
        for u in decoded:
            if u not in seen:
                seen.add(u)
                unique.append(u)

        # Split into direct PDF links and manufacturer product pages
        pdf_urls = [u for u in unique if ".pdf" in u.lower()]

        # From product pages, derive likely PDF URLs
        # TI product pages → /lit/gpn/ URL
        for u in unique:
            m = re.match(r"https?://www\.ti\.com/product/([A-Za-z0-9_-]+)", u)
            if m:
                pn_from_url = m.group(1).lower()
                pdf_urls.append(f"https://www.ti.com/lit/gpn/{pn_from_url}")

        # Prioritize manufacturer domains over third-party sites
        mfr_domains = [
            "ti.com", "analog.com", "microchip.com", "onsemi.com",
            "st.com", "nxp.com", "infineon.com", "renesas.com",
            "diodes.com", "rohm.com", "allegromicro.com",
            "invensense.com", "tdk.com", "bosch-sensortec.com",
            "espressif.com", "raspberrypi.com", "wch-ic.com", "wch.cn",
            "ftdichip.com", "maxlinear.com", "vishay.com",
            "mouser.com", "digikey.com", "arrow.com",
        ]
        # Datasheet aggregator domains (better than random sites but worse than manufacturers)
        aggregator_domains = [
            "alldatasheet.com", "datasheet4u.com", "datasheets.com",
            "mouser.com", "digikey.com", "arrow.com", "lcsc.com",
        ]
        # Reject known non-datasheet domains (module guides, tutorials, etc.)
        reject_domains = [
            "handsontec.com", "instructables.com", "arduino.cc",
            "adafruit.com/product", "sparkfun.com/product",
            "youtube.com", "github.com", "hackaday.com",
        ]

        mfr_pdfs = []
        aggregator_pdfs = []
        other_pdfs = []
        for u in pdf_urls:
            u_lower = u.lower()
            # Skip non-datasheet sources
            if any(d in u_lower for d in reject_domains):
                continue
            if any(d in u_lower for d in mfr_domains):
                mfr_pdfs.append(u)
            elif any(d in u_lower for d in aggregator_domains):
                aggregator_pdfs.append(u)
            else:
                other_pdfs.append(u)

        return _dedup(mfr_pdfs + aggregator_pdfs + other_pdfs)

    except (urllib.error.URLError, urllib.error.HTTPError, OSError,
            TimeoutError, ConnectionError, ValueError):
        return []


# Known manufacturer domains for guessing manufacturer from search result URLs
_DOMAIN_TO_MFR = {
    "ti.com": "TI",
    "analog.com": "Analog Devices",
    "microchip.com": "Microchip",
    "onsemi.com": "ON Semiconductor",
    "st.com": "STMicroelectronics",
    "nxp.com": "NXP",
    "infineon.com": "Infineon",
    "renesas.com": "Renesas",
    "diodes.com": "Diodes Inc",
    "rohm.com": "ROHM",
    "allegromicro.com": "Allegro",
    "invensense.tdk.com": "InvenSense",
    "tdk.com": "TDK",
    "bosch-sensortec.com": "Bosch",
    "espressif.com": "Espressif",
    "wch-ic.com": "WCH",
    "ftdichip.com": "FTDI",
    "vishay.com": "Vishay",
}


def _mfr_from_url(url):
    """Guess manufacturer from a URL's domain."""
    for domain, mfr in _DOMAIN_TO_MFR.items():
        if domain in url.lower():
            return mfr
    return ""


def fetch_datasheet(part_number, status_callback=None):
    """Fetch a datasheet PDF for the given part number.

    Strategy:
    1. If the part matches a known manufacturer prefix, try that manufacturer's
       URL patterns first (fastest — no network search needed).
    2. If step 1 fails, try TI's /lit/gpn/ as a universal catch-all (TI has the
       largest catalog and /lit/gpn/ 404s fast for non-TI parts).
    3. If still no match, search the web for "{part} datasheet pdf" and try
       the PDF URLs found in results. This handles any manufacturer, any part,
       even parts released after this code was written.

    Returns (url, local_path, manufacturer) or (None, None, manufacturer).
    """
    pn = part_number.strip()
    pn_upper = pn.upper()

    def _cb(msg):
        if status_callback:
            status_callback(msg)

    # Step 0: Check if any cached PDF matches this part number by filename.
    # The URL-hash-based cache may miss when the same PDF was fetched via a
    # different URL (e.g. DuckDuckGo vs manufacturer direct).
    base_pn = strip_ti_suffix(pn)[0] if strip_ti_suffix(pn)[0] else pn
    _search_keys = []
    for candidate in [base_pn, pn]:
        clean = candidate.lower().replace("-", "").replace("/", "")
        if clean not in _search_keys:
            _search_keys.append(clean)
    # Add shorter prefixes, but not too short to avoid false matches
    # (e.g. "lm35" from "lm358" matching the wrong PDF)
    # Minimum key = 80% of base PN length to avoid false substring matches
    min_key_len = max(5, int(len(_search_keys[0]) * 0.8)) if _search_keys else 5
    for key in list(_search_keys):
        for length in range(len(key) - 1, min_key_len - 1, -1):
            shorter = key[:length]
            if shorter not in _search_keys:
                _search_keys.append(shorter)
    if os.path.isdir(CACHE_DIR):
        cache_files = [f for f in os.listdir(CACHE_DIR) if f.endswith(".pdf")]
        for search_key in _search_keys:
            if len(search_key) < 4:
                break
            for fname in cache_files:
                fname_core = fname.lower().replace("-", "").replace("_", "")
                if search_key in fname_core:
                    cached = os.path.join(CACHE_DIR, fname)
                    if os.path.getsize(cached) > 1000:
                        _cb("Found cached datasheet (by part number)")
                        return "cached://" + fname, cached, ""

    # Step 1: Try the matched manufacturer first
    matched_mfr = ""
    for pattern, mfr, url_fn in _MFR_PATTERNS:
        if re.match(pattern, pn_upper, re.I):
            matched_mfr = mfr
            _cb("Checking {} URLs...".format(mfr))
            urls = url_fn(pn)
            url, path = _try_urls(urls, status_callback)
            if url:
                _cb("Downloaded datasheet from {}".format(mfr))
                return url, path, mfr
            break  # matched but failed — continue to fallbacks

    # Step 2: Try TI as universal fallback (only if manufacturer is unknown —
    # skip this for known non-TI parts since TI /lit/gpn/ won't help)
    if not matched_mfr:
        _cb("Trying TI universal lookup...")
        ti_urls = _ti_urls(pn)
        url, path = _try_urls(ti_urls, status_callback)
        if url:
            _cb("Downloaded datasheet from TI")
            return url, path, "TI"

    # Step 3: Web search fallback — works for any manufacturer
    _cb("Searching web for datasheet...")
    search_urls = _search_datasheet_urls(pn)
    if search_urls:
        _cb("Found {} candidate URLs, downloading...".format(len(search_urls)))
        url, path = _try_urls(search_urls, status_callback)
        if url:
            mfr = _mfr_from_url(url) or matched_mfr
            _cb("Downloaded datasheet" + (" from {}".format(mfr) if mfr else ""))
            return url, path, mfr

    return None, None, matched_mfr
