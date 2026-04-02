"""Exercise validator engine.

Imports student code, runs structural and behavioral checks,
produces a scored report with detailed error descriptions.
"""

import importlib
import inspect
import sys
import traceback
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable


class Severity(Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


@dataclass
class Check:
    name: str
    description: str
    severity: Severity
    message: str
    points: float = 0.0
    max_points: float = 0.0


@dataclass
class ExerciseReport:
    exercise: str
    title: str
    checks: list[Check] = field(default_factory=list)
    import_error: str | None = None

    @property
    def score(self) -> float:
        total = sum(c.max_points for c in self.checks)
        earned = sum(c.points for c in self.checks)
        return round(earned / total * 100, 1) if total > 0 else 0.0

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.severity == Severity.PASS)

    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if c.severity == Severity.FAIL)

    @property
    def warnings(self) -> int:
        return sum(1 for c in self.checks if c.severity == Severity.WARN)

    @property
    def grade(self) -> str:
        s = self.score
        if s >= 90:
            return "A"
        if s >= 75:
            return "B"
        if s >= 60:
            return "C"
        if s >= 40:
            return "D"
        return "F"


def load_exercise_module(exercise_dir: Path) -> tuple[Any, str | None]:
    """Import the exercise's agent.py module. Returns (module, error_string)."""
    agent_file = exercise_dir / "agent.py"
    if not agent_file.exists():
        return None, f"agent.py not found in {exercise_dir}"

    module_name = f"_validate_{exercise_dir.name}"
    # Remove cached version if any
    if module_name in sys.modules:
        del sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(module_name, str(agent_file))
    if spec is None or spec.loader is None:
        return None, f"Cannot create module spec for {agent_file}"

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        return module, None
    except Exception:
        return None, traceback.format_exc()


def check_root_agent_exists(module: Any) -> Check:
    """Verify root_agent is defined and not None."""
    agent = getattr(module, "root_agent", None)
    if agent is None:
        return Check(
            name="root_agent_exists",
            description="root_agent est defini et non None",
            severity=Severity.FAIL,
            message="root_agent est None ou absent. Remplace `root_agent = None` par `root_agent = Agent(...)`.",
            points=0, max_points=3,
        )
    return Check(
        name="root_agent_exists",
        description="root_agent est defini et non None",
        severity=Severity.PASS,
        message="root_agent est correctement defini.",
        points=3, max_points=3,
    )


def check_agent_name(module: Any, expected_name: str) -> Check:
    """Verify the agent has the expected name."""
    agent = getattr(module, "root_agent", None)
    if agent is None:
        return Check("agent_name", f"Agent nomme '{expected_name}'", Severity.SKIP,
                      "Skipped: root_agent absent.", 0, 1)
    actual = getattr(agent, "name", None)
    if actual == expected_name:
        return Check("agent_name", f"Agent nomme '{expected_name}'", Severity.PASS,
                      f"Nom correct: '{actual}'.", 1, 1)
    return Check("agent_name", f"Agent nomme '{expected_name}'", Severity.WARN,
                  f"Nom attendu '{expected_name}', trouve '{actual}'. Pas bloquant mais preferez le nom demande.",
                  0.5, 1)


def check_agent_has_model(module: Any) -> Check:
    """Verify the agent has a model set."""
    agent = getattr(module, "root_agent", None)
    if agent is None:
        return Check("has_model", "Agent a un model LLM", Severity.SKIP, "Skipped.", 0, 1)
    model = getattr(agent, "model", None)
    if model:
        return Check("has_model", "Agent a un model LLM", Severity.PASS,
                      f"Model: {model}", 1, 1)
    # Workflow agents (Sequential, Parallel, Loop) don't need a model
    agent_type = type(agent).__name__
    if agent_type in ("SequentialAgent", "ParallelAgent", "LoopAgent"):
        return Check("has_model", "Workflow agent (pas de model requis)", Severity.PASS,
                      f"{agent_type} n'a pas besoin de model.", 1, 1)
    return Check("has_model", "Agent a un model LLM", Severity.FAIL,
                  "Aucun model defini. Ajoute model='gemini-2.5-flash'.", 0, 1)


