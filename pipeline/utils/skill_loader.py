# pipeline/utils/skill_loader.py
from pathlib import Path

SKILLS_DIR = Path.home() / ".agents" / "skills"

DESIGN_SKILLS = [
    "design-taste-frontend",
    "high-end-visual-design",
    "emil-design-eng",
    "redesign-existing-projects",
]


def _extract_key_rules(skill_name: str, max_chars: int = 1200) -> str:
    """Read a SKILL.md and return its most actionable content, trimmed."""
    path = SKILLS_DIR / skill_name / "SKILL.md"
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    # Strip frontmatter
    if text.startswith("---"):
        end = text.find("---", 3)
        text = text[end + 3:].strip() if end != -1 else text
    return text[:max_chars]


def build_design_system_prompt() -> str:
    """Build a combined design guidance prompt from installed skill files."""
    parts = []
    for skill in DESIGN_SKILLS:
        content = _extract_key_rules(skill)
        if content:
            parts.append(f"## {skill}\n{content}")

    if not parts:
        return (
            "Design to a high-end agency standard. "
            "No generic layouts. Premium typography. Strong visual hierarchy. "
            "No AI defaults (no purple gradients, no Inter, no Bootstrap cards). "
            "Every pixel intentional."
        )

    return (
        "You are generating a premium demo website. Apply these design standards strictly:\n\n"
        + "\n\n".join(parts)
    )
