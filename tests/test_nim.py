"""Testy reguł Nim i niezależna weryfikacja minimax."""

import contextlib
import io
import itertools
import unittest
from unittest.mock import patch

from nim import apply_move, choose_ai_move, legal_moves, minimax, play, read_human_move


class NimTests(unittest.TestCase):
    """Sprawdź ruchy, końce partii i AI względem twierdzenia o Nim."""

    def test_legal_moves_skip_empty_piles(self):
        """Pusty stos nie ma ruchów; pełny dopuszcza wszystkie ilości."""
        self.assertEqual(list(legal_moves((0, 2))), [(1, 1), (1, 2)])

    def test_move_preserves_original_and_pile_numbers(self):
        """Wejście jest niezmienne, a pusty stos zachowuje numer."""
        state = (1, 2, 3)
        self.assertEqual(apply_move(state, (1, 2)), (1, 0, 3))
        self.assertEqual(state, (1, 2, 3))

    def test_invalid_moves(self):
        """Odrzuć nieistniejące stosy i niewłaściwe ilości."""
        for move in [(-1, 1), (3, 1), (0, 0), (0, -1), (0, 2), (1, 1)]:
            with self.subTest(move=move), self.assertRaises(ValueError):
                apply_move((1, 0, 3), move)

    def test_terminal_values(self):
        """Pusta plansza oznacza porażkę gracza na ruchu."""
        self.assertEqual(minimax((0, 0), True), -1)
        self.assertEqual(minimax((0, 0), False), 1)
        with self.assertRaises(ValueError):
            choose_ai_move((0, 0))

    def test_minimax_against_independent_nim_theorem(self):
        """Porównaj 124 niepuste pozycje z niezależnym wzorcem XOR."""
        for state in itertools.product(range(5), repeat=3):
            if not any(state):
                continue
            xor = state[0] ^ state[1] ^ state[2]
            with self.subTest(state=state):
                self.assertEqual(minimax(state, True), 1 if xor else -1)
                self.assertEqual(minimax(state, False), -1 if xor else 1)
                move = choose_ai_move(state)
                self.assertIn(move, list(legal_moves(state)))
                after = apply_move(state, move)
                if xor:
                    self.assertEqual(after[0] ^ after[1] ^ after[2], 0)

    def test_last_element_wins(self):
        """AI bierze cały samotny stos; ostatni element daje zwycięstwo."""
        self.assertEqual(choose_ai_move((0, 3, 0)), (1, 3))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(play((1,), ai_first=True), "AI")
            self.assertEqual(play((1,), demo=True), "Człowiek")

    def test_invalid_input_does_not_end_turn(self):
        """Błędne dane nie uniemożliwiają poprawnego ruchu w tej samej turze."""
        with patch("builtins.input", side_effect=["abc", "x 1", "1 0", "3 1", "2 2"]):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(read_human_move((1, 2)), (1, 2))

    def test_quit_and_end_of_input(self):
        """Rezygnacja i EOF kończą wprowadzanie bez ruchu."""
        with patch("builtins.input", return_value="q"):
            self.assertIsNone(read_human_move((1,)))
        with patch("builtins.input", side_effect=EOFError):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertIsNone(read_human_move((1,)))


if __name__ == "__main__":
    unittest.main()
