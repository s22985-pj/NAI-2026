"""Niezależne testy importu, miar podobieństwa, predykcji i rankingów.

Autorzy: Jakub Kleemann, Piotr Treder. Python >= 3.10, bez zależności.
Start z katalogu zad 3: py -3 -m unittest discover -s tests -v.
"""

import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from evaluate import evaluate
from prepare_data import ROOT, parse_survey, title_key
from recommender import METRICS, Recommender, euclidean_score, pearson_score


class SimilarityTests(unittest.TestCase):
    """Porównaj implementację miar ze znanymi wynikami analitycznymi."""

    def test_euclidean_3_4_5_triangle(self):
        """Różnice 3 i 4 dają odległość 5, czyli podobieństwo 1/6."""
        data = {"a": {"x": 1, "y": 2}, "b": {"x": 4, "y": 6, "unseen": 10}}
        self.assertAlmostEqual(euclidean_score(data, "a", "b"), 1 / 6)
        self.assertEqual(euclidean_score(data, "a", "a"), 1)

    def test_pearson_shift_reverse_and_constant(self):
        """Pearson rozpoznaje przesunięcie skali, odwrotność i zerową wariancję."""
        data = {"a": {"x": 1, "y": 3, "z": 5}, "b": {"x": 3, "y": 5, "z": 7},
                "c": {"x": 5, "y": 3, "z": 1}, "d": {"x": 4, "y": 4, "z": 4}}
        self.assertAlmostEqual(pearson_score(data, "a", "b"), 1)
        self.assertAlmostEqual(pearson_score(data, "a", "c"), -1)
        self.assertEqual(pearson_score(data, "a", "d"), 0)

    def test_no_common_and_unknown_users(self):
        """Brak wspólnych ocen daje zero, a nieznana osoba czytelny wyjątek."""
        for function in (euclidean_score, pearson_score):
            self.assertEqual(function({"a": {"x": 1}, "b": {"y": 1}}, "a", "b"), 0)
            with self.assertRaises(ValueError):
                function({"a": {}}, "a", "missing")


class ImportTests(unittest.TestCase):
    """Sprawdź czyszczenie danych bez dopisywania wymyślonych ocen."""

    def test_alias_duplicate_zero_and_missing_rating(self):
        """Duplikaty są uśredniane, brak nie staje się zerem, zero nie znika."""
        rows, report = parse_survey("A\tThe Matrix\t10\tMatrix\t6\tBrak oceny\tFilm zero\t0", {"The Matrix": "Matrix"})
        result = {row["title"]: row["rating"] for row in rows}
        self.assertEqual(result, {"Matrix": 8, "Brak oceny": None, "Film zero": 0})
        self.assertEqual(len(report["duplicates"]), 1)
        self.assertEqual(report["zero_ratings"], 1)

    def test_numeric_title_and_blank_cells(self):
        """Numeryczne tytuły i nadmiarowe tabulatory nie przesuwają ocen."""
        rows, _ = parse_survey("A\t1670\t9\t2012\t3\tDoktor\t\t8\t\t", {})
        self.assertEqual({row["title"]: row["rating"] for row in rows}, {"1670": 9, "2012": 3, "Doktor": 8})
        self.assertEqual(title_key(" Dzień ŚWIRA! "), title_key("dzień świra"))

    def test_out_of_range_rating_rejected(self):
        """Błędnych ocen nie importujemy jako poprawnych obserwacji."""
        for text in ("A\tFilm\t11", "A\tFilm\t-1"):
            with self.assertRaises(ValueError):
                parse_survey(text, {})

    def test_prepared_data_is_reproducible(self):
        """Zapisany raport odpowiada dokładnie surowemu plikowi i aliasom."""
        aliases = json.loads((ROOT / "data/aliases.json").read_text(encoding="utf-8"))
        _, report = parse_survey((ROOT / "data/source.tsv").read_text(encoding="utf-8-sig"), aliases)
        self.assertEqual(report, json.loads((ROOT / "data/cleaning_report.json").read_text(encoding="utf-8")))


