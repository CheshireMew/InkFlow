import re
from dataclasses import dataclass, field
from typing import Any, Iterable


DEFAULT_BANNED_PHRASES = (
    "总而言之",
    "综上所述",
    "不可否认",
    "本质上",
    "首先",
    "其次",
    "最后",
)

DEFAULT_STYLE_RULES = (
    "先写具体信息，再写判断，不要一上来下结论。",
    "少用空泛评价，尽量让每句话带来新信息。",
    "避免整段都一样长，句子节奏要自然，有长有短。",
    "不要用模板化收束句，不要为了完整而硬凑总结。",
    "语气像真人在表达，不要像写标准答案。",
)


@dataclass(frozen=True)
class ReviewIssue:
    code: str
    message: str


@dataclass(frozen=True)
class ReviewReport:
    issues: tuple[ReviewIssue, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.issues


@dataclass(frozen=True)
class WritingContract:
    base_system_prompt: str
    style_rules: tuple[str, ...] = DEFAULT_STYLE_RULES
    banned_phrases: tuple[str, ...] = DEFAULT_BANNED_PHRASES
    cleanup_patterns: tuple[tuple[str, str], ...] = field(
        default_factory=lambda: (
            (
                r"(?m)^(总而言之|综上所述|不可否认|本质上)[，,：: ]*",
                "",
            ),
            (
                r"(?m)^(首先|其次|最后)[，,：: ]*",
                "",
            ),
        )
    )
    rewrite_attempts: int = 1


def build_writing_contract(config: dict[str, Any]) -> WritingContract:
    raw_contract = config.get("writing_contract") or {}
    base_system_prompt = config.get("system_prompt", "你是一个经验很强的中文写作者。")

    inherit_default_style_rules = raw_contract.get("inherit_default_style_rules", True)
    inherit_default_banned_phrases = raw_contract.get("inherit_default_banned_phrases", True)

    style_defaults = DEFAULT_STYLE_RULES if inherit_default_style_rules else ()
    banned_defaults = DEFAULT_BANNED_PHRASES if inherit_default_banned_phrases else ()

    style_rules = _merge_unique(style_defaults, raw_contract.get("style_rules", ()))
    banned_phrases = _merge_unique(banned_defaults, raw_contract.get("banned_phrases", ()))
    rewrite_attempts = int(raw_contract.get("rewrite_attempts", 1))

    return WritingContract(
        base_system_prompt=base_system_prompt,
        style_rules=style_rules,
        banned_phrases=banned_phrases,
        rewrite_attempts=max(rewrite_attempts, 0),
    )


def compose_system_prompt(contract: WritingContract) -> str:
    rules = "\n".join(f"{index + 1}. {rule}" for index, rule in enumerate(contract.style_rules))
    banned = "、".join(contract.banned_phrases)
    banned_line = (
        f"禁止出现这些模板化表达：{banned}。"
        if banned
        else "不要写成模板腔，不要补空话。"
    )
    return (
        f"{contract.base_system_prompt}\n\n"
        "你必须遵守以下写作约束：\n"
        f"{rules}\n\n"
        f"{banned_line}\n"
        "如果任务要求输出 JSON，只返回合法 JSON，不要补解释。"
    )


def review_text(text: str, contract: WritingContract) -> ReviewReport:
    issues: list[ReviewIssue] = []
    stripped = text.strip()

    for phrase in contract.banned_phrases:
        if phrase and phrase in stripped:
            issues.append(
                ReviewIssue(
                    code="banned_phrase",
                    message=f"出现了禁用表达“{phrase}”",
                )
            )

    paragraph_openers = re.findall(
        r"(?m)^(首先|其次|最后|总而言之|综上所述|不可否认|本质上)[，,：: ]*",
        stripped,
    )
    if paragraph_openers:
        issues.append(
            ReviewIssue(
                code="template_opener",
                message="段首出现了明显模板化起手式",
            )
        )

    if len(re.findall(r"[。！？!?]", stripped)) >= 3:
        sentence_lengths = [
            len(sentence.strip())
            for sentence in re.split(r"[。！？!?]", stripped)
            if sentence.strip()
        ]
        if sentence_lengths:
            spread = max(sentence_lengths) - min(sentence_lengths)
            if spread <= 6:
                issues.append(
                    ReviewIssue(
                        code="flat_rhythm",
                        message="句长变化太小，整体节奏像模板拼接",
                    )
                )

    return ReviewReport(tuple(issues))


def cleanup_text(text: str, contract: WritingContract) -> str:
    cleaned = text.strip()
    for pattern, replacement in contract.cleanup_patterns:
        cleaned = re.sub(pattern, replacement, cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def build_rewrite_prompt(text: str, report: ReviewReport) -> str:
    issue_lines = "\n".join(f"- {issue.message}" for issue in report.issues)
    return (
        "请只重写下面这段内容，不要改变事实、信息量和任务目标。\n"
        "必须修正这些问题：\n"
        f"{issue_lines}\n\n"
        "重写要求：\n"
        "1. 保留原意。\n"
        "2. 不要补充解释。\n"
        "3. 只输出重写后的正文。\n\n"
        "原文：\n"
        f"{text}"
    )


def _merge_unique(defaults: Iterable[str], overrides: Iterable[str]) -> tuple[str, ...]:
    merged: list[str] = []
    for value in [*defaults, *overrides]:
        if value and value not in merged:
            merged.append(value)
    return tuple(merged)
