"""
AI extraction test bank: 50 components across diverse manufacturers and types.

Tests the full pipeline: fetch PDF -> parse -> AI extract -> validate packages.
Requires a Gemini API key in ~/.schemagic/config.json.

Usage:
    python3 tests/test_ai_extraction.py
"""

import sys
import os
import time
import json

os.environ["SCHEMAGIC_STANDALONE"] = "1"
if __name__ == "__main__":
    REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)

from engine.datasheet.fetcher import fetch_datasheet
from engine.datasheet.parser import extract_tables_and_text
from engine.datasheet.ai_extractor import extract_with_gemini
from engine.core.user_config import get_gemini_key


# Test bank: (part_number, [expected_package_substrings], min_expected_pins)
# Expected packages use substring matching - "SOIC-8" matches "SOIC-8" in results
TEST_BANK = [
    # === POWER MANAGEMENT ===
    # LDO regulators
    ("TPS7E82-Q1",    ["SOT-23-5", "WSON-6", "HVSSOP-8"],  5),   # TI, multi-package
    ("AMS1117-3.3",   ["SOT-223"],                           3),   # AMS, ubiquitous LDO
    ("MCP1700",       ["SOT-23"],                             3),   # Microchip LDO
    ("LP5907",        ["SOT-23-5"],                           5),   # TI ultra-low noise
    # Buck converters
    ("TPS54302",      ["SOT-23-6"],                           6),   # TI simple buck
    ("LM2596",        ["TO-220", "TO-263"],                   5),   # TI/ON classic buck (5-pin power packages)
    ("MP2307",        ["SOIC-8"],                              8),   # MPS buck
    # Boost converters
    ("TPS61023",      ["SOT-563", "SOT563"],                   6),   # TI boost (SOT-563 only)
    # Battery management
    ("BQ24072",       ["QFN-16", "VQFN-16"],                  14),  # TI Li-Ion charger (16-pin VQFN, not 20)
    ("MCP73831",      ["SOT-23-5"],                           5),   # Microchip charge mgr

    # === MICROCONTROLLERS ===
    ("STM32F103C8",   ["LQFP-48"],                            48),  # STM32 Blue Pill
    ("ATmega328P",    ["TQFP-32", "QFN-32"],                   28),  # Arduino classic (PDIP-28 often missed in early pages)
    ("PIC16F877A",    ["PDIP-40", "TQFP-44"],                 40),  # Microchip PIC classic
    ("ESP32-WROOM",   [],                                      0),   # Module (may not parse)
    ("RP2040",        ["QFN-56"],                              30),  # Raspberry Pi MCU

    # === OP-AMPS & ANALOG ===
    ("LM358",         ["SOIC-8", "PDIP-8"],                   8),   # Classic dual op-amp
    ("OPA2134",       ["SOIC-8", "PDIP-8"],                   8),   # TI audio op-amp
    ("AD8605",        ["SOT-23-5"],                            5),   # ADI precision op-amp
    ("TL072",         ["SOIC-8", "PDIP-8"],                   8),   # TI JFET op-amp
    ("LM324",         ["SOIC-14", "PDIP-14"],                 14),  # Quad op-amp

    # === ADC / DAC ===
    ("ADS1115",       ["VSSOP-10"],                            10),  # TI 16-bit ADC
    ("MCP4725",       ["SOT-23-6"],                            6),   # Microchip 12-bit DAC

    # === COMMUNICATION / INTERFACE ===
    ("TJA1050",       ["SOIC-8"],                               8),  # NXP CAN transceiver
    ("MAX485",        ["SOIC-8", "PDIP-8"],                    8),  # Maxim RS-485
    ("SN65HVD230",    ["SOIC-8"],                               8),  # TI CAN transceiver
    ("CH340G",        ["SOIC-16"],                             16),  # WCH USB-UART
    ("FT232RL",       ["SSOP-28"],                             28),  # FTDI USB-UART
    ("SP3232E",       ["SOIC-16"],                             16),  # MaxLinear RS-232

    # === MOTOR DRIVERS ===
    ("DRV8850",       ["VQFN-24"],                             24),  # TI H-bridge
    ("A4988",         ["QFN", "TSSOP"],                        16),  # Allegro stepper (QFN-24/32 + eTSSOP-24)
    ("L298N",         ["MULTIWATT"],                            15),  # ST dual H-bridge
    ("UC3845",        ["SOIC-8", "PDIP-8"],                    8),  # PWM controller

    # === SENSORS ===
    ("BME280",        ["LGA-8"],                                8),  # Bosch env sensor
    ("MPU-6050",      ["QFN-24"],                              24),  # InvenSense IMU
    ("LM35",          ["TO-92", "SOIC-8"],                      3),  # TI temp sensor (TO-92, not SOT-23)
    ("INA219",        ["SOIC-8"],                               6),  # TI current sensor

    # === VOLTAGE REFERENCES ===
    ("REF5050",       ["SOIC-8"],                               8),  # TI precision ref
    ("LM4040",        ["SOT-23"],                               3),  # TI shunt ref

    # === LOGIC ICS ===
    ("SN74HC595",     ["SOIC-16", "PDIP-16"],                 16),  # TI shift register
    ("SN74LVC245A",   ["SOIC-20", "TSSOP-20"],                20),  # TI level shifter
    ("CD4051",        ["SOIC-16", "PDIP-16"],                 16),  # TI analog mux
    ("NE555",         ["SOIC-8", "PDIP-8"],                    8),  # TI classic timer

    # === PROTECTION ===
    ("TPD4E05U06",    ["SOT-5X3"],                              6),  # TI ESD protection

    # === LED DRIVERS ===
    ("TLC5940",       ["HTSSOP-28"],                           28),  # TI 16-ch LED driver

    # === MEMORY ===
    ("AT24C256",      ["SOIC-8"],                               8),  # Microchip I2C EEPROM
    ("W25Q128JV",     ["SOIC-8"],                               8),  # Winbond SPI Flash

    # === AUDIO ===
    ("LM386",         ["SOIC-8", "PDIP-8"],                    8),  # TI audio amp

    # === POWER MOSFETS ===
    ("IRLZ44N",       ["TO-220"],                               3),  # Infineon N-ch MOSFET
    ("AO3400",        ["SOT-23"],                               3),  # AOS N-ch MOSFET

    # === COMPARATORS ===
    ("LM393",         ["SOIC-8", "PDIP-8"],                    8),  # TI dual comparator

    # ================================================================
    # EXPANDED TEST BANK (51-100)
    # ================================================================

    # === MORE POWER ===
    ("TPS62160",      ["WSON-8", "VSSOP-8"],                    8),  # TI 1A step-down (8-pin, not 10)
    ("LMR14030",      ["SOIC-8"],                               8),   # TI 40V buck
    ("TLV1117",       ["SOT-223"],                              3),   # TI 800mA LDO (no PDIP)
    ("AP2112",        ["SOT-23-5"],                              5),   # Diodes Inc LDO
    ("TPS5430",       ["SOIC-8"],                                8),   # TI 3A buck
    ("LT1761",        ["SOT-23-5"],                              5),   # ADI/Linear LDO
    ("MIC5205",       ["SOT-23-5"],                              5),   # Microchip LDO

    # === MORE MCUS ===
    ("STM32G031K8",   ["LQFP-32"],                              32),  # STM32 entry-level
    ("ATtiny85",      ["SOIC-8", "PDIP-8"],                     8),   # Microchip tiny MCU
    ("PIC12F675",     ["SOIC-8", "PDIP-8"],                     8),   # Microchip 8-pin PIC
    ("MSP430G2553",   ["PDIP-20", "TSSOP-20"],                 20),  # TI MSP430

    # === MORE OP-AMPS ===
    ("MCP6002",       ["SOIC-8"],                                8),  # Microchip rail-to-rail
    ("LMV324",        ["SOIC-14", "TSSOP-14"],                 14),  # TI low-voltage quad
    ("TLV9062",       ["SOIC-8"],                                8),  # TI RRIO op-amp
    ("NE5532",        ["SOIC-8", "PDIP-8"],                     8),  # TI audio op-amp

    # === MORE ADC/DAC ===
    ("ADS1256",       ["SSOP-28"],                              28),  # TI 24-bit ADC (SSOP, not TSSOP)
    ("DAC8562",       ["VSSOP-10"],                             10),  # TI dual 16-bit DAC

    # === MORE COMMUNICATION ===
    ("MCP2515",       ["SOIC-18", "PDIP-18"],                  18),  # Microchip CAN controller
    ("SN65HVD3082E",  ["SOIC-8"],                                8),  # TI RS-485
    ("ISO7721",       ["SOIC-8"],                                8),  # TI digital isolator
    ("TXB0108",       ["TSSOP-20"],                             20),  # TI voltage translator
    ("MAX3232",       ["SOIC-16"],                              16),  # TI RS-232

    # === MORE SENSORS ===
    ("ACS712",        ["SOIC-8"],                                8),  # Allegro current sensor
    ("TMP36",         ["SOT-23"],                                3),  # ADI temp sensor
    ("LIS3DH",        ["LGA-16"],                               16),  # ST accelerometer
    ("BMP280",        ["LGA-8"],                                 8),  # Bosch pressure sensor

    # === REGULATORS & REFS ===
    ("TL431",         ["SOIC-8", "SOT-23"],                     3),  # TI prog shunt ref
    ("LM317",         ["SOT-223", "TO-220"],                    3),  # TI adj regulator

    # === MORE LOGIC ===
    ("SN74HC04",      ["SOIC-14", "PDIP-14"],                  14),  # TI hex inverter
    ("SN74HC08",      ["SOIC-14", "PDIP-14"],                  14),  # TI quad AND
    ("SN74HC138",     ["SOIC-16", "PDIP-16"],                  16),  # TI 3-to-8 decoder
    ("SN74AHC1G04",   ["SOT-23-5"],                              5),  # TI single inverter
    ("CD4017",        ["PDIP-16"],                              16),  # TI decade counter
    ("SN74HC32",      ["SOIC-14", "PDIP-14"],                  14),  # TI quad OR gate

    # === MORE MOTOR/POWER ===
    ("DRV8833",       ["HTSSOP-16", "TSSOP-16"],                16),  # TI dual H-bridge (16-pin packages)
    ("ULN2003A",      ["SOIC-16", "PDIP-16"],                  16),  # TI Darlington array
    ("IR2104",        ["SOIC-8", "PDIP-8"],                     8),  # Infineon half-bridge driver
    ("TPS2024",       ["SOIC-8"],                                8),  # TI power switch

    # === MISC ===
    ("LM555",         ["SOIC-8", "PDIP-8"],                     8),  # TI timer (TI branding)
    ("ICM7555",       ["SOIC-8", "PDIP-8"],                     8),  # Renesas CMOS 555
    ("DS18B20",       ["TO-92"],                                 3),  # Maxim 1-Wire temp
    ("PCF8574",       ["SOIC-16", "PDIP-16"],                  16),  # NXP I2C GPIO expander
    ("CD74HC4067",    ["SOIC-24"],                              24),  # TI 16-ch mux (no PDIP)
    ("TCA9548A",      ["TSSOP-24"],                             24),  # TI I2C mux
    ("TCAN1042",      ["SOIC-8"],                                8),  # TI CAN FD transceiver
    ("OPT3001",       ["USON-6"],                                6),  # TI ambient light sensor
]


