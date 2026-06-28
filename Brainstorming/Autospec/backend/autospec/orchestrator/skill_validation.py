"""Deterministic validation of the seeded Autospec skill library."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import skills


@dataclass(frozen=True)
class SkillValidationIssue:
    code: str
    message: str
    severity: str = "blocker"  # blocker | warning


@dataclass(frozen=True)
class SkillValidationResult:
    ok: bool
    issues: tuple[SkillValidationIssue, ...]

    @property
    def blockers(self) -> tuple[SkillValidationIssue, ...]:
        return tuple(i for i in self.issues if i.severity == "blocker")

    def messages(self) -> list[str]:
        return [i.message for i in self.issues]


def validate_seeded_skills(ws: Path) -> SkillValidationResult:
    root = ws / ".claude" / "skills"
    issues: list[SkillValidationIssue] = []
    if not root.exists():
        issues.append(
            SkillValidationIssue(
                "missing_skills_dir",
                "Le dossier .claude/skills est absent alors que les skills sont activées.",
            )
        )
        return SkillValidationResult(ok=False, issues=tuple(issues))

    expected = {s["name"] for s in skills.SKILL_REGISTRY}
    for name in sorted(expected):
        if not (root / name / "SKILL.md").is_file():
            issues.append(
                SkillValidationIssue(
                    "missing_skill",
                    f"Skill attendue manquante : {name}/SKILL.md.",
                )
            )

    rules_path = root / "skill-rules.json"
    try:
        rules = json.loads(rules_path.read_text(encoding="utf-8"))
    except OSError:
        issues.append(
            SkillValidationIssue(
                "missing_rules",
                "skill-rules.json est absent dans .claude/skills.",
            )
        )
        rules = {}
    except json.JSONDecodeError as exc:
        issues.append(
            SkillValidationIssue(
                "invalid_rules",
                f"skill-rules.json est invalide : {exc}.",
            )
        )
        rules = {}

    declared = rules.get("skills") if isinstance(rules, dict) else {}
    if isinstance(declared, dict):
        missing_rules = expected - set(declared)
        for name in sorted(missing_rules):
            issues.append(
                SkillValidationIssue(
                    "missing_rule",
                    f"Règle d'activation manquante pour la skill {name}.",
                )
            )
        for name, rule in declared.items():
            if name == "skill-creator":
                continue
            enforcement = str((rule or {}).get("enforcement") or "")
            if enforcement != "required_when_applicable":
                issues.append(
                    SkillValidationIssue(
                        "weak_enforcement",
                        (
                            f"La skill {name} doit être required_when_applicable "
                            f"(actuel : {enforcement or 'vide'})."
                        ),
                    )
                )
    elif rules:
        issues.append(
            SkillValidationIssue(
                "invalid_rules_shape",
                "skill-rules.json ne contient pas d'objet 'skills'.",
            )
        )

    blockers = [i for i in issues if i.severity == "blocker"]
    return SkillValidationResult(ok=not blockers, issues=tuple(issues))
