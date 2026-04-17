from __future__ import annotations

import argparse
import base64
import html
import io
import json
import math
import mimetypes
import os
import pickle
import re
import sys
import threading
import urllib.parse
import webbrowser
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from Bracket_Score_Classes import Bracket, Bracket2025, Game
from runtime_paths import project_root


SRC_DIR = Path(__file__).resolve().parent
ROOT = project_root(__file__)
SAVED_BRACKETS_DIR = ROOT / "saved_brackets"
LOGO_DIR_CANDIDATES = (ROOT / "logos", ROOT / "NBA logos")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

CARD_W = 248
CARD_H = 118
ROUND_GAP = 220
TOP_MARGIN = 54
ROW_GAP = 138
SIDE_MARGIN = 44
BOARD_PADDING_BOTTOM = 76
BOARD_PADDING_RIGHT = 48

FALLBACK_LOGO = "_NBA_logo.png"

ROUND_COLORS = [
    "#c9ff2f",
    "#66d0ff",
    "#ffbc57",
    "#ff6b8b",
]


@dataclass
class PlanNode:
    key: tuple[str, int, int]
    round_index: int
    round_name: str
    conference: str
    side: str
    x: float
    y: float
    children_keys: tuple[tuple[str, int, int], tuple[str, int, int]] | None = None
    parent_key: tuple[str, int, int] | None = None
    index: int = -1


@dataclass
class BracketPlan:
    nodes: list[PlanNode]
    round_ranges: list[tuple[int, int]]
    round_names: list[str]
    conference_order: list[str]
    first_round_games_per_conference: int
    board_width: int
    board_height: int


STATE_LOCK = threading.Lock()
BRACKET_CLASSES_BY_YEAR: dict[int, type[Bracket]] = {
    2025: Bracket2025,
}
STATE: dict[str, Any] = {
    "loaded": False,
    "message": "Choose a bracket year to begin.",
    "error": "",
    "filename": "",
    "bracket": None,
    "plan": None,
    "active_round_index": None,
    "complete": False,
    "bracket_class": "",
    "bracket_name": "",
}


def resolve_logo_dir() -> Path:
    for candidate in LOGO_DIR_CANDIDATES:
        if candidate.exists():
            return candidate
    return LOGO_DIR_CANDIDATES[-1]


LOGO_DIR = resolve_logo_dir()


