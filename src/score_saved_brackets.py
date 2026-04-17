import pickle
from pathlib import Path

from Bracket_Score_Classes import Game
from runtime_paths import project_root


ROOT = project_root(__file__)
SAVED_BRACKETS_DIR = ROOT / "saved_brackets"

GROUND_TRUTH_FILE = "Results2025"


def load_bracket(filename: str):
    with open(SAVED_BRACKETS_DIR / filename, "rb") as file:
        return pickle.load(file)


def discover_player_files() -> list[str]:
    if not SAVED_BRACKETS_DIR.exists():
        return []
    return sorted(
        path.name
        for path in SAVED_BRACKETS_DIR.iterdir()
        if path.is_file() and path.name != GROUND_TRUTH_FILE
    )


def main() -> None:
    gt = load_bracket(GROUND_TRUTH_FILE)
    player_files = discover_player_files()
    if not player_files:
        print("No player brackets were found in saved_brackets/.")
        return

    players = [load_bracket(filename) for filename in player_files]
    max_score = len(gt.games) * Game.MAX_SCORE

    for player in players:
        score = player.calculate_score(gt)
        print(f"The score of {player.name}: {score}, {score * 100 / max_score:.2f}%")

    try:
        from graph import render_results
    except ModuleNotFoundError as exc:
        print(f"Skipping graph render: {exc}")
        return

    render_results([*players, gt])


if __name__ == "__main__":
    main()
