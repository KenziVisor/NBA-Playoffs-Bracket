import pickle
from abc import ABC, abstractmethod


class Game:
    MAX_SCORE = 4

    def __init__(self, conference: str = "", round: str = "",
                 team1: str = "", team2: str = "", winner: str = "", num_games: int = 0):
        self.conference = conference
        self.round = round
        self.team1 = team1
        self.team2 = team2
        self.winner = winner
        self.num_games = num_games

    def fill(self) -> None:
        print(f"{self.round}: {self.team1} vs {self.team2}!!!")
        choose = int(input(f"Who is your winner? for {self.team1} press 1. for {self.team2} press 2\n"))
        if choose == 1:
            self.winner = self.team1
        elif choose == 2:
            self.winner = self.team2
        num_games = int(input("How many games will be played? enter a number from 4 to 7\n"))
        self.num_games = num_games

    def calculate_score(self, gt: "Game") -> int:
        score = 0
        my_winner_slot = 1 if self.winner == self.team1 else 2 if self.winner == self.team2 else 0
        gt_winner_slot = 1 if gt.winner == gt.team1 else 2 if gt.winner == gt.team2 else 0
        if my_winner_slot and my_winner_slot == gt_winner_slot:
            score += 1
        if self.winner == gt.winner:
            score += 1
        if self.num_games == gt.num_games:
            score += 1
        if score == Game.MAX_SCORE - 1:
            score = Game.MAX_SCORE
        return score

    def save(self, filename: str) -> None:
        with open(filename, 'wb') as f:
            pickle.dump(self, f)

    #Getters
    def get_conference(self) -> str:
        return self.conference

    def get_round(self) -> str:
        return self.round

    def get_team1(self) -> str:
        return self.team1

    def get_team2(self) -> str:
        return self.team2

    def get_winner(self) -> str:
        return self.winner

    def get_num_games(self) -> int:
        return self.num_games

    # Setters
    def set_conference(self, conference: str) -> None:
        self.conference = conference

    def set_round(self, round: str) -> None:
        self.round = round

    def set_team1(self, team1: str) -> None:
        self.team1 = team1

    def set_team2(self, team2: str) -> None:
        self.team2 = team2


class Bracket(ABC):
    conference_round_names = ("first round", "Conference Semi-Finals", "Conference Finals")
    finals_round_name = "Finals"

    def __init__(self, name: str = ""):
        self.name = name
        self.first_round_matchups = self.get_first_round_matchups()
        self.conference_order = self._build_conference_order()
        self.games = self._build_first_round_games()

    @abstractmethod
    def get_first_round_matchups(self) -> list[tuple[str, str, str]]:
        pass

    def _ensure_structure_metadata(self) -> None:
        if not getattr(self, "first_round_matchups", None):
            first_round_games = [
                game for game in self.games
                if game.get_round() == self.conference_round_names[0]
            ]
            if not first_round_games:
                raise ValueError("Bracket must contain first-round games")
            self.first_round_matchups = [
                (game.get_conference(), game.get_team1(), game.get_team2())
                for game in first_round_games
            ]
        if not getattr(self, "conference_order", None):
            self.conference_order = self._build_conference_order()

    def _build_conference_order(self) -> list[str]:
        conference_order = []
        for conference, _, _ in self.first_round_matchups:
            if conference not in conference_order:
                conference_order.append(conference)
        return conference_order

    def _build_first_round_games(self) -> list[Game]:
        return [
            Game(conference, self.conference_round_names[0], team1, team2)
            for conference, team1, team2 in self.first_round_matchups
        ]

    def _build_next_round(self, games: list[Game], round_name: str) -> list[Game]:
        next_round_games = []
        for conference in self.conference_order:
            conference_games = [game for game in games if game.get_conference() == conference]
            if len(conference_games) < 2:
                continue
            for i in range(0, len(conference_games), 2):
                game1 = conference_games[i]
                game2 = conference_games[i + 1]
                next_round_games.append(
                    Game(conference, round_name, game1.get_winner(), game2.get_winner())
                )
        return next_round_games

    def _get_conference_champions(self, games: list[Game]) -> list[Game]:
        champions = []
        for conference in self.conference_order:
            conference_games = [game for game in games if game.get_conference() == conference]
            if len(conference_games) == 1:
                champions.append(conference_games[0])
        return champions

    def get_round_games(self, round_name: str) -> list[Game]:
        return [game for game in self.games if game.get_round() == round_name]

    def reset_to_first_round(self) -> None:
        self._ensure_structure_metadata()
        self.games = self._build_first_round_games()

    def create_next_round(self, current_round_games: list[Game]) -> list[Game]:
        self._ensure_structure_metadata()
        current_round_name = current_round_games[0].get_round()
        if current_round_name == self.conference_round_names[-1]:
            conference_champions = self._get_conference_champions(current_round_games)
            if len(conference_champions) != 2:
                raise ValueError("Bracket finals require exactly two conference champions")
            return [
                Game(
                    self.finals_round_name,
                    self.finals_round_name,
                    conference_champions[0].get_winner(),
                    conference_champions[1].get_winner(),
                )
            ]
        round_index = self.conference_round_names.index(current_round_name)
        return self._build_next_round(current_round_games, self.conference_round_names[round_index + 1])

    def fill(self) -> None:
        self._ensure_structure_metadata()
        current_round_games = self.games[:]
        for g in current_round_games:
            g.fill()

        round_index = 1
        while True:
            next_round_games = self._build_next_round(current_round_games, self.conference_round_names[round_index])
            if not next_round_games:
                break
            self.games.extend(next_round_games)
            for g in next_round_games:
                g.fill()
            current_round_games = next_round_games
            round_index += 1

        finals = self.create_next_round(current_round_games)[0]
        self.games.append(finals)
        finals.fill()

    def calculate_score(self, gt: "Bracket") -> int:
        if len(self.games) != len(gt.games):
            raise ValueError("Brackets must contain the same number of games for scoring")
        return sum(my_game.calculate_score(gt_game) for my_game, gt_game in zip(self.games, gt.games))

    def save(self) -> None:
        with open(self.name, 'wb') as f:
            pickle.dump(self, f)