def check_agent_has_instruction(module: Any) -> Check:
    """Verify the agent has an instruction."""
    agent = getattr(module, "root_agent", None)
    if agent is None:
        return Check("has_instruction", "Agent a une instruction", Severity.SKIP, "Skipped.", 0, 1)
    instruction = getattr(agent, "instruction", None)
    agent_type = type(agent).__name__
    if agent_type in ("SequentialAgent", "ParallelAgent", "LoopAgent"):
        return Check("has_instruction", "Workflow agent (pas d'instruction requise)", Severity.PASS,
                      f"{agent_type} n'a pas besoin d'instruction.", 1, 1)
    if instruction:
        return Check("has_instruction", "Agent a une instruction", Severity.PASS,
                      "Instruction definie.", 1, 1)
    return Check("has_instruction", "Agent a une instruction", Severity.FAIL,
                  "Pas d'instruction. L'agent ne saura pas comment se comporter.", 0, 1)


def check_agent_has_tools(module: Any, expected_count: int | None = None) -> Check:
    """Verify the agent has tools."""
    agent = getattr(module, "root_agent", None)
    if agent is None:
        return Check("has_tools", "Agent a des tools", Severity.SKIP, "Skipped.", 0, 2)
    tools = getattr(agent, "tools", None) or []
    agent_type = type(agent).__name__
    # Workflow agents check sub_agents instead
    if agent_type in ("SequentialAgent", "ParallelAgent", "LoopAgent"):
        sub = getattr(agent, "sub_agents", None) or []
        if sub:
            return Check("has_tools", "Workflow agent a des sub_agents", Severity.PASS,
                          f"{len(sub)} sub-agents.", 2, 2)
        return Check("has_tools", "Workflow agent a des sub_agents", Severity.FAIL,
                      "Aucun sub_agent. Le workflow n'a rien a executer.", 0, 2)
    if not tools:
        return Check("has_tools", "Agent a des tools", Severity.FAIL,
                      "Aucun tool. Ajoute tools=[...] avec tes fonctions.", 0, 2)
    if expected_count and len(tools) != expected_count:
        return Check("has_tools", f"Agent a {expected_count} tools", Severity.WARN,
                      f"Attendu {expected_count} tools, trouve {len(tools)}.", 1, 2)
    return Check("has_tools", "Agent a des tools", Severity.PASS,
                  f"{len(tools)} tool(s) defini(s).", 2, 2)


def check_function_exists(module: Any, func_name: str, points: float = 2.0) -> Check:
    """Verify a function is defined in the module."""
    func = getattr(module, func_name, None)
    if func is None or not callable(func):
        return Check(f"func_{func_name}", f"Fonction '{func_name}' existe",
                      Severity.FAIL,
                      f"Fonction '{func_name}' non trouvee. Definis-la dans agent.py.",
                      0, points)
    return Check(f"func_{func_name}", f"Fonction '{func_name}' existe",
                  Severity.PASS, f"'{func_name}' est definie.", points, points)


def check_function_has_docstring(module: Any, func_name: str) -> Check:
    """Verify a function has a docstring."""
    func = getattr(module, func_name, None)
    if func is None or not callable(func):
        return Check(f"docstring_{func_name}", f"'{func_name}' a une docstring",
                      Severity.SKIP, "Skipped: fonction absente.", 0, 1)
    doc = inspect.getdoc(func)
    if doc and len(doc) > 10:
        return Check(f"docstring_{func_name}", f"'{func_name}' a une docstring",
                      Severity.PASS, "Docstring presente et descriptive.", 1, 1)
    if doc:
        return Check(f"docstring_{func_name}", f"'{func_name}' a une docstring",
                      Severity.WARN, "Docstring trop courte. Le LLM a besoin de plus de contexte.", 0.5, 1)
    return Check(f"docstring_{func_name}", f"'{func_name}' a une docstring",
                  Severity.FAIL,
                  "Pas de docstring ! Le LLM ne saura pas quand utiliser ce tool.", 0, 1)


