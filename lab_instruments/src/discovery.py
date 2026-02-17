"""
Instrument Discovery and Initialization Module
"""

import pyvisa
import time
from typing import Dict, Optional, Any

from .terminal import ColorPrinter
from .bk_4063 import BK_4063
from .hp_34401a import HP_34401A
from .hp_e3631a import HP_E3631A
from .tektronix_mso2024 import Tektronix_MSO2024
from .rigol_dho804 import Rigol_DHO804
from .matrix_mps6010h import MATRIX_MPS6010H
from .owon_xdm1041 import Owon_XDM1041
from .jds6600_generator import JDS6600_Generator


class InstrumentDiscovery:
    """
    Scans for and initializes lab instruments automatically.
    """

    # Mapping of model substrings to Driver Classes
    MODEL_MAP = {
        "4063": BK_4063,
        "MSO2024": Tektronix_MSO2024,
        "DHO804": Rigol_DHO804,
        "E3631A": HP_E3631A,
        "34401A": HP_34401A,
        "MPS-6010H-1C": MATRIX_MPS6010H,
        "XDM1041": Owon_XDM1041,
        "JDS6600": JDS6600_Generator,
    }

    # Friendly names for the instruments (use generic names)
    NAME_MAP = {
        "4063": "awg",
        "MSO2024": "scope",
        "DHO804": "scope",
        "E3631A": "psu",
        "34401A": "dmm",
        "MPS-6010H-1C": "psu",      # Generic name
        "XDM1041": "dmm",           # Generic name
        "JDS6600": "awg",
    }

    # Backup names if there's a conflict (multiple devices of same type)
    FALLBACK_NAMES = {
        "4063": "awg_bk",
        "MSO2024": "scope_tek",
        "DHO804": "scope_rigol",
        "E3631A": "psu_hp",
        "34401A": "dmm_hp",
        "MPS-6010H-1C": "psu_matrix",
        "XDM1041": "dmm_owon",
        "JDS6600": "awg_jds",
    }

    def __init__(self):
        self.rm = pyvisa.ResourceManager()
        self.found_devices: Dict[str, Any] = {}

    def _try_serial_idn(self, inst) -> Optional[str]:
        """
        Try common serial configurations to query *IDN?.

        Returns:
            str: IDN response if successful, None otherwise
        """
        # Common serial configurations for lab instruments
        configs = [
            # (baud_rate, read_term, write_term)
            (9600, '\n', '\r\n'),    # MATRIX MPS-6010H-1C
            (9600, '\n', '\n'),
            (19200, '\n', '\r\n'),
            (115200, '\n', '\n'),
            (115200, '\r\n', '\r\n'),  # JDS6600
        ]

        for baud, read_term, write_term in configs:
            try:
                # Set serial parameters with error handling
                try:
                    inst.baud_rate = baud
                except (ValueError, TypeError):
                    continue  # Skip if baud rate can't be set

                try:
                    inst.data_bits = 8
                    inst.parity = pyvisa.constants.Parity.none
                    inst.stop_bits = pyvisa.constants.StopBits.one
                except (ValueError, TypeError, AttributeError):
                    pass  # Continue even if these fail

                inst.read_termination = read_term
                inst.write_termination = write_term
                inst.timeout = 1000  # 1 second timeout for serial

                idn = inst.query("*IDN?", delay=0.1).strip()
                if idn:  # Got a response
                    return idn
            except Exception:
                continue

        return None

    def _try_jds6600_idn(self, inst) -> Optional[str]:
        """
        Try JDS6600/Seesii DDS generator identification.
        JDS6600 doesn't respond to *IDN?, uses its own protocol.

        Returns:
            str: "JDS6600" if identified, None otherwise
        """
        try:
            inst.baud_rate = 115200
            inst.data_bits = 8
            inst.parity = pyvisa.constants.Parity.none
            inst.stop_bits = pyvisa.constants.StopBits.one
            inst.read_termination = "\r\n"
            inst.write_termination = "\r\n"
            inst.timeout = 1000

            # Try reading output status (command :r20=)
            inst.write(":r20=")
            response = inst.read().strip()

            # JDS6600 responds with format like ":r20=1,1."
            if response.startswith(":r20=") and (',' in response):
                # Try to get model info
                try:
                    inst.write(":r00=")
                    model_resp = inst.read().strip()
                    # Response like ":r00=15." indicates model
                    return f"JDS6600"
                except:
                    return "JDS6600"

        except Exception:
            pass

        return None

    def scan(self, verbose=True) -> Dict[str, Any]:
        """Scans all available VISA resources and attempts to identify supported instruments.

        Returns:
            Dict[str, Any]: A dictionary of initialized instrument drivers, keyed by their friendly name
                            (e.g., 'scope', 'psu', 'awg', 'dmm').
        """
        if verbose:
            ColorPrinter.header("Scanning for Instruments")

        try:
            if verbose:
                print("Enumerating VISA resources...", flush=True)
            resources = self.rm.list_resources()
            if verbose:
                print(f"Found {len(resources)} VISA resource(s)", flush=True)
        except pyvisa.VisaIOError as e:
            if verbose:
                ColorPrinter.error(f"Failed to list resources: {e}")
            return {}
        except Exception as e:
            if verbose:
                ColorPrinter.error(f"Unexpected error listing resources: {e}")
            return {}

        found_drivers = {}

        for resource in resources:
            # Skip Bluetooth and other virtual serial ports that often hang
            if any(skip in resource for skip in ["Bluetooth", "BTHENUM", "BT"]):
                if verbose:
                    print(f"Skipping {resource} (virtual port)")
                continue

            if verbose:
                print(f"Checking {resource}...", end=" ", flush=True)

            try:
                # Open resource with a short timeout for identification
                inst = self.rm.open_resource(resource, timeout=2000)

                # Clear buffer if possible
                try:
                    inst.clear()
                except:
                    pass

                # Query IDN
                idn = None
                try:
                    # Check if this is a serial device
                    if resource.startswith("ASRL"):
                        # Try common serial configurations
                        idn = self._try_serial_idn(inst)

                        # If no *IDN? response, try JDS6600 protocol
                        if not idn:
                            idn = self._try_jds6600_idn(inst)
                    else:
                        # Standard query for USB/GPIB/Ethernet devices
                        idn = inst.query("*IDN?").strip()

                    if not idn:
                        raise pyvisa.VisaIOError("No response")

                except pyvisa.VisaIOError:
                    if verbose:
                        print(f"{ColorPrinter.RED}No response{ColorPrinter.RESET}")
                    inst.close()
                    continue

                if verbose:
                    print(f"{ColorPrinter.GREEN}Found: {idn}{ColorPrinter.RESET}")

                # Match against known models
                matched = False
                for model_key, driver_class in self.MODEL_MAP.items():
                    if model_key in idn:
                        friendly_name = self.NAME_MAP[model_key]

                        # Handle naming conflicts (multiple devices of same type)
                        if friendly_name in found_drivers:
                            # Use fallback name if primary name is already taken
                            friendly_name = self.FALLBACK_NAMES.get(model_key, f"{friendly_name}_2")
                            if verbose:
                                ColorPrinter.warning(
                                    f"  -> Name conflict detected, using '{friendly_name}'"
                                )

                        # We found a match! Initialize the specific driver.
                        # Note: We close the raw instance first, let the driver handle connection.
                        inst.close()

                        if verbose:
                            ColorPrinter.success(
                                f"  -> Identified as {friendly_name.upper()} ({model_key})"
                            )

                        try:
                            # Instantiate the driver
                            driver = driver_class(resource)
                            driver.connect()
                            found_drivers[friendly_name] = driver
                            matched = True
                        except Exception as e:
                            if verbose:
                                ColorPrinter.error(
                                    f"  -> Failed to initialize driver: {e}"
                                )
                        break

                if not matched:
                    inst.close()
                    if verbose:
                        ColorPrinter.warning("  -> Unknown or unsupported device.")

            except Exception as e:
                if verbose:
                    # Only show meaningful errors, not format/type errors
                    error_str = str(e)
                    if "format" not in error_str.lower():
                        print(f"{ColorPrinter.RED}Error: {e}{ColorPrinter.RESET}")
                    else:
                        print(f"{ColorPrinter.RED}No response{ColorPrinter.RESET}")
                continue

        self.found_devices = found_drivers

        if verbose:
            print("\n")
            if found_drivers:
                ColorPrinter.success(
                    f"Discovery Complete. Found {len(found_drivers)} instruments."
                )
            else:
                ColorPrinter.warning(
                    "Discovery Complete. No supported instruments found."
                )
            print("-" * 60)

        return found_drivers

    def get(self, name: str) -> Optional[Any]:
        """Get an initialized driver by friendly name ('scope', 'psu', 'awg', 'dmm')."""
        # Check user input is valid
        if name not in self.NAME_MAP.values():
            raise ValueError(
                f"Invalid instrument name '{name}'. Valid names are: {list(self.NAME_MAP.values())}"
            )
        return self.found_devices.get(name)


def find_all(verbose=True) -> Dict[str, Any]:
    """Shortcut function to scan and return all instruments."""
    scanner = InstrumentDiscovery()
    return scanner.scan(verbose)
