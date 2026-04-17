# Bracket Score

Bracket Score is a local NBA playoffs bracket application for filling brackets, saving them, comparing results, and visualizing scores. It is designed for people who enjoy building and experimenting with custom NBA playoff bracket scoring methods.

## Who This Is For

- Anyone who wants to run the bracket app locally with no technical knowledge required.
- Anyone who wants to experiment with custom scoring rules for NBA playoff brackets.
- Anyone who wants a lightweight local tool rather than a hosted website.

## What Is Included

- `BracketScoreGUI.exe`: launches the local web app.
- `FillBrackets.exe`: runs the terminal-based bracket entry flow and saves bracket files into `saved_brackets/`.
- `ScoreSavedBrackets.exe`: scores the saved bracket files in `saved_brackets/`.
- `saved_brackets/`: stores bracket pickle files.
- `NBA logos/`: logo assets used by the local web app.

## Important Notes

- This project is intended for **Windows** when using the included `.exe` files.
- No Python installation or command-line knowledge is required to run the packaged `.exe` files.
- The `.exe` files already include the Python libraries from `requirements.txt`, including `matplotlib` and `networkx`.
- Do **not** run the `.exe` files from inside a ZIP file.
- Keep the `.exe` files in the main project folder beside `saved_brackets/` and `NBA logos/`.
- The web app runs only on your own computer through the local loopback address.

## Running The App Without Technical Setup

1. Open the GitHub page for the project.
2. Click the green **Code** button.
3. Click **Download ZIP**.
4. After the download finishes, find the ZIP file in your Downloads folder.
5. Right-click the ZIP file and choose **Extract All...**
6. Open the extracted folder.
7. Confirm that the main folder contains the `.exe` files, the `saved_brackets` folder, and the `NBA logos` folder.

## Opening The Web App

1. Double-click `BracketScoreGUI.exe`.
2. A black window should open and stay open while the server is running.
3. Open your web browser manually.
4. In the browser address bar, enter `http://127.0.0.1:8765/`
5. Press Enter.
6. The Bracket Score interface should load in the browser.

If Windows shows a security warning, click **More info** and then **Run anyway** only if you trust the source of the download.

## Stopping The Web App

1. Return to the black window opened by `BracketScoreGUI.exe`.
2. Type `q`
3. Press Enter

## Other Launchers

### `FillBrackets.exe`

Launches the terminal version of the bracket entry flow and saves bracket files into `saved_brackets/`.

### `ScoreSavedBrackets.exe`

Loads `Results2025` from `saved_brackets/`, then scores every other saved bracket file against it.

## Customizing The Scoring Method

The simplest place to customize the scoring logic is [`Game.calculate_score()`](src/Bracket_Score_Classes.py) in `src/Bracket_Score_Classes.py`.

- `Game.calculate_score()` defines how a **single playoff series** is scored.
- [`Bracket.calculate_score()`](src/Bracket_Score_Classes.py) sums those per-series scores across the full bracket.

In the current implementation, the default scoring logic awards points for:

- predicting the correct winner side (`team1` vs `team2`) - 1 point
- predicting the correct winning team - 1 point
- predicting the correct series length - 1 point
- awarding a full perfect-series score when all series details match - 4 points

If you want a different scoring philosophy, this is the main method to edit.

## Technical Setup

If you prefer to run the project from source, clone the repository and install the dependencies from `requirements.txt`.

```bash
git clone https://github.com/KenziVisor/NBA-Playoffs-Bracket.git
cd Bracket_Score
pip install -r requirements.txt
python src/gui.py
```

Then open your browser and go to:

`http://127.0.0.1:8765/`

Other source entry points:

- `python src/fill.py`
- `python src/score_saved_brackets.py`

## Developer Notes

- Scoring logic: `src/Bracket_Score_Classes.py`
- 2025 bracket structure and first-round matchups: `Bracket2025` in `src/Bracket_Score_Classes.py`
- Local web UI server: `src/gui.py`
- Graph rendering: `src/graph.py`

## Local-Only Reminder

- The app is not deployed to the internet.
- `127.0.0.1` means “this computer only.”
- If the page does not open, first check that `BracketScoreGUI.exe` is still running and that the black window has not been closed.