class RankingTests(unittest.TestCase):
    """Sprawdź wykluczenia, rozłączność list, cold start i ostrożną predykcję."""

    @classmethod
    def setUpClass(cls):
        """Wczytaj rzeczywistą ankietę raz dla testów integracyjnych."""
        cls.engine = Recommender.load()

    def test_every_user_has_five_disjoint_unseen_results(self):
        """Obie miary dla wszystkich 13 osób dają 5+5 różnych nieobejrzanych tytułów."""
        for user in self.engine.ratings:
            for metric in METRICS:
                with self.subTest(user=user, metric=metric):
                    result = self.engine.rank(user, metric)
                    all_items = (*result.recommendations, *result.anti_recommendations)
                    titles = {item.title for item in all_items}
                    self.assertEqual(len(result.recommendations), 5)
                    self.assertEqual(len(result.anti_recommendations), 5)
                    self.assertEqual(len(titles), 10)
                    self.assertFalse(titles & self.engine.watched[user])
                    self.assertTrue(all(math.isfinite(item.score) and 0 <= item.score <= 10 for item in all_items))
                    self.assertGreaterEqual(min(i.score for i in result.recommendations), max(i.score for i in result.anti_recommendations))
                    self.assertEqual(result, self.engine.rank(user, metric))

    def test_missing_rating_still_counts_as_watched(self):
        """Pulp Fiction bez oceny u Aleksandra nie wraca jako nieobejrzany tytuł."""
        self.assertIn("Pulp Fiction", self.engine.watched["Aleksander Kozłowicz"])
        self.assertNotIn("Pulp Fiction", self.engine.ratings["Aleksander Kozłowicz"])

    def test_cold_start_uses_explicit_prior(self):
        """Jedna ocena nie tworzy pozornie wiarygodnego podobnego użytkownika."""
        result = self.engine.rank("Aleksander Kozłowicz")
        self.assertFalse(result.neighbors)
        self.assertTrue(all(not p.neighbors for p in (*result.recommendations, *result.anti_recommendations)))
        item = result.recommendations[0]
        votes = self.engine.by_title[item.title]
        self.assertAlmostEqual(item.score, (sum(votes.values()) + 3 * self.engine.global_mean) / (len(votes) + 3))

    def test_personalized_prediction_against_hand_calculation(self):
        """Jedyny identyczny sąsiad ma wagę 1/2; prognoza jest obliczalna ręcznie."""
        model = Recommender({"u": {"a": 2, "b": 4, "c": 6},
                             "v": {"a": 2, "b": 4, "c": 6, "x": 10}})
        neighbors = model.neighbors("u", "Pearson")
        self.assertEqual(neighbors[0].weight, 0.5)
        prior = (10 + 3 * (34 / 7)) / 4
        cf = 4 + (10 - 5.5)
        self.assertAlmostEqual(model.predict("u", "x", neighbors).score, (0.5 * cf + prior) / 1.5)

    def test_zero_is_preserved_and_csv_paths_work(self):
        """Ocena 0 i pusta ocena mają inne znaczenie po odczycie CSV."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ratings.csv"
            path.write_text("user,title,rating\na,x,0\na,y,\nb,x,7\n", encoding="utf-8")
            model = Recommender.load(path)
            self.assertEqual(model.ratings["a"]["x"], 0)
            self.assertNotIn("y", model.ratings["a"])
            self.assertIn("y", model.watched["a"])

    def test_invalid_configuration_and_small_catalog(self):
        """Zgłaszaj nieznane osoby/miary i za mały katalog zamiast powielać tytuły."""
        for user, metric in (("nieznany", "Pearson"), ("Piotr Treder", "wrong")):
            with self.assertRaises(ValueError):
                self.engine.rank(user, metric)
        with self.assertRaises(ValueError):
            Recommender({"a": {"x": 7}}).rank("a")
        with self.assertRaises(ValueError):
            Recommender({"a": {"x": math.nan}})

    def test_leave_one_out_removes_held_out_rating(self):
        """Dwie oceny tego samego filmu przewidują siebie wyłącznie z drugiej oceny."""
        result = evaluate(Recommender({"a": {"x": 0}, "b": {"x": 10}}))
        self.assertEqual(result["evaluated"], 2)
        self.assertEqual(result["metrics"]["Prior"]["mae"], 10)
        self.assertEqual(result["metrics"]["Pearson"]["mae"], 10)

    def test_cli_help_and_unknown_user(self):
        """CLI działa także poza katalogiem projektu i poprawnie zgłasza błędy."""
        app = ROOT / "app.py"
        result = subprocess.run([sys.executable, str(app), "--help"], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([sys.executable, str(app), "--user", "missing"], capture_output=True)
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
