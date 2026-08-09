from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Explicitly copy current and historical 100x writing prompts into InkFlow."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "src" / "inkflow" / "prompt_files",
    )
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()

    content_writing = _read(source / "references" / "content-writing.md")
    naturalness_component_source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "inkflow"
        / "prompt_files"
        / "components"
        / "general-writing-naturalness.txt"
    )
    naturalness_component = _read(naturalness_component_source)
    general_writing = content_writing + "\n\n" + naturalness_component
    _write_text(
        output / "components" / "general-writing-naturalness.txt",
        naturalness_component + "\n",
    )
    prewriting = _read(source / "references" / "prewriting-research.md")
    github_single = _read(source / "references" / "github-project-short-content.md")
    github_list = _read(source / "references" / "github-project-list.md")
    natural_writing = _read(source / "references" / "natural-writing.md")
    content_audit = _read(source / "references" / "content-audit.md")

    prepare_system = "你只负责准备正式交接材料，不写成品。\n\n" + prewriting
    prepare_template = "用户明确要求：\n{{user_request}}\n\n原始材料：\n{{materials}}"
    _write_json(
        output / "seeds" / "runtime" / "prepare-material-current.prompt.json",
        _entity(
            prompt_id=_prompt_id(
                "prompt-builtin-prepare", "prepare_material", prepare_system, prepare_template
            ),
            stage="prepare_material",
            name="100x 当前材料发现与删除式净化",
            system_prompt=prepare_system,
            user_template=prepare_template,
            default_active=True,
            source={"kind": "100x-working-tree", "path": "references/prewriting-research.md"},
        ),
    )
    select_system = (
        "根据用户要求和净化材料，从给定索引中选择有帮助的参考写作案例与参考开头钩子。\n"
        "案例和钩子只帮助写法，不提供当前对象的事实、人物、经历、立场或作者身份，也不增加正文需要覆盖的信息。\n"
        "两者必须来自不同文件，完整正文也不能相同；缺少可区分的另一份参考时保持缺省。\n"
        "不要规定正文结构，不要解释选择过程，不要为了凑数选择参考。"
    )
    select_template = (
        "用户明确要求：\n{{user_request}}\n\n净化后材料：\n{{purified_material}}\n\n"
        "可选参考索引：\n{{reference_index}}"
    )
    _write_json(
        output / "seeds" / "runtime" / "select-references-current.prompt.json",
        _entity(
            prompt_id=_prompt_id(
                "prompt-builtin-select-references",
                "select_references",
                select_system,
                select_template,
            ),
            stage="select_references",
            name="100x 当前案例与钩子选择",
            system_prompt=select_system,
            user_template=select_template,
            default_active=True,
            source={"kind": "100x-working-tree", "path": "SKILL.md#写作"},
        ),
    )
    _write_json(
        output / "seeds" / "runtime" / "generate-current.prompt.json",
        _entity(
            prompt_id=_prompt_id(
                "prompt-builtin-generate", "generate", general_writing, "{{execution_package}}"
            ),
            stage="generate",
            name="100x 当前通用成文与自然表达",
            system_prompt=general_writing,
            user_template="{{execution_package}}",
            default_active=True,
            source={
                "kind": "composed-general-writing",
                "paths": [
                    "100x-learning/references/content-writing.md",
                    "src/inkflow/prompt_files/components/general-writing-naturalness.txt",
                ],
            },
        ),
    )

    _write_github_current(
        output,
        content_writing=general_writing,
        github_text=github_single,
        kind="single",
        name="100x 当前单个 GitHub 项目介绍",
        source_path="references/github-project-short-content.md",
    )
    _write_github_current(
        output,
        content_writing=general_writing,
        github_text=github_list,
        kind="list",
        name="100x 当前 GitHub 项目清单",
        source_path="references/github-project-list.md",
    )
    _write_history(
        source,
        output,
        content_writing=general_writing,
        relative="references/github-project-short-content.md",
        kind="single",
        current_text=github_single,
    )
    _write_history(
        source,
        output,
        content_writing=general_writing,
        relative="references/github-project-list.md",
        kind="list",
        current_text=github_list,
    )
    _write_archived_harness_prompt(source, output)
    _write_ai_flavor_prompts(
        source,
        output,
        content_writing=content_writing,
        natural_writing=natural_writing,
        content_audit=content_audit,
    )

    _write_json(
        output / "operations" / "provider-test.prompt.json",
        {
            "schema_version": 1,
            "name": "供应商连接测试",
            "system_prompt": "这是连接测试。只返回 JSON 对象。",
            "user_prompt": '返回 {"ok":true}。',
        },
    )
    _write_text(
        output / "contracts" / "prepare_material.txt",
        "只返回一个符合下列 JSON Schema 的合法 JSON 对象，"
        "不要添加代码围栏或解释：\n{{result_schema}}\n",
    )
    _write_text(
        output / "contracts" / "select_references.txt",
        "只返回一个符合下列 JSON Schema 的合法 JSON 对象，"
        "不要添加代码围栏或解释：\n{{result_schema}}\n",
    )
    _write_text(
        output / "contracts" / "generate.txt",
        "只返回一个符合下列 JSON Schema 的合法 JSON 对象，"
        "不要添加代码围栏或解释。只生成一篇完整成品，"
        "outputs 必须恰好包含 1 项：\n{{result_schema}}\n",
    )
    _write_text(
        output / "contracts" / "generate_many.txt",
        "只返回一个符合下列 JSON Schema 的合法 JSON 对象，"
        "不要添加代码围栏或解释。一次生成 {{output_count}} 篇完整成品，"
        "outputs 必须恰好包含 {{output_count}} 项：\n{{result_schema}}\n",
    )


