# Bracket Score

Bracket Score is a local NBA playoff bracket project for filling brackets, saving them, comparing them, and showing a score graph. The current web frontend was polished with help from Codex.

## What Is In This Folder

- `BracketScoreGUI.exe`: starts the local web app.
- `FillBrackets.exe`: opens the terminal version and saves bracket picks into `saved_brackets/`.
- `ScoreSavedBrackets.exe`: scores the saved brackets that are already in `saved_brackets/`.
- `saved_brackets/`: where bracket files are stored.
- `NBA logos/`: team logos used by the web app.

## Important

- This is meant for **Windows**.
- The `.exe` files already include the Python libraries from `requirements.txt`, so your friends do not need to install Python, `matplotlib`, or `networkx`.
- Do **not** run the `.exe` files from inside the ZIP file.
- Do **not** move the `.exe` files out of this project folder. They expect the `saved_brackets/` and `NBA logos/` folders to stay beside them.
- The web app runs only on your own computer through a local address called loopback or localhost.

## Easy Setup For Friends

You do **not** need to use Command Prompt, Terminal, or install Python.

1. Go to the GitHub page for this project.
2. Click the green **Code** button.
3. Click **Download ZIP**.
4. When the download finishes, find the ZIP file in your Downloads folder.
5. Right-click the ZIP file and choose **Extract All...**
6. Open the extracted folder.
7. Make sure you can see the folders `saved_brackets` and `NBA logos`, plus the `.exe` files in the same main folder.

## How To Open The Web App

1. In the main folder, double-click `BracketScoreGUI.exe`.
2. A black window should open and stay open. Leave that window open while you use the app.
3. Open your web browser yourself.
4. Click the address bar and type: `http://127.0.0.1:8765/`
5. Press Enter.
6. The Bracket Score page should appear in your browser.

If Windows shows a security warning, click **More info** and then **Run anyway** only if you trust the GitHub download.

## How To Stop The Web App

1. Go back to the black window that opened when you launched `BracketScoreGUI.exe`.
2. Type `q`
3. Press Enter

## Other `.exe` Files

### `FillBrackets.exe`

Use this if you want the classic terminal version. It asks questions in a black window and saves the bracket files into `saved_brackets/`.

### `ScoreSavedBrackets.exe`

Use this if you want to score the saved bracket files that already exist in `saved_brackets/`.

## Notes

- The web app works locally on your computer. It is not a public website.
- The loopback address `127.0.0.1` means “this computer.”
- If the page does not open, first check that `BracketScoreGUI.exe` is still running and that the black window did not close.