def check_function_has_type_hints(module: Any, func_name: str, expected_params: dict[str, type] | None = None) -> Check:
    """Verify a function has type hints on its parameters."""
    func = getattr(module, func_name, None)
    if func is None or not callable(func):
        return Check(f"hints_{func_name}", f"'{func_name}' a des type hints",
                      Severity.SKIP, "Skipped: fonction absente.", 0, 1)
    sig = inspect.signature(func)
    hints = {k: v.annotation for k, v in sig.parameters.items()
             if v.annotation != inspect.Parameter.empty and k != "tool_context"}
    params_without = [k for k, v in sig.parameters.items()
                      if v.annotation == inspect.Parameter.empty and k != "tool_context"]
    if params_without:
        return Check(f"hints_{func_name}", f"'{func_name}' a des type hints",
                      Severity.WARN,
                      f"Parametres sans type hint: {', '.join(params_without)}. Le LLM utilise les types pour le schema.",
                      0.5, 1)
    return Check(f"hints_{func_name}", f"'{func_name}' a des type hints",
                  Severity.PASS, "Tous les parametres ont des type hints.", 1, 1)


def check_function_returns_dict(module: Any, func_name: str, test_args: dict | None = None) -> Check:
    """Call the function with test args and verify it returns a dict."""
    func = getattr(module, func_name, None)
    if func is None or not callable(func):
        return Check(f"returns_{func_name}", f"'{func_name}' retourne un dict",
                      Severity.SKIP, "Skipped: fonction absente.", 0, 1)
    if test_args is None:
        return Check(f"returns_{func_name}", f"'{func_name}' retourne un dict",
                      Severity.SKIP, "Skipped: pas d'arguments de test.", 0, 1)
    try:
        # Filter out tool_context from test_args if function doesn't accept it
        sig = inspect.signature(func)
        has_tool_context = "tool_context" in sig.parameters
        filtered_args = {k: v for k, v in test_args.items() if k != "tool_context" or has_tool_context}
        result = func(**filtered_args)
        if isinstance(result, dict):
            if "status" in result:
                return Check(f"returns_{func_name}", f"'{func_name}' retourne un dict",
                              Severity.PASS, f"Retourne un dict avec status='{result['status']}'.", 1, 1)
            return Check(f"returns_{func_name}", f"'{func_name}' retourne un dict",
                          Severity.WARN, "Retourne un dict mais sans cle 'status'. Recommande: ajoute \"status\": \"success\".",
                          0.5, 1)
        return Check(f"returns_{func_name}", f"'{func_name}' retourne un dict",
                      Severity.FAIL, f"Retourne {type(result).__name__} au lieu d'un dict.", 0, 1)
    except TypeError as e:
        return Check(f"returns_{func_name}", f"'{func_name}' retourne un dict",
                      Severity.FAIL, f"Erreur d'appel: {e}. Verifie la signature.", 0, 1)
    except Exception as e:
        return Check(f"returns_{func_name}", f"'{func_name}' retourne un dict",
                      Severity.WARN, f"Exception lors de l'appel: {e}", 0.5, 1)


def check_agent_has_output_key(module: Any) -> Check:
    """Check if agent has output_key set."""
    agent = getattr(module, "root_agent", None)
    if agent is None:
        return Check("output_key", "output_key defini", Severity.SKIP, "Skipped.", 0, 1)
    ok = getattr(agent, "output_key", None)
    if ok:
        return Check("output_key", "output_key defini", Severity.PASS,
                      f"output_key='{ok}'.", 1, 1)
    return Check("output_key", "output_key defini", Severity.FAIL,
                  "Pas d'output_key. La reponse de l'agent ne sera pas sauvegardee dans le state.", 0, 1)


