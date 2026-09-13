"""Read-only analysis of the retained failed 0041 image; never contacts devices.

Design: reference/DESIGN/0041故障取证.md
The controlled service stubs are assumptions, not emulated hardware.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from capstone import Cs, CS_ARCH_RISCV, CS_MODE_RISCV32, CS_MODE_RISCVC
from unicorn import Uc, UcError, UC_ARCH_RISCV, UC_MODE_RISCV32, UC_HOOK_CODE, UC_HOOK_MEM_INVALID
from unicorn.riscv_const import UC_RISCV_REG_A0, UC_RISCV_REG_A1, UC_RISCV_REG_PC, UC_RISCV_REG_RA, UC_RISCV_REG_SP, UC_RISCV_REG_S1


BASE = 0x9FFFF000
STOCK_SHA = "972db4c136c7ed9e24a83c07c1a7fd62040ca018b08ca285216d26b1fee3c6b9"
FAILED_SHA = "34c2d3d028dd49e9c482e3339d4ef63cf4cc5abc7ae69f2d41998015a0ae7933"
HEAP = 0x63000000
STACK = 0x64008000
RETURN = 0x65000000


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def elf_symbols(data: bytes) -> dict[str, tuple[int, int, bytes]]:
    header = struct.unpack_from("<16sHHIIIIIHHHHHH", data)
    if data[:6] != b"\x7fELF\x01\x01" or header[2] != 243:
        raise ValueError("Expected little-endian ELF32 RISC-V")
    sections = [struct.unpack_from("<IIIIIIIIII", data, header[6] + i * header[11]) for i in range(header[12])]
    result = {}
    for section in sections:
        if section[1] != 2:
            continue
        table = sections[section[6]]
        strings = data[table[4]:table[4] + table[5]]
        for pos in range(section[4], section[4] + section[5], section[9]):
            name, address, size, _, _, index = struct.unpack_from("<IIIBBH", data, pos)
            if not size or not 0 < index < len(sections):
                continue
            name = strings[name:].split(b"\0", 1)[0].decode("ascii")
            source = sections[index]
            offset = source[4] + address - source[3]
            result[name] = (address, size, data[offset:offset + size])
    return result


def simulate(image: bytes, symbols: dict, *, correct_free: bool, fail_allocation: int = 0) -> dict:
    uc = Uc(UC_ARCH_RISCV, UC_MODE_RISCV32)
    uc.mem_map(BASE, (len(image) + 4095) & ~4095)
    uc.mem_write(BASE, image)
    for start, size in ((0x62FC0000, 0x10000), (HEAP, 0x20000), (0x64000000, 0x10000), (RETURN, 4096)):
        uc.mem_map(start, size)
    uc.mem_write(RETURN, bytes.fromhex("1300000013000000"))
    uc.reg_write(UC_RISCV_REG_SP, STACK)
    uc.reg_write(UC_RISCV_REG_RA, RETURN)
    uc.reg_write(UC_RISCV_REG_A0, 0x62FC9000)
    counts = {"allocation": 0, "network": 0, "free": 0, "reschedule": 0, "list_helper_assumed_return": 0}
    addresses = {name: info[0] for name, info in symbols.items()}
    events = []
    fault = []
    last = []
    allocator = [HEAP]

    def ret(value: int | None = None) -> None:
        if value is not None:
            uc.reg_write(UC_RISCV_REG_A0, value & 0xFFFFFFFF)
        uc.reg_write(UC_RISCV_REG_PC, uc.reg_read(UC_RISCV_REG_RA))

    def hook(machine, pc, size, _):
        last.append(hex(pc))
        del last[:-12]
        if pc == RETURN:
            machine.emu_stop()
        elif pc == addresses["fw_malloc"]:
            counts["allocation"] += 1
            size = machine.reg_read(UC_RISCV_REG_A0)
            if counts["allocation"] == fail_allocation:
                ret(0)
            else:
                pointer = allocator[0]
                allocator[0] += (size + 15) & ~15
                if allocator[0] > HEAP + 0x20000:
                    raise ValueError("Mock allocation exceeds mapped heap")
                machine.mem_write(pointer, bytes(size))
                ret(pointer)
        elif pc in (addresses["fw_open"], addresses["fw_read"], addresses["fw_write"]):
            ret(-1)
        elif pc == addresses["fw_close"]:
            ret(0)
        elif pc == addresses["fw_webclient_perform"]:
            counts["network"] += 1
            ret(-5)
        elif pc == addresses["fw_stock_timer_schedule"]:
            counts["reschedule"] += 1
            ret(0)
        elif pc == addresses["fw_free"]:
            counts["free"] += 1
            events.append({"free_argument": hex(machine.reg_read(UC_RISCV_REG_A0)), "s1": hex(machine.reg_read(UC_RISCV_REG_S1)), "sp": hex(machine.reg_read(UC_RISCV_REG_SP)), "return": hex(machine.reg_read(UC_RISCV_REG_RA))})
            if correct_free:
                ret()
        elif pc == 0xA0089D02:
            # Grant the erroneous list helper a successful return. This deliberately
            # does NOT model list state; it isolates the subsequent unsafe epilogue.
            counts["list_helper_assumed_return"] += 1
            ret(0)
        elif pc == 0xA008AB8A:
            # Grant the downstream deallocator success for the same isolation.
            ret()

    def invalid(machine, access, address, size, value, _):
        fault.append({"pc": hex(machine.reg_read(UC_RISCV_REG_PC)), "address": hex(address), "size": size, "access": access})
        return False

    uc.hook_add(UC_HOOK_CODE, hook)
    uc.hook_add(UC_HOOK_MEM_INVALID, invalid)
    error = None
    try:
        uc.emu_start(addresses["ap01_agents_standalone_timer_cb"], RETURN + 4, count=100000)
    except UcError as exc:
        error = str(exc)
    return {
        "correct_free_stub": correct_free, "fail_allocation": fail_allocation,
        "assumptions": ["zeroed successful allocations", "file operations fail except close", "all network calls return -5 without network I/O", "timer reschedule returns success", "wrong list helper and downstream deallocator granted a successful return"],
        "counts": counts, "free_events": events, "fault": fault, "engine_error": error,
        "final_pc": hex(uc.reg_read(UC_RISCV_REG_PC)), "final_sp": hex(uc.reg_read(UC_RISCV_REG_SP)),
        "returned_to_caller": uc.reg_read(UC_RISCV_REG_PC) == RETURN,
        "stack_balanced": uc.reg_read(UC_RISCV_REG_SP) == STACK, "last_instructions": last,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    root = args.root
    original = (root / "artifacts/firmware/original/ap01-1.0.2_0041.bin").read_bytes()
    failed = (root / "artifacts/build/personalized/ap01-1.0.2_0041-opt-personalized.bin").read_bytes()
    build = root / "artifacts/build/personalized/0041-opt"
    payload = (build / "payload.bin").read_bytes()
    if digest(original) != STOCK_SHA or digest(failed) != FAILED_SHA:
        raise ValueError("Input fingerprint mismatch")
    if failed[0x214F90:0x214F90 + len(payload)] != payload:
        raise ValueError("Retained payload is not the installed-image payload")
    symbols = elf_symbols((build / "payload.elf").read_bytes())
    for name, (address, size, data) in symbols.items():
        if name.startswith(("fw_", "ap01_agents_")) and failed[address-BASE:address-BASE+size] != data:
            raise ValueError(f"ELF symbol bytes differ: {name}")
    ranges = []
    begin = None
    for i, (a, b) in enumerate(zip(original, failed)):
        if a != b and begin is None:
            begin = i
        elif a == b and begin is not None:
            ranges.append([begin, i])
            begin = None
    if begin is not None:
        ranges.append([begin, len(failed)])
    decoder = Cs(CS_ARCH_RISCV, CS_MODE_RISCV32 | CS_MODE_RISCVC)
    disassembly = {}
    for address, size in ((0xA008AC06, 50), (0xA00B38FC, 16), (0xA005AB5C, 18), (0xA009D106, 64)):
        data = original[address-BASE:address-BASE+size]
        disassembly[hex(address)] = [{"pc": hex(ins.address), "bytes": ins.bytes.hex(), "mnemonic": ins.mnemonic, "operands": ins.op_str} for ins in decoder.disasm(data, address)]
    simulations = [simulate(failed, symbols, correct_free=correct, fail_allocation=fail) for fail in (0, 1, 2, 3) for correct in (False, True)]
    for run in simulations:
        if run["correct_free_stub"] and (run["engine_error"] or not run["returned_to_caller"] or not run["stack_balanced"] or run["counts"]["reschedule"] != 1):
            raise ValueError("Control scenario did not complete; investigation is inconclusive")
    if simulations[0]["final_pc"] != "0x0" or not simulations[0]["fault"]:
        raise ValueError("Expected release-path fault was not reproduced")
    if simulations[4]["fault"] != [{"pc": "0xa008ac20", "address": "0x14", "size": 4, "access": 19}]:
        raise ValueError("Expected buffer-allocation-failure fault was not reproduced")
    high = struct.unpack_from("<I", failed, 0x5E0F2)[0] & 0xFFFFF000
    low = struct.unpack_from("<I", failed, 0x5E0FC)[0] >> 20
    low = low - 4096 if low & 2048 else low
    timer_callback = (high + low) & 0xFFFFFFFF
    if timer_callback != symbols["ap01_agents_ui_timer_wrapper"][0]:
        raise ValueError("Actual image does not register the retained timer wrapper")
    installation = json.loads((root / "artifacts/install-records/0041-personalized-install.json").read_text(encoding="utf-8-sig"))
    upload = installation["ota"]
    if upload["local"]["sha256"] != FAILED_SHA or upload["readback"]["sha256"] != FAILED_SHA or upload["byte_identical"] is not True:
        raise ValueError("Retained installation record does not match investigated image")
    config = struct.unpack_from("<I", original, 0x78)[0]
    result = {"schema": 1, "purpose": "diagnosis_only_not_installation_approval", "stock_sha256": STOCK_SHA, "failed_sha256": FAILED_SHA, "payload_matches": True, "installation_record_matches": True, "timer_callback": hex(timer_callback), "header_basic_config": {"offset": "0x78", "value": hex(config), "sign_type": config & 3, "encrypt_type": (config >> 2) & 3, "not_device_efuse_readout": True}, "header_unchanged": original[:4096] == failed[:4096], "changed_bytes": sum(end-start for start,end in ranges), "changed_ranges": ranges, "original_instructions": disassembly, "simulations": simulations}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(json.dumps({"payload_matches": True, "changed_bytes": result["changed_bytes"], "simulations": simulations}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