class Bracket2025(Bracket):
    FIRST_ROUND_MATCHUPS = (
        ("west", "OKC", "Memphis"),
        ("west", "Denver", "LA Clippers"),
        ("west", "LA Lakers", "Minnesota"),
        ("west", "Houston", "GSW"),
        ("east", "Cleavland", "Miami Heat"),
        ("east", "Indiana", "Milwaukee"),
        ("east", "Knicks", "Pistons"),
        ("east", "Boston Celtics", "Orlando"),
    )

    def get_first_round_matchups(self) -> list[tuple[str, str, str]]:
        return list(self.FIRST_ROUND_MATCHUPS)
    

class Bracket2026(Bracket):
    # Reference team names for future bracket definitions:
    # Western Conference: Oklahoma City Thunder, Phoenix Suns,
    # Los Angeles Lakers, Houston Rockets, Denver Nuggets,
    # Minnesota Timberwolves, San Antonio Spurs, Portland Trail Blazers,
    # Memphis Grizzlies, Los Angeles Clippers, Golden State Warriors,
    # Dallas Mavericks, Sacramento Kings, New Orleans Pelicans, Utah Jazz.
    # Eastern Conference: Cleveland Cavaliers, Miami Heat, Indiana Pacers,
    # Milwaukee Bucks, New York Knicks, Detroit Pistons, Boston Celtics,
    # Orlando Magic, Toronto Raptors, Atlanta Hawks, Philadelphia 76ers,
    # Chicago Bulls, Charlotte Hornets, Brooklyn Nets, Washington Wizards.
    FIRST_ROUND_MATCHUPS = (
        ("west", "OKC", "Phoenix"),
        ("west", "LA Lakers", "Houston"),
        ("west", "Denver", "Minnesota"),
        ("west", "Spurs", "Portland Trail Blazers"),
        ("east", "Pistons", "Orlando"),
        ("east", "Cleveland", "Toronto Raptors"),
        ("east", "Knicks", "Atlanta Hawks"),
        ("east", "Boston Celtics", "Philadelphia 76ers"),
    )

    def get_first_round_matchups(self) -> list[tuple[str, str, str]]:
        return list(self.FIRST_ROUND_MATCHUPS)
