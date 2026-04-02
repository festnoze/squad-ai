"""Exercise validator - compares student code against correction.

Usage:
    python validator/validate.py                    # Validate all exercises
    python validator/validate.py 01                 # Validate exercise 01 only
    python validator/validate.py 01 03 07           # Validate specific exercises
    python validator/validate.py --html report.html # Generate HTML report
"""

import importlib.util
import inspect
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
EXERCISES = [f"exercise_{i:02d}" for i in range(1, 12)]

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# --- Colors for terminal ---
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


@dataclass
class CheckResult:
    name: str
    passed: bool
    severity: str  # "error", "warning", "info"
    message: str
    points: float
    max_points: float


@dataclass
class ExerciseResult:
    exercise_id: str
    title: str
    import_ok: bool
    import_error: str = ""
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def score(self) -> float:
        total = sum(c.max_points for c in self.checks)
        earned = sum(c.points for c in self.checks)
        return round(earned / total * 100, 1) if total > 0 else 0.0

    @property
    def grade(self) -> str:
        s = self.score
        if s >= 90: return "A"
        if s >= 75: return "B"
        if s >= 60: return "C"
        if s >= 40: return "D"
        return "F"

    @property
    def grade_label(self) -> str:
        labels = {"A": "Excellent", "B": "Bien", "C": "Passable", "D": "Insuffisant", "F": "A refaire"}
        return labels[self.grade]


def load_module(filepath: Path, name: str) -> tuple[Any, str]:
    """Import a Python file as a module. Returns (module, error)."""
    if name in sys.modules:
        del sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, str(filepath))
    if not spec or not spec.loader:
        return None, f"Cannot create module spec for {filepath}"
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        return module, ""
    except Exception:
        return None, traceback.format_exc()


def get_agent_info(module: Any) -> dict:
    """Extract structural info from a module's root_agent."""
    agent = getattr(module, "root_agent", None)
    if agent is None:
        return {"exists": False}

    agent_type = type(agent).__name__
    info = {
        "exists": True,
        "type": agent_type,
        "name": getattr(agent, "name", None),
        "model": getattr(agent, "model", None),
        "instruction": getattr(agent, "instruction", None),
        "description": getattr(agent, "description", None),
        "output_key": getattr(agent, "output_key", None),
    }

    # Tools
    tools = getattr(agent, "tools", None) or []
    info["tool_names"] = sorted(t.name if hasattr(t, "name") else str(t) for t in tools)
    info["tool_count"] = len(tools)

    # Sub-agents
    subs = getattr(agent, "sub_agents", None) or []
    info["sub_agent_names"] = sorted(getattr(s, "name", "?") for s in subs)
    info["sub_agent_count"] = len(subs)

    # Callbacks
    for cb in ["before_model_callback", "after_model_callback", "before_tool_callback",
                "after_tool_callback", "before_agent_callback", "after_agent_callback"]:
        info[cb] = getattr(agent, cb, None) is not None

    # Max iterations (LoopAgent)
    info["max_iterations"] = getattr(agent, "max_iterations", None)

    return info


def get_functions(module: Any) -> dict[str, dict]:
    """Extract all user-defined functions from a module."""
    funcs = {}
    for name, obj in inspect.getmembers(module, inspect.isfunction):
        if obj.__module__ == module.__name__:
            sig = inspect.signature(obj)
            params = {k: str(v.annotation) if v.annotation != inspect.Parameter.empty else "untyped"
                      for k, v in sig.parameters.items() if k != "tool_context"}
            funcs[name] = {
                "params": params,
                "has_docstring": bool(inspect.getdoc(obj)),
                "docstring_length": len(inspect.getdoc(obj) or ""),
                "has_tool_context": "tool_context" in sig.parameters,
                "param_count": len(params),
            }
    return funcs


