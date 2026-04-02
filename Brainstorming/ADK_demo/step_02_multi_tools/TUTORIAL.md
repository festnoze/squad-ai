# Step 2 - Plusieurs outils sur un meme agent

## Concepts

### Selection de tool par le LLM
Quand un agent a plusieurs tools, le LLM **choisit** lequel appeler en se basant sur :
1. Le **nom** de chaque fonction
2. La **docstring** de chaque fonction
3. Les **parametres** (noms + types)

Le LLM recoit le schema de TOUS les tools et decide lequel est pertinent pour la requete.

### Pourquoi les docstrings sont critiques
```python
# MAUVAIS - le LLM ne sait pas quand utiliser ce tool
def process(x):
    return x

# BON - le LLM comprend exactement quand l'appeler
def analyze_code_complexity(code: str) -> dict:
    """Analyzes the cyclomatic complexity of a given Python code snippet.

    Args:
        code: The Python source code to analyze.

    Returns:
        A dictionary with complexity metrics.
    """
```

### Tool sans parametre
Une fonction sans argument est un tool valide :
```python
def list_code_templates() -> dict:
    """Lists all available Python code templates."""
    return {"status": "success", "templates": [...]}
```

## Exploration

Ouvre [agent.py](agent.py) et observe :
1. Les 3 tools : `save_code_snippet`, `analyze_code_complexity`, `list_code_templates`
2. Comment `tools=[...]` contient les 3 fonctions
3. L'instruction qui decrit les 3 capacites

## Prompts de test

Lance `adk web` -> `step_02_multi_tools` :

| Prompt | Tool attendu | Quoi observer |
|--------|-------------|---------------|
| "Write a sorting function" | `save_code_snippet` | Le LLM ecrit le code lui-meme puis le sauvegarde via le tool |
| "How complex is this code: def add(a,b): return a+b" | `analyze_code_complexity` | Le tool analyse le code passe en parametre |
| "What templates do you have?" | `list_code_templates` | Tool appele SANS parametre, retourne la liste statique |
| "Write a function and then analyze its complexity" | Les DEUX tools | Le LLM chaine 2 appels de tools dans le meme tour |

## Exercice

**Mission** : Creer un agent `math_tutor` avec 3 outils mathematiques.

Ouvre `exercise_02/agent.py` et complete les `# TODO`.

Tu dois creer :
1. `solve_equation(equation: str) -> dict` - resout une equation (mock)
2. `explain_concept(concept: str) -> dict` - explique un concept math
3. `generate_quiz(difficulty: str) -> dict` - genere un quiz (difficulty: "easy", "medium", "hard")

Puis un `root_agent` nomme `"math_tutor"` avec les 3 tools.

Teste :
- "Solve x + 5 = 12"
- "Explain what a derivative is"
- "Give me a hard quiz"