def unique_in_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def safe_text(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def normalize_team_key(team: str) -> str:
    cleaned = "".join(ch.lower() for ch in team if ch.isalnum())
    aliases = {
        "okc": "thunder",
        "thunder": "thunder",
        "memphis": "grizzlies",
        "grizzlies": "grizzlies",
        "denver": "nuggets",
        "nuggets": "nuggets",
        "laclippers": "clippers",
        "clippers": "clippers",
        "lalakers": "lakers",
        "lakers": "lakers",
        "minnesota": "timberwolves",
        "timberwolves": "timberwolves",
        "houston": "rockets",
        "rockets": "rockets",
        "gsw": "warriors",
        "warriors": "warriors",
        "cleavland": "cavaliers",
        "cleveland": "cavaliers",
        "cavaliers": "cavaliers",
        "miamiheat": "heat",
        "heat": "heat",
        "indiana": "pacers",
        "pacers": "pacers",
        "milwaukee": "bucks",
        "bucks": "bucks",
        "knicks": "knicks",
        "pistons": "pistons",
        "bostonceltics": "celtics",
        "celtics": "celtics",
        "orlando": "magic",
        "magic": "magic",
    }
    return aliases.get(cleaned, cleaned)


def logo_for_team(team: str) -> str:
    key = normalize_team_key(team)
    mapping = {
        "thunder": "thunder.png",
        "grizzlies": "grizzlies.png",
        "nuggets": "nuggets.png",
        "clippers": "clippers.png",
        "lakers": "lakers.png",
        "timberwolves": "timberwolves.png",
        "rockets": "rockets.png",
        "warriors": "warriors.png",
        "cavaliers": "cavaliers.png",
        "heat": "heat.png",
        "pacers": "pacers.png",
        "bucks": "bucks.png",
        "knicks": "knicks.png",
        "pistons": "pistons.png",
        "celtics": "celtics.png",
        "magic": "magic.png",
    }
    return mapping.get(key, FALLBACK_LOGO)


def is_game_complete(game: Game) -> bool:
    if not game.team1 or not game.team2:
        return False
    if game.winner not in {game.team1, game.team2}:
        return False
    if not isinstance(game.num_games, int):
        return False
    if game.num_games < 4 or game.num_games > 7:
        return False
    return True


def game_to_payload(game: Game, node: PlanNode, actual: bool, editable: bool) -> dict[str, Any]:
    team1 = game.team1 if actual else ""
    team2 = game.team2 if actual else ""
    return {
        "index": node.index,
        "round_index": node.round_index,
        "round_name": node.round_name,
        "conference": node.conference,
        "x": node.x,
        "y": node.y,
        "w": CARD_W,
        "h": CARD_H,
        "side": node.side,
        "actual": actual,
        "editable": editable,
        "placeholder": not actual,
        "team1": team1,
        "team2": team2,
        "team1_logo": logo_for_team(team1) if team1 else FALLBACK_LOGO,
        "team2_logo": logo_for_team(team2) if team2 else FALLBACK_LOGO,
        "winner": game.winner if actual else "",
        "num_games": game.num_games if actual else 0,
        "complete": is_game_complete(game) if actual else False,
        "series_label": f"{game.winner} in {game.num_games}" if actual and is_game_complete(game) else "",
    }


def available_bracket_years() -> list[int]:
    return sorted(BRACKET_CLASSES_BY_YEAR)


def create_bracket_for_year(year: int) -> Bracket:
    bracket_class = BRACKET_CLASSES_BY_YEAR.get(year)
    if bracket_class is None:
        raise ValueError(f"Bracket year {year} is not available.")
    return bracket_class()


def bracket_year_for(bracket: Any) -> int | None:
    for year, bracket_class in BRACKET_CLASSES_BY_YEAR.items():
        if isinstance(bracket, bracket_class):
            return year

    match = re.search(r"(\d{4})$", bracket.__class__.__name__)
    if match:
        return int(match.group(1))
    return None


def load_pickled_bracket(data: bytes, fallback_name: str = "") -> Any:
    try:
        bracket = pickle.loads(data)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Could not read bracket pickle: {exc}") from exc

    if not hasattr(bracket, "games"):
        raise ValueError("The uploaded file does not look like a bracket object.")

    games = getattr(bracket, "games")
    if not isinstance(games, list) or not games:
        raise ValueError("The uploaded bracket contains no games.")

    if not str(getattr(bracket, "name", "")).strip() and fallback_name:
        bracket.name = Path(fallback_name).stem
    return bracket


def load_uploaded_brackets(file_entries: list[dict[str, Any]], *, minimum: int | None = None, exact: int | None = None) -> list[Any]:
    if exact is not None and len(file_entries) != exact:
        raise ValueError(f"Please upload exactly {exact} bracket pickle files.")
    if minimum is not None and len(file_entries) < minimum:
        raise ValueError(f"Please upload at least {minimum} bracket pickle files.")

    brackets: list[Any] = []
    for entry in file_entries:
        if not isinstance(entry, dict):
            raise ValueError("Each uploaded file payload must be an object.")
        encoded = entry.get("data")
        filename = str(entry.get("name", "")).strip()
        if not isinstance(encoded, str) or not encoded:
            raise ValueError("Each uploaded file must include encoded pickle data.")
        try:
            raw = base64.b64decode(encoded.encode("ascii"), validate=True)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Could not decode {filename or 'uploaded file'}: {exc}") from exc
        brackets.append(load_pickled_bracket(raw, fallback_name=filename))
    return brackets


def bracket_label(bracket: Any, fallback: str = "Bracket") -> str:
    label = str(getattr(bracket, "name", "")).strip()
    return label or fallback


def max_bracket_score(bracket: Any) -> int:
    return len(getattr(bracket, "games", [])) * Game.MAX_SCORE


def first_round_games(bracket: Any) -> list[Game]:
    games = list(bracket.games)
    first_round_name = games[0].round
    first_round: list[Game] = []
    for game in games:
        if game.round != first_round_name:
            break
        first_round.append(game)
    return first_round


def round_names_for(bracket: Any, first_round_name: str, rounds_per_conference: int) -> list[str]:
    loaded_rounds: list[str] = []
    for game in bracket.games:
        if game.round not in loaded_rounds:
            loaded_rounds.append(game.round)

    defaults = list(getattr(bracket, "conference_round_names", Bracket.conference_round_names))
    finals_name = getattr(bracket, "finals_round_name", Bracket.finals_round_name)

    names = list(loaded_rounds[: rounds_per_conference + 1])
    if not names:
        names.append(first_round_name)
    elif names[0] != first_round_name:
        names[0] = first_round_name

    fallback = [first_round_name]
    fallback.extend(defaults[1:rounds_per_conference])
    fallback.append(finals_name)

    while len(names) < rounds_per_conference + 1:
        candidate = fallback[len(names)]
        if candidate not in names:
            names.append(candidate)
        else:
            names.append(f"{candidate} {len(names) + 1}")

    return names[: rounds_per_conference + 1]


def build_plan(bracket: Any) -> BracketPlan:
    first_round = first_round_games(bracket)
    conference_order = unique_in_order([game.conference for game in first_round])
    if len(conference_order) != 2:
        raise ValueError("This GUI expects exactly two conferences.")

    conference_game_map: dict[str, list[Game]] = {
        conference: [game for game in first_round if game.conference == conference]
        for conference in conference_order
    }
    first_round_counts = {conference: len(items) for conference, items in conference_game_map.items()}
    if len(set(first_round_counts.values())) != 1:
        raise ValueError("The bracket must have the same number of first-round games per conference.")

    first_round_games_per_conference = next(iter(first_round_counts.values()))
    if first_round_games_per_conference < 2 or first_round_games_per_conference & (first_round_games_per_conference - 1):
        raise ValueError("First-round games per conference must be a power of two.")

    rounds_per_conference = int(math.log2(first_round_games_per_conference)) + 1
    round_names = round_names_for(bracket, first_round[0].round, rounds_per_conference)

    nodes_by_conf: dict[str, list[list[PlanNode]]] = {conf: [] for conf in conference_order}
    board_width = SIDE_MARGIN * 2 + CARD_W + ROUND_GAP * (rounds_per_conference * 2)

    # Build one tree per conference, then flatten in bracket order.
    for conf_index, conference in enumerate(conference_order):
        side = "west" if conf_index == 0 else "east"
        x_positions = [
            SIDE_MARGIN + ROUND_GAP * level if side == "west" else board_width - SIDE_MARGIN - CARD_W - ROUND_GAP * level
            for level in range(rounds_per_conference)
        ]

        levels: list[list[PlanNode]] = []
        base_y = TOP_MARGIN
        first_level: list[PlanNode] = []
        for game_index, _game in enumerate(conference_game_map[conference]):
            node = PlanNode(
                key=(conference, 0, game_index),
                round_index=0,
                round_name=round_names[0],
                conference=conference,
                side=side,
                x=x_positions[0],
                y=base_y + ROW_GAP * game_index,
            )
            first_level.append(node)
        levels.append(first_level)

        for level in range(1, rounds_per_conference):
            previous = levels[-1]
            current: list[PlanNode] = []
            for slot in range(0, len(previous), 2):
                left = previous[slot]
                right = previous[slot + 1]
                node = PlanNode(
                    key=(conference, level, slot // 2),
                    round_index=level,
                    round_name=round_names[level],
                    conference=conference,
                    side=side,
                    x=x_positions[level],
                    y=(left.y + right.y) / 2,
                    children_keys=(left.key, right.key),
                )
                left.parent_key = node.key
                right.parent_key = node.key
                current.append(node)
            levels.append(current)

        nodes_by_conf[conference] = levels

    nodes: list[PlanNode] = []
    round_ranges: list[tuple[int, int]] = []

    for level in range(rounds_per_conference):
        start = len(nodes)
        for conference in conference_order:
            for node in nodes_by_conf[conference][level]:
                nodes.append(node)
        round_ranges.append((start, len(nodes)))

    west_final = nodes_by_conf[conference_order[0]][-1][0]
    east_final = nodes_by_conf[conference_order[1]][-1][0]
    final_node = PlanNode(
        key=("Finals", rounds_per_conference, 0),
        round_index=rounds_per_conference,
        round_name=round_names[-1],
        conference=round_names[-1],
        side="center",
        x=board_width / 2 - CARD_W / 2,
        y=(west_final.y + east_final.y) / 2,
        children_keys=(west_final.key, east_final.key),
    )
    west_final.parent_key = final_node.key
    east_final.parent_key = final_node.key

    final_start = len(nodes)
    nodes.append(final_node)
    round_ranges.append((final_start, len(nodes)))

    index_by_key = {node.key: index for index, node in enumerate(nodes)}
    for node in nodes:
        node.index = index_by_key[node.key]

    for node in nodes:
        if node.children_keys:
            left_key, right_key = node.children_keys
            node.children_keys = (left_key, right_key)

    board_height = int(max(node.y for node in nodes) + CARD_H + BOARD_PADDING_BOTTOM)
    return BracketPlan(
        nodes=nodes,
        round_ranges=round_ranges,
        round_names=round_names,
        conference_order=conference_order,
        first_round_games_per_conference=first_round_games_per_conference,
        board_width=board_width,
        board_height=board_height,
    )


def round_is_complete(games: list[Game]) -> bool:
    return bool(games) and all(is_game_complete(game) for game in games)


def latest_materialized_round_index(bracket: Any, plan: BracketPlan) -> int | None:
    actual_count = len(bracket.games)
    for round_index, (start, end) in enumerate(plan.round_ranges):
        if actual_count < end:
            return round_index if actual_count > start else round_index - 1
    return len(plan.round_ranges) - 1


def append_next_round(bracket: Any, plan: BracketPlan, round_index: int) -> None:
    next_round_index = round_index + 1
    if next_round_index >= len(plan.round_ranges):
        return

    start, end = plan.round_ranges[round_index]
    current_games = bracket.games[start:end]
    if not round_is_complete(current_games):
        raise ValueError("The current round must be fully completed before the next round is created.")

    if hasattr(bracket, "create_next_round"):
        next_round_games = bracket.create_next_round(current_games)
        bracket.games.extend(next_round_games)
        return

    # Fallback for older bracket objects that do not yet expose the helper.
    if next_round_index == len(plan.round_ranges) - 1:
        if len(current_games) != 2:
            raise ValueError("Finals require exactly two conference champions.")
        bracket.games.append(Game("Finals", plan.round_names[-1], current_games[0].winner, current_games[1].winner))
        return

    next_round_name = plan.round_names[next_round_index]
    for conference in plan.conference_order:
        conference_games = [game for game in current_games if game.conference == conference]
        if len(conference_games) % 2 != 0:
            raise ValueError(f"Conference round {next_round_name} is malformed for {conference}.")
        for slot in range(0, len(conference_games), 2):
            bracket.games.append(
                Game(conference, next_round_name, conference_games[slot].winner, conference_games[slot + 1].winner)
            )


def materialize_progression(bracket: Any, plan: BracketPlan) -> bool:
    changed = False
    while True:
        materialized_round = latest_materialized_round_index(bracket, plan)
        if materialized_round is None or materialized_round < 0:
            break
        if materialized_round >= len(plan.round_ranges) - 1:
            break
        start, end = plan.round_ranges[materialized_round]
        if len(bracket.games) < end:
            break
        if not round_is_complete(bracket.games[start:end]):
            break
        if len(bracket.games) < plan.round_ranges[materialized_round + 1][1]:
            append_next_round(bracket, plan, materialized_round)
            changed = True
            continue
        break
    return changed


def next_active_round(bracket: Any, plan: BracketPlan) -> int | None:
    actual_count = len(bracket.games)
    for round_index, (start, end) in enumerate(plan.round_ranges):
        if actual_count <= start:
            return None
        round_games = bracket.games[start : min(end, actual_count)]
        if not round_is_complete(round_games):
            return round_index
    return None


def active_games_for_round(bracket: Any, plan: BracketPlan, round_index: int) -> list[Game]:
    start, end = plan.round_ranges[round_index]
    return bracket.games[start : min(end, len(bracket.games))]


def serialize_state(message: str = "") -> dict[str, Any]:
    bracket = STATE["bracket"]
    plan: BracketPlan | None = STATE["plan"]
    if bracket is None or plan is None:
        return {
            "loaded": False,
            "message": message or STATE["message"],
            "error": STATE["error"],
            "complete": False,
            "available_years": available_bracket_years(),
        }

    actual_count = len(bracket.games)
    active_round = STATE["active_round_index"]
    node_index_by_key = {node.key: node.index for node in plan.nodes}

    games_payload: list[dict[str, Any]] = []
    for node in plan.nodes:
        actual = node.index < actual_count
        game = bracket.games[node.index] if actual else Game(node.conference, node.round_name, "", "")
        editable = actual and active_round is not None and node.round_index == active_round and not STATE["complete"]
        games_payload.append(game_to_payload(game, node, actual, editable))

    connections: list[dict[str, Any]] = []
    for node in plan.nodes:
        if not node.children_keys:
            continue
        left_index = node_index_by_key.get(node.children_keys[0])
        right_index = node_index_by_key.get(node.children_keys[1])
        if left_index is None or right_index is None:
            continue
        left = plan.nodes[left_index]
        right = plan.nodes[right_index]
        parent_center_x = node.x + CARD_W / 2 if node.side == "center" else node.x
        parent_center_y = node.y + CARD_H / 2
        child_left_x = left.x + CARD_W if left.side != "east" else left.x
        child_right_x = right.x + CARD_W if right.side != "east" else right.x
        stem_x = node.x - 30
        connections.extend(
            [
                {
                    "x1": child_left_x,
                    "y1": left.y + CARD_H / 2,
                    "x2": stem_x,
                    "y2": left.y + CARD_H / 2,
                },
                {
                    "x1": child_right_x,
                    "y1": right.y + CARD_H / 2,
                    "x2": stem_x,
                    "y2": right.y + CARD_H / 2,
                },
                {
                    "x1": stem_x,
                    "y1": left.y + CARD_H / 2,
                    "x2": stem_x,
                    "y2": right.y + CARD_H / 2,
                },
                {
                    "x1": stem_x,
                    "y1": parent_center_y,
                    "x2": parent_center_x,
                    "y2": parent_center_y,
                },
            ]
        )

    return {
        "loaded": True,
        "message": message or STATE["message"],
        "error": STATE["error"],
        "filename": STATE["filename"],
        "bracket_name": getattr(bracket, "name", ""),
        "bracket_class": bracket.__class__.__name__,
        "bracket_year": bracket_year_for(bracket),
        "complete": STATE["complete"],
        "active_round_index": active_round,
        "active_round_name": plan.round_names[active_round] if active_round is not None and active_round < len(plan.round_names) else "",
        "available_years": available_bracket_years(),
        "board_width": plan.board_width,
        "board_height": plan.board_height,
        "rounds": [
            {
                "round_index": round_index,
                "round_name": plan.round_names[round_index],
                "start": start,
                "end": end,
            }
            for round_index, (start, end) in enumerate(plan.round_ranges)
        ],
        "games": games_payload,
        "connections": connections,
    }


def load_session(bracket: Bracket, message: str, filename: str = "") -> None:
    plan = build_plan(bracket)
    materialize_progression(bracket, plan)
    active_round = next_active_round(bracket, plan)
    complete = len(bracket.games) >= plan.round_ranges[-1][1] and active_round is None

    with STATE_LOCK:
        STATE.update(
            {
                "loaded": True,
                "message": message,
                "error": "",
                "filename": filename,
                "bracket": bracket,
                "plan": plan,
                "active_round_index": active_round,
                "complete": complete,
                "bracket_class": bracket.__class__.__name__,
                "bracket_name": getattr(bracket, "name", ""),
            }
        )


def create_new_bracket_session(year: int) -> None:
    bracket = create_bracket_for_year(year)
    load_session(bracket, message=f"Started an empty {year} bracket. Fill the first round.")


def reset_current_bracket_session() -> None:
    with STATE_LOCK:
        bracket = STATE["bracket"]
    if bracket is None:
        raise ValueError("No bracket is loaded.")

    year = bracket_year_for(bracket)
    if year is None:
        raise ValueError("Could not determine the current bracket year.")

    create_new_bracket_session(year)


def validate_and_apply_round(entries: list[dict[str, Any]]) -> None:
    bracket = STATE["bracket"]
    plan: BracketPlan = STATE["plan"]
    if bracket is None or plan is None:
        raise ValueError("No bracket is loaded.")

    active_round = STATE["active_round_index"]
    if active_round is None:
        raise ValueError("The bracket is already complete.")

    active_games = active_games_for_round(bracket, plan, active_round)
    if len(entries) != len(active_games):
        raise ValueError("The submitted round does not match the current active round.")

    for game, entry in zip(active_games, entries):
        team1_score = int(entry["team1_score"])
        team2_score = int(entry["team2_score"])
        if {team1_score, team2_score} != {4, 0} and 4 not in {team1_score, team2_score}:
            raise ValueError("Every series must have exactly one side at 4 and the other between 0 and 3.")
        if team1_score == 4 and not (0 <= team2_score <= 3):
            raise ValueError("The losing score must be between 0 and 3.")
        if team2_score == 4 and not (0 <= team1_score <= 3):
            raise ValueError("The losing score must be between 0 and 3.")
        if team1_score == 4:
            game.winner = game.team1
            game.num_games = 4 + team2_score
        elif team2_score == 4:
            game.winner = game.team2
            game.num_games = 4 + team1_score
        else:
            raise ValueError("Exactly one side must be 4.")

    materialize_progression(bracket, plan)

    active_round_after = next_active_round(bracket, plan)
    complete = len(bracket.games) >= plan.round_ranges[-1][1] and active_round_after is None

    with STATE_LOCK:
        STATE["active_round_index"] = active_round_after
        STATE["complete"] = complete
        STATE["message"] = "Round accepted. Fill the next round." if not complete else "Bracket completed. Enter a name and save it."
        STATE["error"] = ""


def save_bracket(name: str) -> str:
    bracket = STATE["bracket"]
    if bracket is None:
        raise ValueError("No bracket is loaded.")
    if not STATE["complete"]:
        raise ValueError("You can save only after the entire bracket is completed.")

    cleaned = name.strip()
    if not cleaned:
        raise ValueError("Please enter a bracket name.")
    if any(sep in cleaned for sep in ("/", "\\", "\0")):
        raise ValueError("The bracket name cannot contain path separators.")

    bracket.name = cleaned
    SAVED_BRACKETS_DIR.mkdir(parents=True, exist_ok=True)
    save_path = SAVED_BRACKETS_DIR / cleaned
    with open(save_path, "wb") as f:
        pickle.dump(bracket, f)
    return str(save_path)


def read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length) if length else b"{}"
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def write_json(handler: BaseHTTPRequestHandler, payload: dict[str, Any], status: int = 200) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


HTML_PAGE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Bracket GUI</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0b0d12;
      --panel: rgba(18, 20, 29, 0.88);
      --panel-2: rgba(255, 255, 255, 0.04);
      --line: rgba(255, 255, 255, 0.14);
      --text: #f4f7fb;
      --muted: #97a2b8;
      --accent: #c9ff2f;
      --accent-2: #68d6ff;
      --shadow: 0 18px 44px rgba(0, 0, 0, 0.4);
      --card: #111621;
      --card-locked: #0f141d;
      --danger: #ff7188;
      --good: #8bff9a;
      --input: #0a0f18;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
      background:
        radial-gradient(circle at top left, rgba(201,255,47,0.10), transparent 34%),
        radial-gradient(circle at top right, rgba(104,214,255,0.10), transparent 34%),
        linear-gradient(180deg, #0b0d12 0%, #0f1118 100%);
      color: var(--text);
    }
    header {
      position: sticky;
      top: 0;
      z-index: 20;
      backdrop-filter: blur(10px);
      background: rgba(9, 12, 17, 0.72);
      border-bottom: 1px solid var(--line);
      padding: 18px 24px 14px;
      box-shadow: var(--shadow);
    }
    .title-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      flex-wrap: wrap;
    }
    h1 {
      margin: 0;
      font-size: clamp(24px, 3vw, 34px);
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }
    .subtitle {
      color: var(--muted);
      margin-top: 6px;
      font-size: 14px;
    }
    .chip-row {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }
    .chip {
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.04);
      border-radius: 999px;
      padding: 8px 12px;
      font-size: 13px;
      color: var(--muted);
    }
    .shell {
      padding: 18px 18px 28px;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }
    .tab-bar {
      display: flex;
      gap: 10px;
      padding: 16px 18px 0;
      flex-wrap: wrap;
      background: rgba(255,255,255,0.02);
      border-bottom: 1px solid var(--line);
    }
    .tab-button {
      appearance: none;
      border: 1px solid var(--line);
      border-bottom: 0;
      border-radius: 14px 14px 0 0;
      padding: 12px 16px;
      cursor: pointer;
      background: rgba(255,255,255,0.04);
      color: var(--muted);
      font-weight: 700;
      letter-spacing: 0.03em;
    }
    .tab-button.active {
      color: var(--text);
      background: rgba(255,255,255,0.08);
    }
    .tab-panel {
      display: none;
    }
    .tab-panel.active {
      display: block;
    }
    .guide {
      padding: 18px 20px 16px;
      border-bottom: 1px solid var(--line);
      background: linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.02));
    }
    .guide h2 {
      margin: 0 0 8px;
      font-size: 16px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }
    .guide ol {
      margin: 0;
      padding-left: 18px;
      color: var(--muted);
      line-height: 1.55;
      font-size: 14px;
    }
    .tool-shell {
      padding: 24px 20px 28px;
      display: grid;
      gap: 18px;
    }
    .tool-card {
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 20px;
      background: linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.02));
      box-shadow: var(--shadow);
    }
    .tool-card h2 {
      margin: 0 0 10px;
      font-size: 22px;
      letter-spacing: 0.03em;
      text-transform: uppercase;
    }
    .tool-card p {
      margin: 0;
      color: var(--muted);
      line-height: 1.55;
    }
    .tool-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 14px;
    }
    .field-block {
      display: grid;
      gap: 8px;
      padding: 16px;
      border-radius: 14px;
      border: 1px solid rgba(255,255,255,0.10);
      background: rgba(255,255,255,0.03);
    }
    .field-block strong {
      font-size: 14px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }
    .file-input {
      width: 100%;
      border: 1px solid rgba(255,255,255,0.14);
      border-radius: 10px;
      background: rgba(6,9,14,0.88);
      color: var(--muted);
      padding: 10px 12px;
      font-size: 14px;
    }
    .upload-list {
      display: grid;
      gap: 4px;
      min-height: 20px;
      color: var(--muted);
      font-size: 13px;
    }
    .result-panel {
      min-height: 24px;
      color: var(--accent);
      font-weight: 600;
    }
    .result-panel.error {
      color: var(--danger);
    }
    .graph-preview {
      width: 100%;
      border-radius: 16px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.03);
      padding: 8px;
    }
    .selector-area {
      padding: 34px;
      text-align: center;
      display: grid;
      gap: 18px;
      place-items: center;
      min-height: 260px;
    }
    .selector-box {
      width: min(680px, 100%);
      border: 1px dashed rgba(201,255,47,0.5);
      border-radius: 18px;
      padding: 28px;
      background: linear-gradient(180deg, rgba(201,255,47,0.05), rgba(255,255,255,0.02));
    }
    .selector-box p {
      margin: 0 0 16px;
      color: var(--muted);
      line-height: 1.45;
    }
    .button, .file-label {
      appearance: none;
      border: 0;
      border-radius: 12px;
      padding: 12px 16px;
      cursor: pointer;
      font-weight: 700;
      letter-spacing: 0.02em;
      color: #08110a;
      background: linear-gradient(180deg, #d7ff4b, #a8d81d);
      box-shadow: 0 10px 24px rgba(201,255,47,0.18);
    }
    .button.secondary {
      color: var(--text);
      background: linear-gradient(180deg, rgba(255,255,255,0.09), rgba(255,255,255,0.04));
      border: 1px solid var(--line);
      box-shadow: none;
    }
    .button:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
    .year-picker {
      width: min(360px, 80vw);
      accent-color: var(--accent);
    }
    .year-value {
      font-size: 36px;
      font-weight: 800;
      letter-spacing: 0.08em;
      margin: 8px 0 14px;
    }
    .year-ticks {
      display: flex;
      justify-content: center;
      gap: 12px;
      flex-wrap: wrap;
      color: var(--muted);
      font-size: 13px;
    }
    .status {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      align-items: center;
      padding: 18px 20px;
      border-bottom: 1px solid var(--line);
      background: rgba(255,255,255,0.03);
    }
    .status strong {
      display: block;
      font-size: 16px;
      margin-bottom: 4px;
    }
    .status small {
      color: var(--muted);
    }
    .status-msg {
      color: var(--accent);
      font-weight: 600;
    }
    .status-msg.error {
      color: var(--danger);
    }
    .board-wrap {
      position: relative;
      overflow: auto;
      max-width: 100%;
      background:
        linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.00)),
        radial-gradient(circle at center, rgba(201,255,47,0.06), transparent 56%);
    }
    .board {
      position: relative;
      min-width: 100%;
      width: max-content;
      margin: 0 auto;
      background:
        radial-gradient(circle at center, rgba(255,255,255,0.02), transparent 50%),
        repeating-linear-gradient(90deg, rgba(255,255,255,0.018) 0, rgba(255,255,255,0.018) 1px, transparent 1px, transparent 58px);
    }
    .connector-layer {
      position: absolute;
      inset: 0;
      pointer-events: none;
      overflow: visible;
    }
    .connector-layer line {
      stroke: rgba(201,255,47,0.45);
      stroke-width: 3;
      stroke-linecap: round;
    }
    .game-card {
      position: absolute;
      width: 248px;
      min-height: 118px;
      border-radius: 16px;
      border: 1px solid rgba(255,255,255,0.16);
      background: linear-gradient(180deg, rgba(24, 30, 42, 0.98), rgba(14, 18, 28, 0.98));
      box-shadow: 0 10px 22px rgba(0, 0, 0, 0.32);
      overflow: hidden;
    }
    .game-card.current {
      border-color: rgba(201,255,47,0.55);
      box-shadow: 0 0 0 1px rgba(201,255,47,0.12), 0 14px 28px rgba(0,0,0,0.35);
    }
    .game-card.complete {
      border-color: rgba(104,214,255,0.38);
    }
    .game-card.placeholder {
      background: linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.02));
      border-style: dashed;
      color: rgba(255,255,255,0.48);
    }
    .card-head {
      padding: 10px 12px 8px;
      display: flex;
      justify-content: space-between;
      gap: 8px;
      align-items: center;
      border-bottom: 1px solid rgba(255,255,255,0.08);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: var(--muted);
    }
    .card-head .round-pill {
      border-radius: 999px;
      padding: 4px 8px;
      background: rgba(201,255,47,0.12);
      color: var(--accent);
    }
    .card-body {
      padding: 10px 10px 12px;
      display: grid;
      gap: 8px;
    }
    .team-row {
      display: grid;
      grid-template-columns: 28px 1fr 36px;
      align-items: center;
      gap: 8px;
      min-height: 38px;
      padding: 5px 6px;
      border-radius: 10px;
      background: rgba(255,255,255,0.03);
    }
    .team-row.winner {
      background: rgba(201,255,47,0.12);
      color: #f5ffd3;
    }
    .team-logo {
      width: 28px;
      height: 28px;
      object-fit: contain;
      filter: drop-shadow(0 0 6px rgba(0,0,0,0.2));
    }
    .team-name {
      font-size: 15px;
      font-weight: 700;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .score {
      width: 34px;
      height: 28px;
      border-radius: 8px;
      border: 1px solid rgba(255,255,255,0.18);
      background: var(--input);
      color: var(--text);
      text-align: center;
      font-size: 14px;
      font-weight: 700;
    }
    .score:disabled {
      opacity: 0.8;
      background: rgba(255,255,255,0.04);
      color: rgba(255,255,255,0.85);
    }
    .score.invalid {
      border-color: var(--danger);
      box-shadow: 0 0 0 1px rgba(255,113,136,0.15);
    }
    .series-note {
      margin-top: 4px;
      font-size: 12px;
      color: var(--muted);
      padding: 0 6px;
      min-height: 16px;
    }
    .game-card.placeholder .card-body {
      opacity: 0.55;
    }
    .board-footer {
      display: flex;
      gap: 12px;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      padding: 14px 18px;
      border-top: 1px solid var(--line);
      background: rgba(255,255,255,0.03);
    }
    .form-row {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
    }
    .save-name {
      width: min(320px, 70vw);
      border-radius: 12px;
      border: 1px solid rgba(255,255,255,0.14);
      background: rgba(6,9,14,0.88);
      color: var(--text);
      padding: 12px 14px;
      font-size: 14px;
    }
    .hidden { display: none !important; }
    .hint {
      color: var(--muted);
      font-size: 13px;
    }
    .error-box {
      color: var(--danger);
      font-size: 14px;
      margin-top: 10px;
      min-height: 20px;
    }
    @media (max-width: 920px) {
      .shell { padding: 12px; }
      .board-wrap { overflow-x: auto; }
    }
  </style>
</head>
<body>
  <header>
    <div class="title-row">
      <div>
        <h1>Bracket GUI</h1>
        <div class="subtitle">Fill a fresh bracket, compare saved pickles, or render a score graph from uploaded brackets.</div>
      </div>
      <div class="chip-row">
        <div class="chip">Single-file stdlib backend</div>
        <div class="chip">Fill, compare, and graph tabs</div>
        <div class="chip">Terminal quit support</div>
      </div>
    </div>
  </header>
  <div class="shell">
    <div class="panel" id="app">
      <div class="tab-bar">
        <button class="tab-button active" data-tab="fill">Fill</button>
        <button class="tab-button" data-tab="compare">Compare</button>
        <button class="tab-button" data-tab="graph">Graph</button>
      </div>

      <section class="tab-panel active" id="fillTab">
        <section class="guide">
          <h2>How It Works</h2>
          <ol>
            <li>Choose the bracket year and start a fresh bracket.</li>
            <li>In the active round, enter one winner at <strong>4</strong> and the loser between <strong>0</strong> and <strong>3</strong>.</li>
            <li>Click <strong>Next Round</strong> only after every series in the active round is filled.</li>
            <li>Use <strong>Reset Bracket</strong> to erase the current bracket and restart the same year.</li>
            <li>Ranking is based on the saved bracket compared with the ground truth, series by series: correct winner side (<strong>team 1</strong> vs <strong>team 2</strong>) = <strong>1</strong> point, correct winner identity = <strong>1</strong> point, and exact number of games = <strong>1</strong> point.</li>
            <li>If you get all three for a series, that series is worth <strong>4</strong> points total.</li>
            <li>There are 15 series in total, so the highest possible score is <strong>60</strong>. Higher total score ranks higher.</li>
          </ol>
        </section>
        <div class="selector-area" id="selectorArea">
          <div class="selector-box">
            <p><strong>Choose a bracket year to begin.</strong><br />The app will create a fresh bracket object on the backend, then unlock the first round for score entry.</p>
            <input class="year-picker" id="yearInput" type="range" min="0" max="0" step="1" value="0" />
            <div class="year-value" id="yearValue">2025</div>
            <div class="year-ticks" id="yearTicks"></div>
            <button class="button" id="startBracketBtn">Start New Bracket</button>
            <div class="error-box" id="selectorError"></div>
          </div>
        </div>

        <div class="hidden" id="workspace">
          <div class="status">
            <div>
              <strong id="statusTitle">Bracket not loaded</strong>
              <small id="statusDetails">Choose a bracket year.</small>
            </div>
            <div class="status-msg" id="statusMsg"></div>
          </div>
          <div class="board-wrap">
            <div class="board" id="board">
              <svg class="connector-layer" id="connectorLayer"></svg>
              <div id="cardsLayer"></div>
            </div>
          </div>
          <div class="board-footer">
            <div class="form-row">
              <button class="button" id="nextRoundBtn" disabled>Next Round</button>
              <button class="button secondary" id="resetBtn">Reset Bracket</button>
              <span class="hint" id="roundHint">Fill the active round, then advance.</span>
            </div>
            <div class="form-row hidden" id="saveRow">
              <input class="save-name" id="saveName" placeholder="Enter bracket filename" />
              <button class="button secondary" id="saveBtn">Save Pickle</button>
            </div>
          </div>
        </div>
      </section>

      <section class="tab-panel" id="compareTab">
        <div class="tool-shell">
          <div class="tool-card">
            <h2>Compare Brackets</h2>
            <p>Upload two saved bracket pickle files, then compare them series by series. The score uses the same 60-point system as the ground-truth ranking.</p>
          </div>
          <div class="tool-grid">
            <div class="field-block">
              <strong>Bracket A</strong>
              <input class="file-input" id="compareFileA" type="file" accept=".pkl,.pickle" />
              <div class="upload-list" id="compareFileAName"></div>
            </div>
            <div class="field-block">
              <strong>Bracket B</strong>
              <input class="file-input" id="compareFileB" type="file" accept=".pkl,.pickle" />
              <div class="upload-list" id="compareFileBName"></div>
            </div>
          </div>
          <div class="form-row">
            <button class="button" id="compareBtn">Compare Brackets</button>
          </div>
          <div class="result-panel" id="compareResult"></div>
        </div>
      </section>

      <section class="tab-panel" id="graphTab">
        <div class="tool-shell">
          <div class="tool-card">
            <h2>Graph View</h2>
            <p>Upload at least three saved bracket pickle files, then render the pairwise score graph directly in the browser.</p>
          </div>
          <div class="field-block">
            <strong>Bracket Files</strong>
            <input class="file-input" id="graphFiles" type="file" accept=".pkl,.pickle" multiple />
            <div class="upload-list" id="graphFileNames"></div>
          </div>
          <div class="form-row">
            <button class="button" id="graphBtn">Render Graph</button>
          </div>
          <div class="result-panel" id="graphResult"></div>
          <img class="graph-preview hidden" id="graphImage" alt="Bracket comparison graph" />
        </div>
      </section>
    </div>
  </div>

  <template id="cardTemplate">
    <div class="game-card">
      <div class="card-head">
        <span class="round-pill"></span>
        <span class="series-pill"></span>
      </div>
      <div class="card-body"></div>
      <div class="series-note"></div>
    </div>
  </template>

  <script>
    const state = {
      data: null,
      availableYears: [],
    };

    const tabButtons = Array.from(document.querySelectorAll(".tab-button"));
    const tabPanels = {
      fill: document.getElementById("fillTab"),
      compare: document.getElementById("compareTab"),
      graph: document.getElementById("graphTab"),
    };
    const selectorArea = document.getElementById("selectorArea");
    const yearInput = document.getElementById("yearInput");
    const yearValue = document.getElementById("yearValue");
    const yearTicks = document.getElementById("yearTicks");
    const startBracketBtn = document.getElementById("startBracketBtn");
    const selectorError = document.getElementById("selectorError");
    const workspace = document.getElementById("workspace");
    const statusTitle = document.getElementById("statusTitle");
    const statusDetails = document.getElementById("statusDetails");
    const statusMsg = document.getElementById("statusMsg");
    const board = document.getElementById("board");
    const cardsLayer = document.getElementById("cardsLayer");
    const connectorLayer = document.getElementById("connectorLayer");
    const nextRoundBtn = document.getElementById("nextRoundBtn");
    const resetBtn = document.getElementById("resetBtn");
    const roundHint = document.getElementById("roundHint");
    const saveRow = document.getElementById("saveRow");
    const saveName = document.getElementById("saveName");
    const saveBtn = document.getElementById("saveBtn");
    const compareFileA = document.getElementById("compareFileA");
    const compareFileB = document.getElementById("compareFileB");
    const compareFileAName = document.getElementById("compareFileAName");
    const compareFileBName = document.getElementById("compareFileBName");
    const compareBtn = document.getElementById("compareBtn");
    const compareResult = document.getElementById("compareResult");
    const graphFiles = document.getElementById("graphFiles");
    const graphFileNames = document.getElementById("graphFileNames");
    const graphBtn = document.getElementById("graphBtn");
    const graphResult = document.getElementById("graphResult");
    const graphImage = document.getElementById("graphImage");

    tabButtons.forEach(button => {
      button.addEventListener("click", () => switchTab(button.dataset.tab));
    });
    yearInput.addEventListener("input", renderSelectedYear);
    compareFileA.addEventListener("change", () => renderSelectedFiles(compareFileA.files, compareFileAName, false));
    compareFileB.addEventListener("change", () => renderSelectedFiles(compareFileB.files, compareFileBName, false));
    graphFiles.addEventListener("change", () => renderSelectedFiles(graphFiles.files, graphFileNames, true));

    startBracketBtn.addEventListener("click", async () => {
      selectorError.textContent = "";
      const year = getSelectedYear();
      if (year === null) {
        selectorError.textContent = "No bracket year is available.";
        return;
      }
      try {
        const response = await fetch("/create-bracket", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({year}),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || data.message || "Bracket creation failed.");
        renderState(data);
      } catch (err) {
        selectorError.textContent = err.message;
      }
    });

    nextRoundBtn.addEventListener("click", async () => {
      const payload = gatherActiveRound();
      if (!payload.ok) {
        statusMsg.textContent = payload.error;
        statusMsg.classList.add("error");
        return;
      }
      try {
        const response = await fetch("/submit-round", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({series: payload.series}),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Round submission failed.");
        renderState(data);
      } catch (err) {
        statusMsg.textContent = err.message;
        statusMsg.classList.add("error");
      }
    });

    resetBtn.addEventListener("click", async () => {
      if (!state.data || !state.data.loaded) return;
      const bracketYear = state.data.bracket_year;
      const confirmed = window.confirm(`Reset the current ${bracketYear || ""} bracket and start over?`);
      if (!confirmed) return;
      try {
        const response = await fetch("/reset-bracket", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Reset failed.");
        saveName.value = "";
        renderState(data);
      } catch (err) {
        statusMsg.textContent = err.message;
        statusMsg.classList.add("error");
      }
    });

    saveBtn.addEventListener("click", async () => {
      try {
        const response = await fetch("/save", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({name: saveName.value}),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Save failed.");
        statusMsg.textContent = data.message;
        statusMsg.classList.remove("error");
      } catch (err) {
        statusMsg.textContent = err.message;
        statusMsg.classList.add("error");
      }
    });

    compareBtn.addEventListener("click", async () => {
      setResult(compareResult, "");
      try {
        const files = [compareFileA.files[0], compareFileB.files[0]].filter(Boolean);
        if (files.length !== 2) {
          throw new Error("Choose exactly two bracket pickle files.");
        }
        const response = await fetch("/compare-brackets", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({files: await collectUploadEntries(files)}),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Compare failed.");
        setResult(compareResult, data.message || "Comparison complete.");
      } catch (err) {
        setResult(compareResult, err.message, true);
      }
    });

    graphBtn.addEventListener("click", async () => {
      setResult(graphResult, "");
      graphImage.classList.add("hidden");
      graphImage.removeAttribute("src");
      try {
        const files = Array.from(graphFiles.files || []);
        if (files.length < 3) {
          throw new Error("Choose at least three bracket pickle files.");
        }
        const response = await fetch("/graph-brackets", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({files: await collectUploadEntries(files)}),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Graph render failed.");
        graphImage.src = `data:image/png;base64,${data.image_base64}`;
        graphImage.classList.remove("hidden");
        setResult(graphResult, data.message || "Graph ready.");
      } catch (err) {
        setResult(graphResult, err.message, true);
      }
    });

    async function boot() {
      switchTab("fill");
      renderSelectedFiles([], compareFileAName, false);
      renderSelectedFiles([], compareFileBName, false);
      renderSelectedFiles([], graphFileNames, true);
      try {
        const response = await fetch("/state");
        const data = await response.json();
        renderState(data);
      } catch (err) {
        // Fresh start is fine.
      }
    }

    function switchTab(tabName) {
      for (const button of tabButtons) {
        button.classList.toggle("active", button.dataset.tab === tabName);
      }
      for (const [name, panel] of Object.entries(tabPanels)) {
        panel.classList.toggle("active", name === tabName);
      }
    }

    function setResult(element, message, isError = false) {
      element.textContent = message;
      element.classList.toggle("error", Boolean(isError));
    }

    function renderSelectedFiles(fileList, container, multiple) {
      const files = Array.from(fileList || []);
      if (!files.length) {
        container.innerHTML = `<span>${multiple ? "No files selected yet." : "No file selected yet."}</span>`;
        return;
      }
      container.innerHTML = files.map(file => `<span>${file.name}</span>`).join("");
    }

    async function collectUploadEntries(files) {
      return Promise.all(files.map(async file => ({
        name: file.name,
        data: arrayBufferToBase64(await file.arrayBuffer()),
      })));
    }

    function arrayBufferToBase64(buffer) {
      const bytes = new Uint8Array(buffer);
      const chunkSize = 0x8000;
      let binary = "";
      for (let index = 0; index < bytes.length; index += chunkSize) {
        const chunk = bytes.subarray(index, index + chunkSize);
        binary += String.fromCharCode(...chunk);
      }
      return btoa(binary);
    }

    function renderState(data) {
      state.data = data;
      state.availableYears = Array.isArray(data.available_years) ? data.available_years : [];
      selectorError.textContent = "";
      renderYearPicker();

      if (!data.loaded) {
        selectorArea.classList.remove("hidden");
        workspace.classList.add("hidden");
        return;
      }

      selectorArea.classList.add("hidden");
      workspace.classList.remove("hidden");

      statusTitle.textContent = `${data.bracket_class || "Bracket"}${data.bracket_name ? ` • ${data.bracket_name}` : ""}`;
      statusDetails.textContent = data.complete
        ? "Bracket complete. Enter a save name below and export the pickle."
        : `Year ${data.bracket_year || "?"} • Active round: ${data.active_round_name || "n/a"}`;
      statusMsg.textContent = data.message || "";
      statusMsg.classList.toggle("error", Boolean(data.error));
      if (data.error) {
        statusMsg.textContent = data.error;
      }

      nextRoundBtn.disabled = Boolean(data.complete);
      resetBtn.disabled = false;
      roundHint.textContent = data.complete ? "All rounds are complete." : "Fill every series in the active round before advancing.";
      saveRow.classList.toggle("hidden", !data.complete);

      board.style.width = `${data.board_width}px`;
      board.style.height = `${data.board_height}px`;
      connectorLayer.setAttribute("viewBox", `0 0 ${data.board_width} ${data.board_height}`);
      connectorLayer.setAttribute("width", data.board_width);
      connectorLayer.setAttribute("height", data.board_height);

      drawConnections(data.connections || []);
      drawCards(data.games || []);
    }

    function drawConnections(connections) {
      connectorLayer.innerHTML = "";
      for (const segment of connections) {
        const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
        line.setAttribute("x1", segment.x1);
        line.setAttribute("y1", segment.y1);
        line.setAttribute("x2", segment.x2);
        line.setAttribute("y2", segment.y2);
        connectorLayer.appendChild(line);
      }
    }

    function renderYearPicker() {
      const count = state.availableYears.length;
      const disabled = count === 0;
      yearInput.disabled = disabled;
      startBracketBtn.disabled = disabled;

      if (disabled) {
        yearInput.min = "0";
        yearInput.max = "0";
        yearInput.value = "0";
        yearValue.textContent = "N/A";
        yearTicks.innerHTML = "<span>No bracket years are configured yet.</span>";
        return;
      }

      yearInput.min = "0";
      yearInput.max = String(count - 1);
      yearInput.value = clampYearIndex(yearInput.value);
      yearValue.textContent = String(getSelectedYear());
      yearTicks.innerHTML = state.availableYears.map(year => `<span>${year}</span>`).join("");
    }

    function clampYearIndex(rawValue) {
      const max = Math.max(0, state.availableYears.length - 1);
      const parsed = Number.parseInt(rawValue, 10);
      if (Number.isNaN(parsed)) return "0";
      return String(Math.max(0, Math.min(parsed, max)));
    }

    function getSelectedYear() {
      const index = Number.parseInt(clampYearIndex(yearInput.value), 10);
      return state.availableYears[index] ?? null;
    }

    function renderSelectedYear() {
      const year = getSelectedYear();
      yearValue.textContent = year === null ? "N/A" : String(year);
    }

    function drawCards(games) {
      cardsLayer.innerHTML = "";
      for (const game of games) {
        const card = document.getElementById("cardTemplate").content.firstElementChild.cloneNode(true);
        card.style.left = `${game.x}px`;
        card.style.top = `${game.y}px`;
        if (game.placeholder) card.classList.add("placeholder");
        if (game.complete) card.classList.add("complete");
        if (game.editable) card.classList.add("current");

        const roundLabel = card.querySelector(".round-pill");
        const seriesLabel = card.querySelector(".series-pill");
        const body = card.querySelector(".card-body");
        const note = card.querySelector(".series-note");

        roundLabel.textContent = game.round_name;
        seriesLabel.textContent = game.conference;

        if (game.placeholder) {
          body.innerHTML = `
            <div class="team-row"><div></div><div class="team-name">Pending</div><div></div></div>
            <div class="team-row"><div></div><div class="team-name">Waiting for winners</div><div></div></div>
          `;
          note.textContent = "This round will unlock after the previous round is submitted.";
        } else {
          body.innerHTML = `
            ${renderTeamRow(game, 1)}
            ${renderTeamRow(game, 2)}
          `;
          note.textContent = game.series_label || (game.complete ? `${game.winner} in ${game.num_games}` : "Enter 4 and 0-3 to resolve the series.");
          if (game.complete && game.winner) {
            card.querySelectorAll(".team-row").forEach(row => {
              const name = row.querySelector(".team-name")?.textContent;
              if (name && name === game.winner) row.classList.add("winner");
            });
          }
        }

        cardsLayer.appendChild(card);
      }

      for (const card of cardsLayer.querySelectorAll(".game-card.current")) {
        const inputs = card.querySelectorAll(".score");
        inputs.forEach(input => input.addEventListener("input", () => input.classList.remove("invalid")));
      }
    }

    function renderTeamRow(game, side) {
      const team = side === 1 ? game.team1 : game.team2;
      const logo = side === 1 ? game.team1_logo : game.team2_logo;
      const value = game.complete ? (game.winner === team ? 4 : Math.max(0, (game.num_games || 4) - 4)) : "";
      const disabled = game.editable ? "" : "disabled";
      const placeholder = game.editable ? "0-4" : "";
      const id = `g${game.index}_s${side}`;
      return `
        <div class="team-row ${game.complete && game.winner === team ? "winner" : ""}">
          <img class="team-logo" src="/logos/${encodeURIComponent(logo)}" alt="${team || "team"} logo" />
          <div class="team-name">${team || "Pending"}</div>
          <input class="score" id="${id}" type="text" inputmode="numeric" maxlength="1" value="${value}" placeholder="${placeholder}" ${disabled} />
        </div>
      `;
    }

    function gatherActiveRound() {
      if (!state.data || !state.data.loaded) return {ok: false, error: "Create a bracket first."};
      const games = state.data.games.filter(g => g.editable);
      const series = [];
      for (const game of games) {
        const s1 = document.getElementById(`g${game.index}_s1`);
        const s2 = document.getElementById(`g${game.index}_s2`);
        if (!s1 || !s2) return {ok: false, error: "Missing score inputs."};
        const a = s1.value.trim();
        const b = s2.value.trim();
        if (!/^[0-4]$/.test(a) || !/^[0-4]$/.test(b)) {
          s1.classList.toggle("invalid", !/^[0-4]$/.test(a));
          s2.classList.toggle("invalid", !/^[0-4]$/.test(b));
          return {ok: false, error: "Use only integers 0-4 for each team."};
        }
        const team1 = parseInt(a, 10);
        const team2 = parseInt(b, 10);
        if ((team1 === 4) === (team2 === 4)) {
          s1.classList.add("invalid");
          s2.classList.add("invalid");
          return {ok: false, error: "Exactly one side must be 4 and the other must be 0-3."};
        }
        if (team1 !== 4 && team1 > 3) {
          s1.classList.add("invalid");
          return {ok: false, error: "The losing score must be between 0 and 3."};
        }
        if (team2 !== 4 && team2 > 3) {
          s2.classList.add("invalid");
          return {ok: false, error: "The losing score must be between 0 and 3."};
        }
        series.push({team1_score: team1, team2_score: team2});
      }
      return {ok: true, series};
    }

    boot();
  </script>
</body>
</html>
"""


class FillGUIHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/":
            body = HTML_PAGE.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/state":
            with STATE_LOCK:
                payload = serialize_state()
            write_json(self, payload)
            return

        if path.startswith("/logos/"):
            rel = path[len("/logos/") :]
            candidate = LOGO_DIR / rel
            if not candidate.exists() or not candidate.is_file():
                self.send_error(HTTPStatus.NOT_FOUND, "Logo not found")
                return
            content = candidate.read_bytes()
            content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/create-bracket":
            try:
                payload = read_json(self)
                year = int(payload.get("year"))
                create_new_bracket_session(year)
                with STATE_LOCK:
                    payload = serialize_state(message=STATE["message"])
                write_json(self, payload)
            except Exception as exc:  # noqa: BLE001
                with STATE_LOCK:
                    STATE["error"] = str(exc)
                    STATE["message"] = str(exc)
                write_json(self, {"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        if path == "/submit-round":
            try:
                payload = read_json(self)
                series = payload.get("series", [])
                if not isinstance(series, list) or not series:
                    raise ValueError("No series were submitted.")
                validate_and_apply_round(series)
                with STATE_LOCK:
                    response = serialize_state(message=STATE["message"])
                write_json(self, response)
            except Exception as exc:  # noqa: BLE001
                with STATE_LOCK:
                    STATE["error"] = str(exc)
                    STATE["message"] = str(exc)
                write_json(self, {"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        if path == "/reset-bracket":
            try:
                reset_current_bracket_session()
                with STATE_LOCK:
                    response = serialize_state(message=STATE["message"])
                write_json(self, response)
            except Exception as exc:  # noqa: BLE001
                with STATE_LOCK:
                    STATE["error"] = str(exc)
                    STATE["message"] = str(exc)
                write_json(self, {"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        if path == "/compare-brackets":
            try:
                payload = read_json(self)
                brackets = load_uploaded_brackets(payload.get("files", []), exact=2)
                score = brackets[0].calculate_score(brackets[1])
                max_score = min(max_bracket_score(brackets[0]), max_bracket_score(brackets[1]))
                message = f"{bracket_label(brackets[0], 'Bracket A')} vs {bracket_label(brackets[1], 'Bracket B')}: {score} / {max_score}"
                write_json(self, {"message": message, "score": score, "max_score": max_score})
            except Exception as exc:  # noqa: BLE001
                write_json(self, {"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        if path == "/graph-brackets":
            try:
                payload = read_json(self)
                brackets = load_uploaded_brackets(payload.get("files", []), minimum=3)
                try:
                    from graph import render_results_image
                except ModuleNotFoundError as exc:
                    raise ValueError(
                        f"Graph rendering requires {exc.name}. Install the packages from requirements.txt first."
                    ) from exc

                image_base64 = base64.b64encode(render_results_image(brackets)).decode("ascii")
                write_json(
                    self,
                    {
                        "message": f"Rendered score graph for {len(brackets)} brackets.",
                        "image_base64": image_base64,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                write_json(self, {"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        if path == "/save":
            try:
                payload = read_json(self)
                name = str(payload.get("name", ""))
                save_path = save_bracket(name)
                with STATE_LOCK:
                    STATE["message"] = f"Saved to {save_path}."
                    response = serialize_state(message=STATE["message"])
                    response["saved_to"] = save_path
                write_json(self, response)
            except Exception as exc:  # noqa: BLE001
                with STATE_LOCK:
                    STATE["error"] = str(exc)
                    STATE["message"] = str(exc)
                write_json(self, {"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")


def start_server(host: str, port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), FillGUIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def wait_for_shutdown_command() -> None:
    if not sys.stdin or not sys.stdin.isatty():
        threading.Event().wait()
        return

    print("Type 'q' or 'quit' and press Enter to stop the server.")
    while True:
        try:
            command = input().strip().lower()
        except EOFError:
            threading.Event().wait()
            return

        if command in {"q", "quit", "exit", "stop"}:
            return
        if command:
            print("Unknown command. Type 'q' or 'quit' to stop the server.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Local bracket fill GUI")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", default=DEFAULT_PORT, type=int)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    server = start_server(args.host, args.port)
    url = f"http://{args.host}:{args.port}/"
    print(f"Bracket fill GUI running at {url}")
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        wait_for_shutdown_command()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