def compare(student_info: dict, correction_info: dict, student_funcs: dict, correction_funcs: dict) -> list[CheckResult]:
    """Compare student code against correction and produce checks."""
    checks = []

    # 1. root_agent exists
    if not student_info["exists"]:
        checks.append(CheckResult(
            "root_agent", False, "error",
            "root_agent est None. Remplace `root_agent = None` par ta definition d'agent.",
            0, 5))
        return checks  # No point checking further
    checks.append(CheckResult("root_agent", True, "info", "root_agent est defini.", 5, 5))

    # 2. Agent type
    expected_type = correction_info["type"]
    actual_type = student_info["type"]
    if actual_type == expected_type:
        checks.append(CheckResult("agent_type", True, "info", f"Type correct: {actual_type}.", 3, 3))
    else:
        checks.append(CheckResult("agent_type", False, "error",
                                   f"Type attendu: {expected_type}, trouve: {actual_type}.", 0, 3))

    # 3. Agent name
    expected_name = correction_info["name"]
    actual_name = student_info["name"]
    if actual_name == expected_name:
        checks.append(CheckResult("name", True, "info", f"Nom correct: '{actual_name}'.", 1, 1))
    else:
        checks.append(CheckResult("name", False, "warning",
                                   f"Nom attendu: '{expected_name}', trouve: '{actual_name}'.", 0.5, 1))

    # 4. Model (skip for workflow agents)
    if expected_type in ("SequentialAgent", "ParallelAgent", "LoopAgent"):
        checks.append(CheckResult("model", True, "info",
                                   f"{expected_type} n'a pas besoin de model.", 1, 1))
    elif student_info["model"]:
        checks.append(CheckResult("model", True, "info", f"Model: {student_info['model']}.", 1, 1))
    else:
        checks.append(CheckResult("model", False, "error",
                                   "Pas de model. Ajoute model='gemini-2.5-flash'.", 0, 1))

    # 5. Instruction
    if expected_type in ("SequentialAgent", "ParallelAgent", "LoopAgent"):
        checks.append(CheckResult("instruction", True, "info", "Workflow agent, pas d'instruction.", 1, 1))
    elif student_info["instruction"]:
        checks.append(CheckResult("instruction", True, "info", "Instruction definie.", 1, 1))
    else:
        checks.append(CheckResult("instruction", False, "error",
                                   "Pas d'instruction. L'agent ne sait pas comment se comporter.", 0, 1))

    # 6. Functions defined
    for func_name in correction_funcs:
        if func_name in student_funcs:
            sf = student_funcs[func_name]
            cf = correction_funcs[func_name]

            # Function exists
            checks.append(CheckResult(f"func_{func_name}", True, "info",
                                       f"Fonction '{func_name}' definie.", 2, 2))

            # Docstring
            if sf["has_docstring"]:
                if sf["docstring_length"] >= 20:
                    checks.append(CheckResult(f"doc_{func_name}", True, "info",
                                               f"Docstring OK ({sf['docstring_length']} chars).", 1, 1))
                else:
                    checks.append(CheckResult(f"doc_{func_name}", False, "warning",
                                               f"Docstring trop courte ({sf['docstring_length']} chars). "
                                               "Le LLM a besoin d'une description claire.", 0.5, 1))
            else:
                checks.append(CheckResult(f"doc_{func_name}", False, "error",
                                           f"'{func_name}' n'a pas de docstring. "
                                           "Le LLM ne saura pas quand l'utiliser !", 0, 1))

            # Type hints
            untyped = [k for k, v in sf["params"].items() if v == "untyped"]
            if not untyped:
                checks.append(CheckResult(f"types_{func_name}", True, "info",
                                           "Tous les params ont des type hints.", 1, 1))
            else:
                checks.append(CheckResult(f"types_{func_name}", False, "warning",
                                           f"Params sans type hint: {', '.join(untyped)}.", 0.5, 1))

            # ToolContext if expected
            if cf["has_tool_context"] and not sf["has_tool_context"]:
                checks.append(CheckResult(f"ctx_{func_name}", False, "error",
                                           f"'{func_name}' devrait accepter tool_context: ToolContext.", 0, 1))
            elif cf["has_tool_context"] and sf["has_tool_context"]:
                checks.append(CheckResult(f"ctx_{func_name}", True, "info",
                                           "ToolContext present.", 1, 1))
        else:
            checks.append(CheckResult(f"func_{func_name}", False, "error",
                                       f"Fonction '{func_name}' manquante. "
                                       f"Cree-la avec les bons parametres.", 0, 2))

    # 7. Tools count
    expected_tools = correction_info["tool_count"]
    actual_tools = student_info["tool_count"]
    if actual_tools == expected_tools:
        checks.append(CheckResult("tool_count", True, "info",
                                   f"{actual_tools} tool(s) - correct.", 2, 2))
    elif actual_tools > 0:
        checks.append(CheckResult("tool_count", False, "warning",
                                   f"Attendu {expected_tools} tools, trouve {actual_tools}.", 1, 2))
    else:
        checks.append(CheckResult("tool_count", False, "error",
                                   f"Aucun tool. Attendu: {expected_tools}.", 0, 2))

    # 8. Sub-agents
    expected_subs = correction_info["sub_agent_count"]
    actual_subs = student_info["sub_agent_count"]
    if expected_subs > 0:
        if actual_subs == expected_subs:
            checks.append(CheckResult("sub_agents", True, "info",
                                       f"{actual_subs} sub-agents - correct.", 2, 2))
        elif actual_subs > 0:
            checks.append(CheckResult("sub_agents", False, "warning",
                                       f"Attendu {expected_subs} sub-agents, trouve {actual_subs}.", 1, 2))
        else:
            checks.append(CheckResult("sub_agents", False, "error",
                                       f"Aucun sub-agent. Attendu: {expected_subs}.", 0, 2))

    # 9. output_key
    if correction_info["output_key"]:
        if student_info["output_key"]:
            checks.append(CheckResult("output_key", True, "info",
                                       f"output_key='{student_info['output_key']}'.", 1, 1))
        else:
            checks.append(CheckResult("output_key", False, "warning",
                                       f"output_key manquant (attendu: '{correction_info['output_key']}').", 0, 1))

    # 10. Callbacks
    for cb in ["before_model_callback", "before_tool_callback", "after_model_callback"]:
        if correction_info[cb]:
            if student_info[cb]:
                checks.append(CheckResult(cb, True, "info", f"{cb} defini.", 2, 2))
            else:
                checks.append(CheckResult(cb, False, "error", f"{cb} manquant.", 0, 2))

    # 11. max_iterations (LoopAgent)
    if correction_info.get("max_iterations"):
        if student_info.get("max_iterations"):
            checks.append(CheckResult("max_iterations", True, "info",
                                       f"max_iterations={student_info['max_iterations']}.", 1, 1))
        else:
            checks.append(CheckResult("max_iterations", False, "warning",
                                       "max_iterations non defini. Risque de boucle infinie !", 0, 1))

    return checks