def _write_github_current(
    output: Path,
    *,
    content_writing: str,
    github_text: str,
    kind: str,
    name: str,
    source_path: str,
) -> None:
    system_prompt = content_writing + "\n\n" + github_text
    _write_json(
        output / "seeds" / "github" / "current" / f"github-{kind}-current.prompt.json",
        _entity(
            prompt_id=_prompt_id(
                f"prompt-100x-github-{kind}-current",
                "generate",
                system_prompt,
                "{{execution_package}}",
            ),
            stage="generate",
            name=name,
            system_prompt=system_prompt,
            user_template="{{execution_package}}",
            default_active=False,
            source={"kind": "100x-working-tree", "path": source_path},
        ),
    )


def _write_history(
    source: Path,
    output: Path,
    *,
    content_writing: str,
    relative: str,
    kind: str,
    current_text: str,
) -> None:
    seen: set[str] = set()
    commits = _git(source, "log", "--all", "--format=%H", "--", relative).splitlines()
    for commit in commits:
        blob = _git(source, "rev-parse", f"{commit}:{relative}").strip()
        if blob in seen:
            continue
        seen.add(blob)
        text = _git(source, "show", f"{commit}:{relative}")
        date, subject = _git(source, "show", "-s", "--format=%cs%n%s", commit).splitlines()[:2]
        system_prompt = content_writing + "\n\n" + text
        prompt_id = _prompt_id(
            f"prompt-100x-github-{kind}-history-{blob[:12]}",
            "generate",
            system_prompt,
            "{{execution_package}}",
        )
        _write_json(
            output
            / "seeds"
            / "github"
            / "history"
            / f"github-{kind}-{date}-{blob[:12]}.prompt.json",
            _entity(
                prompt_id=prompt_id,
                stage="generate",
                name=f"100x 历史 GitHub {kind} · {date} · {blob[:8]}",
                system_prompt=system_prompt,
                user_template="{{execution_package}}",
                default_active=False,
                source={
                    "kind": "100x-git-history",
                    "path": relative,
                    "commit": commit,
                    "blob": blob,
                    "date": date,
                    "subject": subject,
                },
            ),
        )


def _write_archived_harness_prompt(source: Path, output: Path) -> None:
    github_path = (
        "archive/harness-overbuild-20260726/references/github-project-short-content.previous.md"
    )
    content_path = "archive/harness-overbuild-20260726/references/content-writing.previous.md"
    github_text = _read(source / github_path)
    content_text = _read(source / content_path)
    blob = _git(source, "hash-object", github_path).strip()
    commit = _git(source, "log", "-1", "--format=%H", "--", github_path).strip()
    system_prompt = content_text + "\n\n" + github_text
    _write_json(
        output
        / "seeds"
        / "github"
        / "history"
        / f"github-single-archive-2026-07-26-{blob[:12]}.prompt.json",
        _entity(
            prompt_id=_prompt_id(
                f"prompt-100x-github-single-archive-{blob[:12]}",
                "generate",
                system_prompt,
                "{{execution_package}}",
            ),
            stage="generate",
            name=f"100x 归档 GitHub 单项目介绍 · 2026-07-26 · {blob[:8]}",
            system_prompt=system_prompt,
            user_template="{{execution_package}}",
            default_active=False,
            source={
                "kind": "100x-archived-git-history",
                "path": github_path,
                "companion_path": content_path,
                "commit": commit,
                "blob": blob,
                "date": "2026-07-26",
            },
        ),
    )