def check_agent_has_sub_agents(module: Any, expected_count: int | None = None) -> Check:
    """Check if agent has sub_agents."""
    agent = getattr(module, "root_agent", None)
    if agent is None:
        return Check("sub_agents", "sub_agents definis", Severity.SKIP, "Skipped.", 0, 2)
    subs = getattr(agent, "sub_agents", None) or []
    if not subs:
        return Check("sub_agents", "sub_agents definis", Severity.FAIL,
                      "Aucun sub_agent. Ajoute sub_agents=[...] avec tes agents specialises.", 0, 2)
    if expected_count and len(subs) != expected_count:
        return Check("sub_agents", f"{expected_count} sub_agents attendus", Severity.WARN,
                      f"Attendu {expected_count}, trouve {len(subs)}.", 1, 2)
    names = [getattr(s, "name", "?") for s in subs]
    return Check("sub_agents", "sub_agents definis", Severity.PASS,
                  f"{len(subs)} sub-agents: {', '.join(names)}.", 2, 2)


def check_agent_type(module: Any, expected_type: str) -> Check:
    """Check root_agent is of the expected type."""
    agent = getattr(module, "root_agent", None)
    if agent is None:
        return Check("agent_type", f"root_agent est un {expected_type}", Severity.SKIP, "Skipped.", 0, 2)
    actual = type(agent).__name__
    if actual == expected_type:
        return Check("agent_type", f"root_agent est un {expected_type}", Severity.PASS,
                      f"Correct: {actual}.", 2, 2)
    return Check("agent_type", f"root_agent est un {expected_type}", Severity.FAIL,
                  f"Attendu {expected_type}, trouve {actual}.", 0, 2)


def check_agent_has_callbacks(module: Any, callback_names: list[str]) -> Check:
    """Check if agent has specific callbacks defined."""
    agent = getattr(module, "root_agent", None)
    if agent is None:
        return Check("callbacks", "Callbacks definis", Severity.SKIP, "Skipped.", 0, 2)
    missing = []
    found = []
    for cb_name in callback_names:
        cb = getattr(agent, cb_name, None)
        if cb:
            found.append(cb_name)
        else:
            missing.append(cb_name)
    if not missing:
        return Check("callbacks", "Callbacks definis", Severity.PASS,
                      f"Tous presents: {', '.join(found)}.", 2, 2)
    if found:
        return Check("callbacks", "Callbacks definis", Severity.WARN,
                      f"Manquants: {', '.join(missing)}. Trouves: {', '.join(found)}.", 1, 2)
    return Check("callbacks", "Callbacks definis", Severity.FAIL,
                  f"Aucun callback trouve. Attendus: {', '.join(callback_names)}.", 0, 2)


def check_instruction_uses_state_var(module: Any, var_name: str) -> Check:
    """Check if agent instruction contains {var_name} templating."""
    agent = getattr(module, "root_agent", None)
    if agent is None:
        return Check(f"state_var_{var_name}", f"Instruction utilise {{{var_name}}}", Severity.SKIP, "Skipped.", 0, 1)
    instruction = getattr(agent, "instruction", "") or ""
    if callable(instruction):
        return Check(f"state_var_{var_name}", f"Instruction dynamique (callable)", Severity.PASS,
                      "Instruction est un callable - verification manuelle requise.", 1, 1)
    if f"{{{var_name}}}" in instruction:
        return Check(f"state_var_{var_name}", f"Instruction utilise {{{var_name}}}", Severity.PASS,
                      f"Trouve {{{var_name}}} dans l'instruction.", 1, 1)
    return Check(f"state_var_{var_name}", f"Instruction utilise {{{var_name}}}", Severity.WARN,
                  f"{{{var_name}}} absent de l'instruction. L'agent ne verra pas cette donnee du state.", 0, 1)