def validate_exercise(exercise_id: str) -> ExerciseResult:
    """Validate one exercise against its correction."""
    ex_dir = BASE_DIR / exercise_id
    correction_file = ex_dir / "correction.py"
    student_file = ex_dir / "agent.py"

    title_map = {
        "exercise_01": "Agent basique + 1 Tool",
        "exercise_02": "Plusieurs Tools",
        "exercise_03": "Runtime, Config & Artifacts",
        "exercise_04": "Session State & ToolContext",
        "exercise_05": "Delegation Multi-Agent",
        "exercise_06": "SequentialAgent",
        "exercise_07": "ParallelAgent",
        "exercise_08": "LoopAgent",
        "exercise_09": "Callbacks",
        "exercise_10": "Pipeline complet",
        "exercise_11": "Concepts avances",
    }
    title = title_map.get(exercise_id, exercise_id)
    result = ExerciseResult(exercise_id=exercise_id, title=title, import_ok=True)

    if not correction_file.exists():
        result.import_ok = False
        result.import_error = f"Correction file not found: {correction_file}"
        return result

    # Load correction
    corr_mod, corr_err = load_module(correction_file, f"_corr_{exercise_id}")
    if corr_err:
        result.import_ok = False
        result.import_error = f"Correction import error:\n{corr_err}"
        return result

    # Load student
    stud_mod, stud_err = load_module(student_file, f"_stud_{exercise_id}")
    if stud_err:
        result.import_ok = False
        result.import_error = f"Erreur d'import dans ton code:\n{stud_err}"
        return result

    # Extract info
    corr_info = get_agent_info(corr_mod)
    stud_info = get_agent_info(stud_mod)
    corr_funcs = get_functions(corr_mod)
    stud_funcs = get_functions(stud_mod)

    # Compare
    result.checks = compare(stud_info, corr_info, stud_funcs, corr_funcs)
    return result