def _write_ai_flavor_prompts(
    source: Path,
    output: Path,
    *,
    content_writing: str,
    natural_writing: str,
    content_audit: str,
) -> None:
    root = output / "library" / "ai_flavor"
    template = (
        "【用户本次要求】\n{{user_request}}\n\n"
        "【对应写作准备材料】\n{{writing_material}}\n\n"
        "【写作规则】\n{{writing_rules}}\n\n"
        "【待审查正文】\n{{draft}}"
    )
    combined = content_audit + "\n\n" + natural_writing
    _write_json(
        root / "current" / "ai-flavor-audit-and-cleanup-current.prompt.json",
        _specialized_entity(
            prompt_id=_prompt_id(
                "prompt-100x-ai-flavor-current",
                "ai_flavor_audit_and_cleanup",
                combined,
                template,
            ),
            name="100x 当前 AI 味审查与清理",
            purpose="ai_flavor_audit_and_cleanup",
            system_prompt=combined,
            user_template=template,
            source={
                "kind": "100x-working-tree-combined",
                "paths": [
                    "references/content-audit.md",
                    "references/natural-writing.md",
                ],
            },
        ),
    )
    for relative, text, purpose, label in (
        (
            "references/natural-writing.md",
            natural_writing,
            "ai_flavor_guidance",
            "AI 味审查与清理",
        ),
        (
            "references/content-audit.md",
            content_audit,
            "content_audit_guidance",
            "内容审查",
        ),
        (
            "references/content-writing.md",
            content_writing,
            "writing_guidance",
            "成文与自然表达",
        ),
    ):
        _write_json(
            root / "current" / f"{Path(relative).stem}-current.prompt.json",
            _specialized_entity(
                prompt_id=_prompt_id(
                    f"prompt-100x-{Path(relative).stem}-current",
                    purpose,
                    text,
                    template,
                ),
                name=f"100x 当前{label}原文",
                purpose=purpose,
                system_prompt=text,
                user_template=template,
                source={"kind": "100x-working-tree", "path": relative},
            ),
        )
        _write_specialized_history(
            source,
            root,
            relative=relative,
            purpose=purpose,
            label=label,
            user_template=template,
        )

    for archived_path, purpose, label in (
        (
            "archive/harness-overbuild-20260726/references/content-audit.previous.md",
            "content_audit_guidance",
            "内容与 AI 味审计",
        ),
        (
            "archive/harness-overbuild-20260726/references/content-writing.previous.md",
            "writing_guidance",
            "成文与自然表达",
        ),
    ):
        archived = _read(source / archived_path)
        blob = _git(source, "hash-object", archived_path).strip()
        commit = _git(source, "log", "-1", "--format=%H", "--", archived_path).strip()
        stem = Path(archived_path).name.removesuffix(".previous.md")
        _write_json(
            root / "history" / f"{stem}-archive-2026-07-26-{blob[:12]}.prompt.json",
            _specialized_entity(
                prompt_id=_prompt_id(
                    f"prompt-100x-{stem}-archive-{blob[:12]}",
                    purpose,
                    archived,
                    template,
                ),
                name=f"100x 归档{label} · 2026-07-26 · {blob[:8]}",
                purpose=purpose,
                system_prompt=archived,
                user_template=template,
                source={
                    "kind": "100x-archived-git-history",
                    "path": archived_path,
                    "commit": commit,
                    "blob": blob,
                    "date": "2026-07-26",
                },
            ),
        )


def _write_specialized_history(
    source: Path,
    output: Path,
    *,
    relative: str,
    purpose: str,
    label: str,
    user_template: str,
) -> None:
    seen: set[str] = set()
    commits = _git(source, "log", "--all", "--format=%H", "--", relative).splitlines()
    for commit in commits:
        blob = _git(source, "rev-parse", f"{commit}:{relative}").strip()
        if blob in seen:
            continue
        seen.add(blob)
        text = _git(source, "show", f"{commit}:{relative}")
        date, subject = _git(source, "show", "-s", "--format=%cs%n%s", commit).splitlines()[:2]
        stem = Path(relative).stem
        _write_json(
            output / "history" / f"{stem}-{date}-{blob[:12]}.prompt.json",
            _specialized_entity(
                prompt_id=_prompt_id(
                    f"prompt-100x-{stem}-history-{blob[:12]}",
                    purpose,
                    text,
                    user_template,
                ),
                name=f"100x 历史{label} · {date} · {blob[:8]}",
                purpose=purpose,
                system_prompt=text,
                user_template=user_template,
                source={
                    "kind": "100x-git-history",
                    "path": relative,
                    "commit": commit,
                    "blob": blob,
                    "date": date,
                    "subject": subject,
                },
            ),
        )


def _entity(
    *,
    prompt_id: str,
    stage: str,
    name: str,
    system_prompt: str,
    user_template: str,
    default_active: bool,
    source: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "id": prompt_id,
        "stage": stage,
        "name": name,
        "system_prompt": system_prompt.rstrip(),
        "user_template": user_template,
        "contract_version": 1,
        "revision": None,
        "default_active": default_active,
        "source": source,
    }


def _specialized_entity(
    *,
    prompt_id: str,
    name: str,
    purpose: str,
    system_prompt: str,
    user_template: str,
    source: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "id": prompt_id,
        "name": name,
        "purpose": purpose,
        "system_prompt": system_prompt.rstrip(),
        "user_template": user_template,
        "source": source,
    }


def _prompt_id(prefix: str, stage: str, system_prompt: str, user_template: str) -> str:
    content = f"{stage}\0{system_prompt.rstrip()}\0{user_template}".encode("utf-8")
    return f"{prefix}-{hashlib.sha256(content).hexdigest()[:12]}"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig").rstrip()


def _git(source: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=source,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.rstrip("\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
