import pickle
from pathlib import Path

from Bracket_Score_Classes import Bracket2025
from runtime_paths import project_root


ROOT = project_root(__file__)
SAVED_BRACKETS_DIR = ROOT / "saved_brackets"

BRACKET_TARGETS = (("Results2025", "Results2025"),) + tuple(
    (f"Player {index}", f"Player{index}_2025") for index in range(1, 5)
)


def save_bracket(bracket: Bracket2025, filename: str) -> None:
    SAVED_BRACKETS_DIR.mkdir(parents=True, exist_ok=True)
    with open(SAVED_BRACKETS_DIR / filename, "wb") as file:
        pickle.dump(bracket, file)


def fill_brackets() -> None:
    for display_name, filename in BRACKET_TARGETS:
        bracket = Bracket2025(display_name)
        bracket.fill()
        save_bracket(bracket, filename)


if __name__ == "__main__":
    fill_brackets()
