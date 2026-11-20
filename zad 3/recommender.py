"""Filtracja kolaboratywna user–user z rekomendacjami i antyrekomendacjami.

Problem: proponowanie nieobejrzanych filmów/seriali na podstawie ocen grupy.
Autorzy: Jakub Kleemann, Piotr Treder.
Środowisko: Python >= 3.10, wyłącznie biblioteka standardowa.
Użycie: py -3 app.py --user "Jakub Kleemann" --compare.
Referencja: demo prowadzącego — Euclidean i Pearson na wspólnych ocenach.
"""

from collections import defaultdict
import csv
from dataclasses import dataclass
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parent
METRICS = ("Euclidean", "Pearson")


def common_ratings(dataset: dict, user1: str, user2: str) -> tuple[list[float], list[float]]:
    """Zwróć pary ocen wspólnych tytułów w stabilnej kolejności; sprawdź użytkowników."""
    if user1 not in dataset or user2 not in dataset:
        raise ValueError("Nie znaleziono użytkownika w danych.")
    common = sorted(dataset[user1].keys() & dataset[user2].keys())
    return ([dataset[user1][title] for title in common], [dataset[user2][title] for title in common])


def euclidean_score(dataset: dict, user1: str, user2: str) -> float:
    """Zwróć 1/(1+sqrt(sum((x-y)^2))) jak w demo; brak wspólnych ocen daje 0."""
    x, y = common_ratings(dataset, user1, user2)
    return 1 / (1 + math.sqrt(sum((a - b) ** 2 for a, b in zip(x, y)))) if x else 0.0


def pearson_score(dataset: dict, user1: str, user2: str) -> float:
    """Zwróć korelację Pearsona [-1,1]; brak ocen/zerowa wariancja daje 0 jak w demo."""
    x, y = common_ratings(dataset, user1, user2)
    if not x:
        return 0.0
    x_mean, y_mean = statistics.mean(x), statistics.mean(y)
    dx, dy = [a - x_mean for a in x], [b - y_mean for b in y]
    denominator = math.sqrt(sum(a * a for a in dx) * sum(b * b for b in dy))
    if denominator == 0:
        return 0.0
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(dx, dy)) / denominator))


@dataclass(frozen=True)
class Neighbor:
    """Podobny użytkownik: liczba wspólnych ocen, wynik demo i skorygowana waga."""

    user: str
    common: int
    similarity: float
    weight: float


@dataclass(frozen=True)
class Prediction:
    """Prognoza oceny 0–10, liczba oceniających, sąsiedzi i źródło prognozy."""

    title: str
    score: float
    rating_count: int
    neighbors: tuple[str, ...]
    source: str


@dataclass(frozen=True)
class Ranking:
    """Dwie rozłączne listy nieobejrzanych tytułów oraz porównywani sąsiedzi."""

    user: str
    metric: str
    recommendations: tuple[Prediction, ...]
    anti_recommendations: tuple[Prediction, ...]
    neighbors: tuple[Neighbor, ...]
    candidate_count: int


