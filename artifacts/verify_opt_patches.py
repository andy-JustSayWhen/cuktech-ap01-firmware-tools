"""Verify the three approved OPT patch regions across firmware variants."""

from pathlib import Path

ROOT = Path(r"c:\Users\17239\Desktop\cuktech-ap01-firmware-tools")

FIRMWARES = {
    "original": ROOT / "artifacts/firmware/original/ap01-1.0.2_0031.bin",
    "opt-setting": ROOT / "artifacts/firmware/ap01-1.0.2_0031-opt-setting.bin",
    "opt-public": ROOT / "artifacts/firmware/ap01-1.0.2_0031-opt.bin",
    "personalized-v4": ROOT / "artifacts/build/personalized-v4/ap01-1.0.2_0031-opt-personalized.bin",
}

# From knowledge/AP01-官方固件分析/原厂各页面物理旋钮交互实现.md section 8.2
REGIONS = {
    "wrap_handler(0x01c008..0x01c0ac)": (0x01C008, 0x01C0AC),
    "right_hook(0x0f919e..0x0f91a2)": (0x0F919E, 0x0F91A2),
    "left_hook(0x0f976a..0x0f976e)": (0x0F976A, 0x0F976E),
    "encoder_isr(0x108e20..0x108e22)": (0x108E20, 0x108E22),
    "trampoline_zone(0x01c0ac..0x01c100)": (0x01C0AC, 0x01C100),
}

EXPECTED_AFTER = {
    "right_hook(0x0f919e..0x0f91a2)": "6f20b2e6",
    "left_hook(0x0f976a..0x0f976e)": "6f20128f",
}
EXPECTED_BEFORE = {
    "right_hook(0x0f919e..0x0f91a2)": "83c71400",
    "left_hook(0x0f976a..0x0f976e)": "83c71400",
    "encoder_isr(0x108e20..0x108e22)": "a14d",
}

data = {}
for name, path in FIRMWARES.items():
    data[name] = path.read_bytes()

for region, (start, end) in REGIONS.items():
    print(f"== {region} ==")
    for name, blob in data.items():
        chunk = blob[start:end]
        note = ""
        if region in EXPECTED_AFTER:
            note = (
                " <-- PATCHED"
                if chunk.hex() == EXPECTED_AFTER[region]
                else " <-- ORIGINAL"
                if chunk.hex() == EXPECTED_BEFORE[region]
                else " <-- UNEXPECTED"
            )
        elif region.startswith("wrap_handler"):
            note = " (nonzero=%d bytes)" % sum(1 for b in chunk if b)
        elif region.startswith("trampoline"):
            note = " (nonzero=%d bytes)" % sum(1 for b in chunk if b)
        print(f"  {name:18s} len={len(blob):7d}  {chunk[:64].hex()}{'...' if len(chunk) > 64 else ''}{note}")
    print()
