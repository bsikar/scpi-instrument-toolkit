import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from lab_instruments import BK_4063, ColorPrinter, InstrumentDiscovery
except ImportError as e:
    print(f"Import Error: {e}")
    print(
        "Ensure you are running this from the project root or have installed the package."
    )
    sys.exit(1)


def main():
    ColorPrinter.header("Testing BK 4063 AWG Driver")

    # Discover connected instruments
    discovery = InstrumentDiscovery()
    discovery.scan(verbose=True)
    awg = discovery.get("awg")

    if not awg or not isinstance(awg, BK_4063):
        ColorPrinter.error("BK 4063 AWG not found among connected instruments.")
        return

    # Waveforms to test: Sine, Square, Ramp, Pulse, Noise, DC, Arb
    # Other to test: MOD, SWEEP, BURST
    # Testing on CH1 and CH2
    # Wait for user input between changes
    # The user should be able to specify if it works, we will log at the end whats broken
    # Then shutdown

    test_waveforms = ["SINE", "SQUARE", "RAMP", "PULSE", "NOISE", "DC", "ARB"]
    channels = [1, 2]
    results = {}
    try:
        for channel in channels:
            for waveform in test_waveforms:
                ColorPrinter.info(f"Setting CH{channel} to {waveform}")
                awg.set_waveform(channel, waveform)
                awg.enable_output(channel, True)
                user_input = (
                    input(
                        "Press Enter if the waveform works, type 'no' if it doesn't: "
                    )
                    .strip()
                    .lower()
                )
                results[(channel, waveform)] = user_input != "no"
            awg.enable_output(channel, False)
    finally:
        ColorPrinter.info("Disabling all outputs and disconnecting.")
        awg.disable_all_channels()
        awg.disconnect()

    # Summary of results
    ColorPrinter.header("Test Summary")
    for (channel, waveform), passed in results.items():
        # print with color
        status = "PASS" if passed else "FAIL"
        if passed:
            ColorPrinter.success(f"CH{channel} {waveform}: {status}")
        else:
            ColorPrinter.error(f"CH{channel} {waveform}: {status}")


if __name__ == "__main__":
    main()
