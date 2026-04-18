# Project Memory

- Entry points:
  - `Bracket_Score_Classes.py` defines `Game`, the abstract `Bracket` flow, and year-specific bracket classes such as `Bracket2025` and `Bracket2026`.
  - `src/score_saved_brackets.py` loads saved bracket pickles from `saved_brackets/`, prints scores against the results bracket, and asks `graph.py` to render the comparison graph when graph dependencies are installed.
  - `src/fill.py` runs the interactive terminal bracket-filling flow and saves the standard five pickle files into `saved_brackets/`.
  - `src/gui.py` runs a local single-file web UI with three tabs: fill a fresh bracket, compare two uploaded pickles, or render a graph from 3+ uploaded pickles.

- Runtime assumptions:
  - Python entry points live under `src/`, while saved pickle files live under `saved_brackets/` and logo assets live at the repo root in `NBA logos/`.
  - `src/score_saved_brackets.py` expects `Results2025` to exist in `saved_brackets/`, then scores every other pickle file there against it.
  - Graph rendering depends only on `matplotlib`; `src/gui.py` can still run its fill and compare tabs without it, but the graph tab needs the packages from `requirements.txt`.
  - The graph path is intentionally `Agg`-only and avoids both `pyplot` and `networkx` so Windows one-file builds stay small and do not pull in interactive backends.
  - Team logo assets currently live in `NBA logos/`, even though future code should also tolerate a `logos/` directory.
  - Saved 2025 pickles still deserialize through the top-level module name `Bracket_Score_Classes`, so code that loads them needs `src/` on the Python import path.
  - `src/gui.py` is stdlib-only apart from the optional graph dependencies, can skip auto-opening the browser with `--no-browser`, and keeps the terminal open for `q`/`quit` shutdown commands.
  - Frozen Windows builds need to resolve the project root from `sys.executable`; otherwise one-file executables read and write against PyInstaller's temp extraction directory instead of the extracted repo folder.

- Data contract:
  - Saved brackets are pickle files containing year-specific `Bracket_Score_Classes` bracket objects such as `Bracket2025` and `Bracket2026`.
  - Scoring depends on the exact order of `games`: 8 first-round series, then 4 conference semifinals, then 2 conference finals, then 1 finals series.
  - Scoring is series-by-series against the ground truth: correct winner side (`team1` vs `team2`) = 1 point, correct winner identity = 1 point, and exact series length = 1 point; a perfect series is worth 4 and the perfect bracket score is 60.
  - The only reserved saved-bracket filename is `Results2025`; any other pickle filename in `saved_brackets/` is treated as a player bracket when scoring.
  - Downstream rounds are built by pairing adjacent winners within each conference, so first-round matchup order is part of the bracket definition.
  - The GUI fill flow is bracket-class driven: it instantiates a bracket class from the selected year, and future subclasses such as `Bracket2026` should keep the same ordered-game contract so the fill board can render them.
  - `src/gui.py` exposes bracket years through `BRACKET_CLASSES_BY_YEAR`; adding a new bracket subclass to the GUI means registering it there, and the year picker should default to the latest configured year.

- Important decision:
  - `Bracket2025` now inherits from a generic `Bracket` base and provides only the ordered 2025 first-round matchups.
  - Keep the module path/class name `Bracket_Score_Classes.Bracket2025` stable if you want old pickle files to stay loadable.
  - Do not delete and rewrite an entire script just to make changes; prefer targeted in-place edits, and only replace a whole file if the user explicitly asks for that kind of rewrite.
