#!/usr/bin/env bash
set -euo pipefail

require_line() {
    local label="$1"
    local expected="$2"
    shift 2
    local actual
    actual="$("$@" 2>&1 | head -n 1)"
    if [[ "$actual" != *"$expected"* ]]; then
        printf '%s 版本不匹配：预期包含 %s，实际为 %s\n' "$label" "$expected" "$actual" >&2
        return 1
    fi
    printf '%s: %s\n' "$label" "$actual"
}

require_line "Gifsicle" "1.96" gifsicle --version
require_line "FFmpeg" "8.1.1" ffmpeg -version
require_line "RISC-V GCC" "16.1.0" riscv64-elf-gcc --version
require_line "RISC-V Binutils" "2.46.1" riscv64-elf-as --version

compile_directory="$(mktemp -d)"
trap 'rm -rf "$compile_directory"' EXIT
printf 'void ap01_tool_check(void) {}\n' >"$compile_directory/check.c"
riscv64-elf-gcc \
    -march=rv32imac \
    -mabi=ilp32 \
    -ffreestanding \
    -c "$compile_directory/check.c" \
    -o "$compile_directory/check.o"
riscv64-elf-readelf -h "$compile_directory/check.o" >/dev/null
printf 'RISC-V C 编译检查: 通过\n'

python - <<'PY'
from PIL import __version__ as pillow_version
import requests

expected = {"Pillow": "12.2.0", "Requests": "2.34.2"}
actual = {"Pillow": pillow_version, "Requests": requests.__version__}
for name, version in expected.items():
    if actual[name] != version:
        raise SystemExit(f"{name} 版本不匹配：预期 {version}，实际 {actual[name]}")
    print(f"{name}: {actual[name]}")
PY
