"""Testy matematyczne sterownika i demonstracji w pętli zamkniętej.

Autorzy: Jakub Kleemann, Piotr Treder. Uruchom w zad 2:
py -3 -m unittest discover -s tests -v
"""

import math
from pathlib import Path
import subprocess
import sys
import unittest

from fuzzy import FuzzySet, INPUTS, RULES, infer
from simulation import Room, trajectory


class ControllerTests(unittest.TestCase):
    """Sprawdź przynależności, inferencję i pokrycie dziedziny wejściowej."""

    def test_trapezoid_and_shoulders(self):
        """Sprawdź granice, nachylenia i poprawną obsługę pionowych ramion."""
        trapezoid = FuzzySet("test", (0, 2, 4, 6))
        for x, expected in ((-1, 0), (0, 0), (1, 0.5), (2, 1), (3, 1), (5, 0.5), (6, 0), (7, 0)):
            with self.subTest(x=x):
                self.assertAlmostEqual(trapezoid.membership(x), expected)
        self.assertEqual(FuzzySet("lewe", (0, 0, 2, 4)).membership(0), 1)
        self.assertEqual(FuzzySet("prawe", (0, 2, 4, 4)).membership(4), 1)
        with self.assertRaises(ValueError):
            FuzzySet("błędny", (0, 3, 2, 4))

    def test_centroids_against_analytic_shapes(self):
        """Porównaj centroidy z całkami analitycznymi, niezależnie od implementacji."""
        # Niski zbiór: prostokąt 0..15 oraz trójkąt 15..35.
        expected_low = (15 * 7.5 + 10 * (15 + 20 / 3)) / 25
        self.assertAlmostEqual(infer(10, 20, 500).speed, expected_low, delta=0.01)
        self.assertAlmostEqual(infer(25, 50, 1100).speed, 50, delta=0.01)
        self.assertAlmostEqual(infer(40, 90, 2200).speed, 100 - expected_low, delta=0.01)

    def test_mixed_memberships_and_rule_strength(self):
        """W punkcie mieszanym wiele reguł działa naraz, a AND jest minimum."""
        result = infer(28, 65, 1400)
        self.assertAlmostEqual(result.memberships[0][1], 0.8)
        self.assertAlmostEqual(result.memberships[1][2], 0.5)
        self.assertAlmostEqual(result.memberships[2][2], 0.2)
        self.assertEqual(sum(strength > 0 for strength in result.activations), 8)
        index = next(i for i, rule in enumerate(RULES) if rule.antecedents == (1, 2, 1))
        self.assertAlmostEqual(result.activations[index], 0.5)
        self.assertGreater(result.speed, 50)
        self.assertLess(result.speed, 100)

    def test_all_three_inputs_can_change_output(self):
        """Każde z trzech wejść rzeczywiście wpływa na sterowanie."""
        baseline = infer(15, 20, 500).speed
        for values in ((40, 20, 500), (15, 90, 500), (15, 20, 2200)):
            with self.subTest(values=values):
                self.assertGreater(infer(*values).speed, baseline + 50)

    def test_rule_base_is_complete_and_unique(self):
        """27 różnych reguł obejmuje każdą kombinację trzech zbiorów wejść."""
        self.assertEqual(len(RULES), 27)
        self.assertEqual(len({rule.antecedents for rule in RULES}), 27)

    def test_grid_coverage_including_boundaries(self):
        """1210 pozycji z brzegami dziedzin nie daje pustego agregatu ani NaN."""
        for temperature in range(0, 46, 5):
            for humidity in range(0, 101, 10):
                for co2 in range(400, 2501, 210):
                    with self.subTest(t=temperature, h=humidity, co2=co2):
                        result = infer(temperature, humidity, co2)
                        self.assertTrue(math.isfinite(result.speed))
                        self.assertTrue(0 <= result.speed <= 100)
                        self.assertGreater(max(result.activations), 0)

    def test_invalid_measurements_are_rejected(self):
        """Nie koryguj po cichu błędnych pomiarów sterownika."""
        for i, variable in enumerate(INPUTS):
            for bad in (variable.minimum - 1, variable.maximum + 1, math.nan, math.inf, -math.inf):
                values = [25, 50, 1000]
                values[i] = bad
                with self.subTest(i=i, bad=bad), self.assertRaises(ValueError):
                    infer(*values)

    def test_cli_help_and_invalid_measurement(self):
        """Pomoc CLI działa, a błędny pomiar kończy program kodem argparse 2."""
        app = Path(__file__).resolve().parents[1] / "app.py"
        help_result = subprocess.run([sys.executable, str(app), "--help"], capture_output=True)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn(b"--cli", help_result.stdout)
        invalid = subprocess.run([sys.executable, str(app), "--cli", "99", "50", "1000"], capture_output=True)
        self.assertEqual(invalid.returncode, 2)


class SimulationTests(unittest.TestCase):
    """Sprawdź, że obroty oddziałują na model, a model wraca na wejścia sterownika."""

    def test_ventilation_improves_all_three_values(self):
        """Przy tych samych źródłach wentylacja daje niższe T, H i CO₂."""
        off, on = Room(), Room()
        for _ in range(60):
            off.step(0, 1)
            on.step(100, 1)
        for passive, ventilated in zip(off.values(), on.values()):
            self.assertLess(ventilated, passive)

    def test_closed_loop_trajectory_is_reproducible(self):
        """Wyniki są deterministyczne, a sterownik reaguje na poprawę warunków."""
        rows = trajectory(120)
        self.assertEqual(len(rows), 121)
        self.assertEqual(rows, trajectory(120))
        for i in (1, 2, 3, 4):
            self.assertLess(rows[-1][i], rows[0][i])
        for row in rows:
            self.assertAlmostEqual(row[4], infer(*row[1:4]).speed)

    def test_simulation_rejects_invalid_parameters(self):
        """Nie dopuszczaj ujemnych czasów, obrotów ani nieskończonych danych."""
        for speed, seconds in ((-1, 1), (101, 1), (50, -1), (50, 61), (math.nan, 1), (50, math.inf)):
            with self.subTest(speed=speed, seconds=seconds), self.assertRaises(ValueError):
                Room().step(speed, seconds)
        with self.assertRaises(ValueError):
            trajectory(-1)


if __name__ == "__main__":
    unittest.main()
