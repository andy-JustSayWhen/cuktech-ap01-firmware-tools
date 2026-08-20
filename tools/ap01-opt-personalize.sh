#!/usr/bin/env bash
set -euo pipefail

run_full_tests=false
if (($# > 0)); then
  if [[ "$1" == "--run-full-tests" ]]; then
    run_full_tests=true
    shift
  else
    echo "用法：$0 [--run-full-tests]" >&2
    exit 2
  fi
fi
if (($# > 0)); then
  echo "用法：$0 [--run-full-tests]" >&2
  exit 2
fi

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
image="cuktech-ap01-build-tools:1.0"
input="artifacts/firmware/第三方固件/物理旋钮交互优化/ap01-1.0.2_0031-opt-setting.bin"
config="env/agents-dashboard.env"
output_root="artifacts/build/personalized"
cache_relative="$output_root/.opt-fast-test-cache.json"
stamp="$(python3 -c 'from datetime import datetime; print(datetime.now().strftime("%Y%m%d-%H%M%S%f"))')"
output_directory="$output_root/fast-$stamp"
output="$output_directory/ap01-1.0.2_0031-opt-personalized.bin"
manifest="$output_directory/ap01-1.0.2_0031-opt-personalized.manifest.json"
report="$output_directory/ap01-1.0.2_0031-opt-personalized.interaction-report.json"
work_directory="$output_directory/work"

cd "$repo_root"
[[ -f "$config" ]] || { echo "缺少本机服务地址配置：$config" >&2; exit 1; }
[[ -f "$input" ]] || { echo "缺少已验收的设置菜单阶段固件：$input" >&2; exit 1; }
docker info --format '{{.ServerVersion}}' >/dev/null

image_id="$(docker image inspect "$image" --format '{{.Id}}' 2>/dev/null || true)"
if [[ -z "$image_id" ]]; then
  "$repo_root/tools/ap01-tools.sh" python -c "pass"
  image_id="$(docker image inspect "$image" --format '{{.Id}}')"
fi

input_hash="$(python3 - "$input" <<'PY'
import hashlib
import sys
from pathlib import Path
print(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest())
PY
)"
revision="$(git rev-parse HEAD)"
implementation_changes="$(git status --porcelain -- app features tools)"
cache_path="$repo_root/$cache_relative"
can_reuse_tests=false
if ! "$run_full_tests" && [[ -z "$implementation_changes" && -f "$cache_path" ]]; then
  if CACHE_PATH="$cache_path" REVISION="$revision" INPUT_HASH="$input_hash" IMAGE_ID="$image_id" python3 - <<'PY'
import json
import os
from pathlib import Path

try:
    cache = json.loads(Path(os.environ["CACHE_PATH"]).read_text(encoding="utf-8"))
except (OSError, ValueError):
    raise SystemExit(1)
raise SystemExit(0 if (
    cache.get("revision") == os.environ["REVISION"]
    and cache.get("input_sha256") == os.environ["INPUT_HASH"]
    and cache.get("image_id") == os.environ["IMAGE_ID"]
) else 1)
PY
  then
    can_reuse_tests=true
  fi
fi

if ! "$can_reuse_tests"; then
  "$repo_root/tools/ap01-tools.sh" python -m unittest discover -s . -p 'test_*.py'
  image_id="$(docker image inspect "$image" --format '{{.Id}}')"
  mkdir -p "$(dirname -- "$cache_path")"
  CACHE_PATH="$cache_path" REVISION="$revision" INPUT_HASH="$input_hash" IMAGE_ID="$image_id" python3 - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

Path(os.environ["CACHE_PATH"]).write_text(json.dumps({
    "revision": os.environ["REVISION"],
    "input_sha256": os.environ["INPUT_HASH"],
    "image_id": os.environ["IMAGE_ID"],
    "verified_at": datetime.now(timezone.utc).isoformat(),
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
fi

for target in "$output_directory" "$output" "$manifest" "$report"; do
  [[ ! -e "$target" ]] || { echo "构建目标已存在，不能覆盖：$target" >&2; exit 1; }
done

run_container() {
  docker run --rm --platform linux/amd64 --user "$(id -u):$(id -g)" \
    --mount "type=bind,source=$repo_root,target=/workspace" \
    --workdir /workspace "$image" "$@"
}

run_container python app/ap01_firmware.py agents-personalized-build \
  --input "$input" \
  --env-file "$config" \
  --output "$output" \
  --manifest "$manifest" \
  --build-dir "$work_directory"

run_container python app/ap01_firmware.py agents-interaction-simulate \
  --manifest "$manifest" \
  --report "$report" \
  --depth 8

OUTPUT_PATH="$repo_root/$output" MANIFEST_PATH="$repo_root/$manifest" python3 - <<'PY'
import hashlib
import json
import os
from pathlib import Path

output = Path(os.environ["OUTPUT_PATH"])
manifest = json.loads(Path(os.environ["MANIFEST_PATH"]).read_text(encoding="utf-8"))
payload = output.read_bytes()
sha256 = hashlib.sha256(payload).hexdigest()
allowed = (
    len(payload) == manifest["output"]["size"]
    and sha256 == manifest["output"]["sha256"]
    and manifest.get("status") == "approved-for-one-test-installation"
    and manifest.get("device_specific") is True
    and manifest.get("transport", {}).get("enabled") is True
    and manifest.get("transport", {}).get("endpoint_configuration_required") is not True
    and bool(manifest.get("transport", {}).get("endpoint_priority"))
    and manifest.get("validation", {}).get("installation_allowed") is True
    and manifest.get("completeness", {}).get("complete") is True
    and not manifest.get("completeness", {}).get("missing_items")
)
if not allowed:
    raise SystemExit("个人固件构建清单不满足安装条件")
print(json.dumps({"output_sha256": sha256}, ensure_ascii=False))
PY

chmod a-w "$repo_root/$output"
python3 - "$repo_root/$output" "$repo_root/$manifest" "$repo_root/$report" "$can_reuse_tests" <<'PY'
import json
import sys
from pathlib import Path

output = Path(sys.argv[1])
manifest = Path(sys.argv[2])
report = Path(sys.argv[3])
reused = sys.argv[4]
print(json.dumps({
    "result": "优化固件快速个人化完成",
    "output": str(output),
    "manifest": str(manifest),
    "report": str(report),
    "full_tests_reused": reused == "true",
    "interaction_simulation_passed": True,
}, ensure_ascii=False))
PY
