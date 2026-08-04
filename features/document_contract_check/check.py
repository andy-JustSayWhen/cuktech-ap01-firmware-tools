"""核对 Brief、SPEC、DESIGN 与实现矩阵之间的稳定合同。"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


SPEC_PATTERN = re.compile(r"SPEC-[A-Z]+-[0-9]{3}")
LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)")


class ContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class ContractReport:
    brief_sha256: str
    spec_sha256: str
    spec_ids: tuple[str, ...]
    matrix_ids: tuple[str, ...]
    checked_links: int

    def to_dict(self) -> dict[str, object]:
        return {
            "brief_sha256": self.brief_sha256,
            "spec_sha256": self.spec_sha256,
            "spec_clause_count": len(self.spec_ids),
            "matrix_clause_count": len(self.matrix_ids),
            "checked_links": self.checked_links,
            "missing_spec_ids": [],
        }


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ContractError(f"文档无法读取：{path}") from exc


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def check_contract(root: Path) -> ContractReport:
    project = root.expanduser().resolve(strict=True)
    brief = project / "reference/brief.md"
    spec = project / "reference/SPEC.md"
    matrix = project / "reference/DESIGN/SPEC到DESIGN实现矩阵.md"
    brief_text = _text(brief)
    spec_text = _text(spec)
    matrix_text = _text(matrix)
    spec_ids = tuple(sorted(set(SPEC_PATTERN.findall(spec_text))))
    matrix_ids = tuple(sorted(set(SPEC_PATTERN.findall(matrix_text))))
    missing = sorted(set(spec_ids) - set(matrix_ids))
    unknown = sorted(set(matrix_ids) - set(spec_ids))
    if missing:
        raise ContractError("实现矩阵缺少 SPEC 条款：" + ", ".join(missing))
    if unknown:
        raise ContractError("实现矩阵引用了不存在的 SPEC 条款：" + ", ".join(unknown))

    checked_links = 0
    for document in (brief, spec, matrix):
        for relative in LINK_PATTERN.findall(_text(document)):
            if relative.startswith(("http://", "https://")):
                continue
            target = (document.parent / relative).resolve()
            if not target.exists():
                raise ContractError(f"文档链接目标不存在：{document} -> {relative}")
            checked_links += 1
    return ContractReport(_sha(brief_text), _sha(spec_text), spec_ids, matrix_ids, checked_links)
