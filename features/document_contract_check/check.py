"""核对最终版 Brief、SPEC、DESIGN 与本地文档链接。"""

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
    design_sha256: str
    spec_ids: tuple[str, ...]
    checked_links: int

    def to_dict(self) -> dict[str, object]:
        return {
            "brief_sha256": self.brief_sha256,
            "spec_sha256": self.spec_sha256,
            "design_sha256": self.design_sha256,
            "spec_clause_count": len(self.spec_ids),
            "checked_links": self.checked_links,
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
    documents = (
        project / "reference/brief.md",
        project / "reference/SPEC.md",
        project / "reference/design.md",
        project
        / "reference/DESIGN/ap01-1.0.2_0031-opt.bin技术实现"
        / "ap01-1.0.2_0031-opt.bin技术实现.md",
    )
    texts = {path: _text(path) for path in documents}
    spec_occurrences = SPEC_PATTERN.findall(texts[documents[1]])
    if not spec_occurrences:
        raise ContractError("SPEC 没有最终版条款编号")
    duplicates = sorted({item for item in spec_occurrences if spec_occurrences.count(item) > 1})
    if duplicates:
        raise ContractError("SPEC 条款编号重复：" + ", ".join(duplicates))

    checked_links = 0
    for document, content in texts.items():
        for relative in LINK_PATTERN.findall(content):
            if relative.startswith(("http://", "https://")):
                continue
            target = (document.parent / relative).resolve()
            if not target.exists():
                raise ContractError(f"文档链接目标不存在：{document} -> {relative}")
            checked_links += 1

    return ContractReport(
        brief_sha256=_sha(texts[documents[0]]),
        spec_sha256=_sha(texts[documents[1]]),
        design_sha256=_sha(texts[documents[3]]),
        spec_ids=tuple(sorted(spec_occurrences)),
        checked_links=checked_links,
    )
