"""
Datasheet PDF parser using pdfplumber.

Extracts text and tables from datasheet PDFs for pin and package identification.
"""

import re


def extract_tables_and_text(pdf_path):
    """Extract all tables and text from a PDF file.

    Returns (tables, full_text, page_texts) where:
    - tables: list of (page_num, table) where table is list of rows (list of cells)
    - full_text: concatenated text from all pages
    - page_texts: list of (page_num, text)
    """
    import pdfplumber

    tables = []
    page_texts = []
    full_text_parts = []

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            # Extract text
            text = page.extract_text() or ""
            page_texts.append((i + 1, text))
            full_text_parts.append(text)

            # Extract tables
            page_tables = page.extract_tables() or []
            for table in page_tables:
                if table and len(table) > 1:  # need header + at least one row
                    tables.append((i + 1, table))

    return tables, "\n".join(full_text_parts), page_texts


def find_description(full_text, part_number):
    """Extract a short description from the datasheet text."""
    pn = part_number.upper()

    # Skip lines that look like ordering/packaging info or website navigation
    skip_keywords = {"active", "production", "t&r", "reel", "tube", "tray",
                     "qty", "package", "orderable", "addendum", "large",
                     "3000", "2500", "1000", "tape",
                     "tools & support", "order", "technical", "reference design",
                     "copyright", "document", "revision"}

    # Look for the title / first line that contains the part number
    for line in full_text.split("\n"):
        line = line.strip()
        if pn in line.upper() and 20 < len(line) < 200:
            lower = line.lower()
            if any(kw in lower for kw in skip_keywords):
                continue
            return line

    # Fallback: first substantial line
    for line in full_text.split("\n")[:30]:
        line = line.strip()
        if len(line) > 30 and not line.startswith("www.") and not line.startswith("http"):
            return line[:200]

    return ""


def find_component_type(full_text):
    """Guess the component type from datasheet text."""
    text_lower = full_text.lower()

    # Ordered by specificity: more specific types first
    type_keywords = [
        ("motor_driver", ["h-bridge", "motor driver", "half-bridge", "brushed dc",
                          "stepper driver", "bldc driver"]),
        ("gate_driver", ["gate driver", "mosfet driver"]),
        ("led_driver", ["led driver", "led controller"]),
        ("op_amp", ["operational amplifier", "op amp", "opamp"]),
        ("adc", ["analog-to-digital", "analog to digital", "a/d converter"]),
        ("dac", ["digital-to-analog", "digital to analog", "d/a converter"]),
        ("mcu", ["microcontroller", "microprocessor"]),
        ("power_switch", ["load switch", "power switch", "high-side switch",
                          "low-side switch"]),
        ("voltage regulator", ["step-down", "buck converter", "switching regulator",
                               "step-up", "boost converter", "ldo", "linear regulator"]),
        ("sensor", ["sensor", "temperature", "accelerometer", "gyroscope"]),
        ("interface", ["uart", "spi", "i2c", "rs-232", "rs-485", "can bus"]),
        ("battery", ["battery charger", "battery management", "fuel gauge"]),
    ]

    for comp_type, keywords in type_keywords:
        for kw in keywords:
            if kw in text_lower:
                return comp_type

    return "ic"