def print_result(result: ExerciseResult):
    """Print a single exercise result to terminal."""
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}{BLUE}  {result.exercise_id.upper()} - {result.title}{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")

    if not result.import_ok:
        print(f"  {RED}ERREUR D'IMPORT:{RESET}")
        for line in result.import_error.splitlines()[-5:]:
            print(f"    {DIM}{line}{RESET}")
        print(f"\n  {BOLD}Score: 0% (F){RESET}")
        return

    for c in result.checks:
        if c.passed:
            icon = f"{GREEN}\u2713{RESET}"
        elif c.severity == "warning":
            icon = f"{YELLOW}\u26A0{RESET}"
        else:
            icon = f"{RED}\u2717{RESET}"
        pts = f"({c.points}/{c.max_points})"
        print(f"  {icon} {c.name:<30} {DIM}{pts:>8}{RESET}  {c.message}")

    grade = result.grade
    score = result.score
    label = result.grade_label
    color = GREEN if grade in ("A", "B") else YELLOW if grade == "C" else RED
    print(f"\n  {BOLD}Score: {color}{score}% ({grade} - {label}){RESET}")


def generate_html_report(results: list[ExerciseResult], output: Path):
    """Generate an HTML report from results."""
    rows = ""
    for r in results:
        color = "#3fb950" if r.grade in ("A","B") else "#d29922" if r.grade == "C" else "#f85149"
        checks_html = ""
        if r.import_ok:
            for c in r.checks:
                icon = "\u2713" if c.passed else "\u26A0" if c.severity == "warning" else "\u2717"
                c_color = "#3fb950" if c.passed else "#d29922" if c.severity == "warning" else "#f85149"
                checks_html += f'<tr><td style="color:{c_color}">{icon}</td><td>{c.name}</td><td>{c.points}/{c.max_points}</td><td>{c.message}</td></tr>'
        else:
            checks_html = f'<tr><td colspan="4" style="color:#f85149">Erreur d\'import: {r.import_error[-200:]}</td></tr>'

        rows += f"""
        <div class="exercise-card">
            <div class="exercise-header">
                <h3>{r.exercise_id.upper()} - {r.title}</h3>
                <span class="grade" style="color:{color}">{r.score}% ({r.grade})</span>
            </div>
            <table><thead><tr><th></th><th>Check</th><th>Points</th><th>Detail</th></tr></thead>
            <tbody>{checks_html}</tbody></table>
        </div>"""

    total_avg = sum(r.score for r in results) / len(results) if results else 0
    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>ADK Exercise Report</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; background: #0d1117; color: #e6edf3; padding: 2rem; }}
        .container {{ max-width: 800px; margin: 0 auto; }}
        h1 {{ color: #58a6ff; }} h3 {{ margin: 0; }}
        .summary {{ background: #161b22; padding: 1.5rem; border-radius: 8px; margin: 1rem 0; text-align: center; font-size: 1.5rem; }}
        .exercise-card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1rem; margin: 1rem 0; }}
        .exercise-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }}
        .grade {{ font-size: 1.2rem; font-weight: 700; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
        th {{ text-align: left; color: #8b949e; padding: 0.3rem; border-bottom: 1px solid #30363d; }}
        td {{ padding: 0.3rem; border-bottom: 1px solid #21262d; }}
    </style></head><body><div class="container">
    <h1>Code Forge - Rapport d'exercices</h1>
    <div class="summary">Moyenne: {total_avg:.0f}%</div>
    {rows}
    </div></body></html>"""

    output.write_text(html, encoding="utf-8")
    print(f"\n{GREEN}Rapport HTML genere: {output}{RESET}")


def main():
    args = sys.argv[1:]
    html_output = None
    exercise_ids = []

    # Parse args
    i = 0
    while i < len(args):
        if args[i] == "--html" and i + 1 < len(args):
            html_output = Path(args[i + 1])
            i += 2
        else:
            ex_id = args[i]
            if not ex_id.startswith("exercise_"):
                ex_id = f"exercise_{ex_id}"
            exercise_ids.append(ex_id)
            i += 1

    if not exercise_ids:
        exercise_ids = EXERCISES

    print(f"{BOLD}{BLUE}Code Forge - Validation des exercices{RESET}")
    print(f"{DIM}Comparing your code against corrections...{RESET}")

    results = []
    for ex_id in exercise_ids:
        result = validate_exercise(ex_id)
        results.append(result)
        print_result(result)

    # Summary
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}{BLUE}  RESUME{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")
    for r in results:
        color = GREEN if r.grade in ("A","B") else YELLOW if r.grade == "C" else RED
        bar = "\u2588" * int(r.score / 5) + "\u2591" * (20 - int(r.score / 5))
        print(f"  {r.exercise_id}: {color}{bar} {r.score:5.1f}% ({r.grade}){RESET}")

    avg = sum(r.score for r in results) / len(results) if results else 0
    print(f"\n  {BOLD}Moyenne: {avg:.0f}%{RESET}")

    if html_output:
        generate_html_report(results, html_output)


if __name__ == "__main__":
    main()