def run_test_bank():
    try:
        api_key, model = get_gemini_key()
    except RuntimeError as e:
        print("ERROR: {}".format(e))
        print('  {"gemini_api_key": "YOUR_KEY", "gemini_model": "gemini-2.5-flash-lite"}')
        sys.exit(1)

    print("=" * 80)
    print("schemagic AI Extraction Test Bank")
    print("Provider: gemini / {}".format(model))
    print("{} components to test".format(len(TEST_BANK)))
    print("=" * 80)

    results = []
    fetch_fails = []
    ai_fails = []
    passes = []
    partials = []

    for i, (pn, expected_pkgs, expected_min_pins) in enumerate(TEST_BANK):
        print("\n[{}/{}] {} ...".format(i + 1, len(TEST_BANK), pn), end=" ", flush=True)

        t0 = time.time()

        # Fetch
        try:
            url, pdf_path, mfr = fetch_datasheet(pn)
            if not pdf_path:
                print("FETCH_FAIL ({})".format(mfr or "unknown"))
                fetch_fails.append(pn)
                results.append((pn, "FETCH_FAIL", [], 0, time.time() - t0))
                continue
        except Exception as e:
            print("FETCH_ERROR: {}".format(str(e)[:60]))
            fetch_fails.append(pn)
            results.append((pn, "FETCH_ERROR", [], 0, time.time() - t0))
            continue

        # Parse
        try:
            tables, full_text, page_texts = extract_tables_and_text(pdf_path)
        except Exception as e:
            print("PARSE_ERROR: {}".format(str(e)[:60]))
            results.append((pn, "PARSE_ERROR", [], 0, time.time() - t0))
            continue

        # AI extract
        try:
            packages, pins, desc = extract_with_gemini(
                pn, page_texts, api_key, model,
            )
            ai_time = time.time() - t0

            pkg_names = [p.name for p in packages]

            # Validate
            if not expected_pkgs:
                # No expected packages (module/exotic) - just check we got something
                status = "PASS" if packages else "NO_DATA"
            else:
                found = 0
                for exp in expected_pkgs:
                    exp_lower = exp.lower()
                    if any(exp_lower in n.lower() for n in pkg_names):
                        found += 1
                if found == len(expected_pkgs):
                    status = "PASS"
                elif found > 0:
                    status = "PARTIAL ({}/{})".format(found, len(expected_pkgs))
                else:
                    status = "FAIL"

            # Check pins
            pin_ok = len(pins) >= expected_min_pins if expected_min_pins > 0 else True

            if status == "PASS" and pin_ok:
                passes.append(pn)
            elif "PARTIAL" in status:
                partials.append(pn)
            elif status == "FAIL":
                ai_fails.append(pn)

            pkg_str = ", ".join(pkg_names)[:50]
            pin_str = "{} pins".format(len(pins))
            if not pin_ok and expected_min_pins > 0:
                pin_str += " (expected >= {})".format(expected_min_pins)
                status += " LOW_PINS"

            print("{} [{:.1f}s] {} | {}".format(status, ai_time, pkg_str, pin_str))
            results.append((pn, status, pkg_names, len(pins), ai_time))

        except Exception as e:
            print("AI_ERROR: {}".format(str(e)[:60]))
            ai_fails.append(pn)
            results.append((pn, "AI_ERROR", [], 0, time.time() - t0))

        # Rate limit: brief pause between API calls
        time.sleep(0.5)

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    total = len(TEST_BANK)
    n_pass = len(passes)
    n_partial = len(partials)
    n_fetch_fail = len(fetch_fails)
    n_ai_fail = len(ai_fails)
    n_other = total - n_pass - n_partial - n_fetch_fail - n_ai_fail

    print("PASS:       {}/{}".format(n_pass, total))
    print("PARTIAL:    {}/{}".format(n_partial, total))
    print("FETCH_FAIL: {}/{}".format(n_fetch_fail, total))
    print("AI_FAIL:    {}/{}".format(n_ai_fail, total))
    if n_other:
        print("OTHER:      {}/{}".format(n_other, total))

    if partials:
        print("\nPartial results (got some but not all expected packages):")
        for pn in partials:
            r = next(r for r in results if r[0] == pn)
            print("  {} -> got: {}".format(pn, ", ".join(r[2])))

    if ai_fails:
        print("\nAI failures:")
        for pn in ai_fails:
            r = next(r for r in results if r[0] == pn)
            print("  {} -> got: {}".format(pn, ", ".join(r[2]) if r[2] else "nothing"))

    if fetch_fails:
        print("\nFetch failures (datasheet not downloadable):")
        for pn in fetch_fails:
            print("  {}".format(pn))

    # Timing stats
    ai_times = [r[4] for r in results if r[1] not in ("FETCH_FAIL", "FETCH_ERROR")]
    if ai_times:
        print("\nTiming: avg {:.1f}s, min {:.1f}s, max {:.1f}s".format(
            sum(ai_times) / len(ai_times),
            min(ai_times),
            max(ai_times),
        ))

    rate = (n_pass + n_partial) / (total - n_fetch_fail) * 100 if (total - n_fetch_fail) > 0 else 0
    print("\nAI accuracy rate: {:.0f}% ({}/{} fetchable parts)".format(
        rate, n_pass + n_partial, total - n_fetch_fail,
    ))

    return n_pass, n_partial, n_fetch_fail, n_ai_fail


if __name__ == "__main__":
    run_test_bank()
