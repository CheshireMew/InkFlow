from __future__ import annotations

import re

MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\((?:<)?[^)]+(?:>)?\)")
BARE_URL = re.compile(
    r"(?<![\w@])(?:https?://|www\.)[^\s<>()\[\]{}\"'，。！？；：、）》】]+",
    re.IGNORECASE,
)
SOURCE_LABEL = re.compile(
    r"^\s*(?:来源|原始材料|材料文件|文件路径)(?:\s*[一二三四五六七八九十0-9]+)?\s*[：:].*$"
)
WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/].*$")
ATTACHMENT_PATH = re.compile(r"(?:^|[\\/])(?:attachments|AppData|Temp)(?:[\\/]|$)", re.IGNORECASE)


def sanitize_handoff_material(text: str) -> str:
    """Remove provenance wrappers while preserving the actual writing material."""

    cleaned_lines: list[str] = []
    for raw_line in text.replace("\ufeff", "").splitlines():
        line = raw_line.rstrip()
        if SOURCE_LABEL.match(line):
            continue
        if WINDOWS_PATH.match(line.strip()) or ATTACHMENT_PATH.search(line):
            continue
        line = MARKDOWN_LINK.sub(r"\1", line)
        line = BARE_URL.sub("", line).rstrip()
        line = re.sub(r"\s+([，。！？；：、）》】])", r"\1", line)
        line = re.sub(r"[ \t]{2,}", " ", line)
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def strip_reference_wrapper(text: str, *, section_heading: str) -> tuple[str, str]:
    """Return a storage title and the actual reference body."""

    normalized = text.replace("\ufeff", "")
    metadata_start = re.search(r"\n?<!--\s*(?:content-case-index|hook-library-index)\b", normalized)
    if metadata_start:
        normalized = normalized[: metadata_start.start()].rstrip()

    title_match = re.search(r"^#\s+(.+?)\s*$", normalized, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else "未命名参考"
    section_match = re.search(rf"^##\s+{re.escape(section_heading)}\s*$", normalized, re.MULTILINE)
    if not section_match:
        raise ValueError(f"Reference is missing section: {section_heading}")
    body = normalized[section_match.end() :].strip()
    if not body:
        raise ValueError("Reference body is empty")
    return title, body