class Recommender:
    """Silnik user–user z minimalnym pokryciem i awaryjną średnią bayesowską."""

    def __init__(self, ratings: dict[str, dict[str, float]], watched: dict[str, set[str]] | None = None):
        """Skopiuj oceny, sprawdź skalę 0–10 i zbuduj indeks filmów.

        Parameters:
            ratings: Słownik osoba → tytuł → ocena, bez sztucznych zer za brak danych.
            watched: Opcjonalne obejrzane tytuły bez oceny, także wykluczane z wyników.
        Raises:
            ValueError: Zbiór nie ma ocen lub zawiera błędne wartości.
        """
        self.ratings = {user: dict(items) for user, items in ratings.items()}
        self.watched = {user: set((watched or {}).get(user, ())) | set(items) for user, items in self.ratings.items()}
        self.by_title = defaultdict(dict)
        for user, items in self.ratings.items():
            for title, rating in items.items():
                if not math.isfinite(rating) or not 0 <= rating <= 10:
                    raise ValueError("Oceny muszą być skończonymi liczbami w skali 0–10.")
                self.by_title[title][user] = rating
        all_ratings = [value for items in self.ratings.values() for value in items.values()]
        if not all_ratings:
            raise ValueError("Brak ocen do obliczenia rekomendacji.")
        self.global_mean = statistics.mean(all_ratings)
        self.means = {user: statistics.mean(items.values()) if items else self.global_mean
                      for user, items in self.ratings.items()}

    @classmethod
    def load(cls, path: Path = ROOT / "data/ratings.csv"):
        """Wczytaj CSV user,title,rating; pusta ocena nadal oznacza obejrzany tytuł."""
        ratings, watched = defaultdict(dict), defaultdict(set)
        with path.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                user, title = row["user"], row["title"]
                watched[user].add(title)
                ratings[user]  # zachowaj też osobę mającą wyłącznie puste oceny
                if row["rating"].strip():
                    if title in ratings[user]:
                        raise ValueError("Duplikat w CSV — uruchom prepare_data.py.")
                    ratings[user][title] = float(row["rating"])
        return cls(dict(ratings), dict(watched))

    def neighbors(self, user: str, metric: str) -> tuple[Neighbor, ...]:
        """Zwróć dodatnio podobnych sąsiadów z co najmniej 3 wspólnymi ocenami.

        Wynik z demo mnożymy przez n/(n+3), osłabiając małe próby.
        Ujemna korelacja i zerowa wariancja nie są używane jako pozytywna waga.
        """
        if user not in self.ratings:
            raise ValueError(f"Nieznany użytkownik: {user}")
        if metric not in METRICS:
            raise ValueError("Wybierz Euclidean lub Pearson.")
        function = euclidean_score if metric == "Euclidean" else pearson_score
        result = []
        for other in sorted(self.ratings):
            if other == user:
                continue
            common = len(self.ratings[user].keys() & self.ratings[other].keys())
            if common < 3:
                continue
            similarity = function(self.ratings, user, other)
            if similarity > 0:
                result.append(Neighbor(other, common, similarity, similarity * common / (common + 3)))
        return tuple(sorted(result, key=lambda neighbor: (-neighbor.weight, neighbor.user)))

    def predict(self, user: str, title: str, neighbors: tuple[Neighbor, ...]) -> Prediction:
        """Przewidź ocenę, łącząc do 5 sąsiadów oceniających film z prior.

        Prior = (suma ocen filmu + 3·średnia globalna)/(liczba ocen + 3).
        CF = średnia użytkownika + ważona średnia odchyleń ocen sąsiadów
        od ich własnych średnich. Wynik = (suma wag·CF + prior)/(suma wag+1).
        Brak sąsiadów filmu daje jawnie oznaczoną prognozę ogólną (prior).
        """
        votes = self.by_title[title]
        prior = (sum(votes.values()) + 3 * self.global_mean) / (len(votes) + 3)
        voters = tuple(neighbor for neighbor in neighbors if neighbor.user in votes)[:5]
        weight = sum(neighbor.weight for neighbor in voters)
        if weight:
            residual = sum(neighbor.weight * (votes[neighbor.user] - self.means[neighbor.user]) for neighbor in voters)
            collaborative = self.means[user] + residual / weight
            score = (weight * collaborative + prior) / (weight + 1)
        else:
            score = prior
        return Prediction(title, max(0.0, min(10.0, score)), len(votes), tuple(n.user for n in voters),
                          "sąsiedzi + prior" if voters else "ogólna (brak sąsiadów filmu)")

    def rank(self, user: str, metric: str = "Pearson", count: int = 5) -> Ranking:
        """Zwróć top-N i bottom-N, wykluczając obejrzane tytuły i duplikaty.

        Returns:
            Ranking z deterministycznym rozstrzyganiem remisów alfabetycznie.
        Raises:
            ValueError: Użytkownik/miara są nieznane lub brak 2·N kandydatów.
        """
        if not isinstance(count, int) or count < 1:
            raise ValueError("Liczba wyników musi być dodatnią liczbą całkowitą.")
        neighbors = self.neighbors(user, metric)
        predictions = [self.predict(user, title, neighbors) for title in sorted(self.by_title)
                       if title not in self.watched[user]]
        if len(predictions) < 2 * count:
            raise ValueError(f"Za mało nieobejrzanych tytułów ({len(predictions)}), potrzeba {2 * count}.")
        top = tuple(sorted(predictions, key=lambda item: (-item.score, item.title))[:count])
        selected = {item.title for item in top}
        bottom = tuple(sorted((item for item in predictions if item.title not in selected),
                              key=lambda item: (item.score, item.title))[:count])
        return Ranking(user, metric, top, bottom, neighbors, len(predictions))
