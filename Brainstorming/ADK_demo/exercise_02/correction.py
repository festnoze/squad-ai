"""Corrige exercice 2 - Agent avec plusieurs outils."""

from google.adk.agents import Agent


def save_solution(equation: str, solution: str, steps: list[str]) -> dict:
    """Saves the solution of a math equation with step-by-step breakdown.

    Args:
        equation: The original equation.
        solution: The final answer.
        steps: List of resolution steps.

    Returns:
        Dictionary with save confirmation.
    """
    return {
        "status": "success",
        "message": f"Solution for '{equation}' saved ({len(steps)} steps)",
        "equation": equation,
        "solution": solution,
    }


def save_explanation(concept: str, explanation: str) -> dict:
    """Saves a math concept explanation for the student.

    Args:
        concept: The mathematical concept being explained.
        explanation: The detailed explanation.

    Returns:
        Dictionary with save confirmation.
    """
    return {
        "status": "success",
        "message": f"Explanation for '{concept}' saved",
        "word_count": len(explanation.split()),
    }


def generate_quiz(difficulty: str, question_count: int = 3) -> dict:
    """Generates a math quiz at the specified difficulty level.

    Args:
        difficulty: The difficulty level: "easy", "medium", or "hard".
        question_count: Number of questions to generate. Defaults to 3.

    Returns:
        Dictionary with quiz questions.
    """
    quizzes = {
        "easy": ["What is 2 + 2?", "What is 10 - 3?", "What is 5 x 2?"],
        "medium": ["Solve: 3x + 5 = 20", "What is sqrt(144)?", "What is 15% of 200?"],
        "hard": ["Find the derivative of x^3 + 2x", "Solve: x^2 - 5x + 6 = 0", "What is the integral of 2x dx?"],
    }
    questions = quizzes.get(difficulty.lower(), quizzes["medium"])[:question_count]
    return {
        "status": "success",
        "difficulty": difficulty,
        "questions": questions,
        "question_count": len(questions),
    }


root_agent = Agent(
    name="math_tutor",
    model="gemini-2.5-flash",
    description="A math tutor that solves equations, explains concepts, and generates quizzes.",
    instruction=(
        "You are a patient math tutor with three capabilities:\n"
        "1. Solve equations: work through the solution yourself, then use save_solution to record it\n"
        "2. Explain concepts: explain in simple terms, then use save_explanation to record it\n"
        "3. Generate quizzes: use generate_quiz with the requested difficulty\n\n"
        "Choose the right tool based on the student's request."
    ),
    tools=[save_solution, save_explanation, generate_quiz],
)
