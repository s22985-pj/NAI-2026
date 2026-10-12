"""Nim — gra człowieka z AI minimax.

Autorzy: Jakub Kleemann, Piotr Treder.
Zasady: https://mathworld.wolfram.com/Nim.html (ostatni element wygrywa).
Środowisko: Python >= 3.10, wyłącznie biblioteka standardowa.
Start: Windows: py -3 nim.py; Linux/macOS: python3 nim.py.
Testy: py -3 -m unittest discover -s tests -v.
"""

import argparse
from functools import lru_cache
from typing import Iterator

State = tuple[int, ...]
Move = tuple[int, int]
DEFAULT_PILES: State = (3, 4, 5)


def legal_moves(state: State) -> Iterator[Move]:
    """Generuj wszystkie legalne ruchy w ustalonej kolejności.

    Parameters:
        state: Nieujemne liczebności stosów.
    Yields:
        Para (indeks stosu od 0, dodatnia liczba elementów do zabrania).
    """
    for pile, count in enumerate(state):
        for amount in range(1, count + 1):
            yield pile, amount


def apply_move(state: State, move: Move) -> State:
    """Wykonaj ruch bez modyfikowania wejściowej krotki.

    Parameters:
        state: Liczebności stosów.
        move: Indeks stosu od 0 i liczba do zabrania.
    Returns:
        Nowa krotka liczebności stosów.
    Raises:
        ValueError: Jeśli stos nie istnieje lub ilość jest niedozwolona.
    """
    pile, amount = move
    if not 0 <= pile < len(state):
        raise ValueError("Nie ma stosu o takim numerze.")
    if not 1 <= amount <= state[pile]:
        raise ValueError("Zabierz co najmniej 1 element, nie więcej niż jest na stosie.")
    return state[:pile] + (state[pile] - amount,) + state[pile + 1:]


@lru_cache(maxsize=None)
def minimax(state: State, ai_turn: bool) -> int:
    """Oceń pełne drzewo gry z perspektywy AI, pamiętając wyniki.

    Parameters:
        state: Nieujemne liczebności stosów.
        ai_turn: True oznacza turę AI (maksymalizację).
    Returns:
        +1 dla wymuszonego zwycięstwa AI, -1 dla wymuszonej porażki AI.
        Zakładamy optymalną grę obu stron.
    """
    if not any(state):
        # Gracz bez ruchu przegrał; przeciwnik zabrał ostatni element.
        return -1 if ai_turn else 1
    scores = (
        minimax(apply_move(state, move), not ai_turn)
        for move in legal_moves(state)
    )
    return max(scores) if ai_turn else min(scores)


def choose_ai_move(state: State) -> Move:
    """Wybierz ruch o największej ocenie minimax.

    Parameters:
        state: Niekońcowa pozycja gry.
    Returns:
        Ruch AI; przy równych ocenach pierwszy z legal_moves.
    Raises:
        ValueError: Jeśli gra jest zakończona.
    """
    if not any(state):
        raise ValueError("Gra jest zakończona — brak legalnych ruchów.")
    return max(
        legal_moves(state),
        key=lambda move: minimax(apply_move(state, move), False),
    )


def print_board(state: State) -> None:
    """Wyświetl stosy z trwałymi numerami od 1.

    Parameters:
        state: Liczebności stosów.
    Returns:
        None.
    """
    print()
    for pile, count in enumerate(state, start=1):
        print(f"Stos {pile}: {'|' * count or '-'} ({count})")


def read_human_move(state: State) -> Move | None:
    """Czytaj dane do poprawnego ruchu lub rezygnacji.

    Parameters:
        state: Bieżąca pozycja do walidacji ruchu.
    Returns:
        Legalny ruch lub None po q, EOF lub Ctrl+C.
    """
    while True:
        try:
            answer = input("Twój ruch [stos liczba, q = koniec]: ").strip()
            if answer.lower() == "q":
                return None
            parts = answer.split()
            if len(parts) != 2:
                print("Wpisz dwie liczby, np. 2 3.")
                continue
            try:
                pile, amount = map(int, parts)
            except ValueError:
                print("Numer stosu i liczba elementów muszą być liczbami całkowitymi.")
                continue
            move = pile - 1, amount
            apply_move(state, move)
            return move
        except ValueError as error:
            print(f"Błędny ruch: {error}")
        except (EOFError, KeyboardInterrupt):
            print()
            return None


def play(state: State, ai_first: bool = False, demo: bool = False) -> str:
    """Przeprowadź partię lub powtarzalną demonstrację.

    Parameters:
        state: Początkowe stosy z co najmniej jednym elementem.
        ai_first: Czy AI zaczyna.
        demo: Czy zastąpić wejście człowieka pierwszym legalnym ruchem.
    Returns:
        Nazwa zwycięzcy albo 'przerwano'.
    Raises:
        ValueError: Jeśli początkowa plansza jest pusta.
    """
    if not any(state):
        raise ValueError("Początkowa plansza nie może być pusta.")
    print("NIM | Człowiek vs AI (minimax)")
    print("Zabierz elementy z jednego stosu. Ostatni element wygrywa.")
    if demo:
        print("DEMO: człowiek zabiera 1 element z pierwszego niepustego stosu.")
    ai_turn = ai_first
    print_board(state)
    while any(state):
        player = "AI" if ai_turn else "Człowiek"
        if ai_turn:
            move = choose_ai_move(state)
        elif demo:
            move = next(legal_moves(state))
        else:
            move = read_human_move(state)
            if move is None:
                print("Gra przerwana.")
                return "przerwano"
        pile, amount = move
        print(f"{player}: stos {pile + 1}, zabiera {amount}.")
        state = apply_move(state, move)
        print_board(state)
        if not any(state):
            print(f"Wygrywa {player}!")
            return player
        ai_turn = not ai_turn
    raise AssertionError("Nieosiągalny stan gry")


def main() -> None:
    """Odczytaj opcje, sprawdź limity i uruchom grę.

    Returns:
        None. argparse zgłasza błąd dla niewłaściwej konfiguracji.
    """
    parser = argparse.ArgumentParser(description="Nim z AI minimax; ostatni element wygrywa.")
    parser.add_argument("--piles", type=int, nargs="+", default=DEFAULT_PILES,
                        help="1–4 stosy po 1–7 elementów (domyślnie: 3 4 5)")
    parser.add_argument("--first", choices=("human", "ai"), default="human",
                        help="kto zaczyna (domyślnie: human)")
    parser.add_argument("--demo", action="store_true", help="partia bez wpisywania ruchów")
    args = parser.parse_args()
    if not 1 <= len(args.piles) <= 4 or any(not 1 <= count <= 7 for count in args.piles):
        parser.error("Podaj od 1 do 4 stosów, każdy po 1–7 elementów.")
    play(tuple(args.piles), ai_first=args.first == "ai", demo=args.demo)


if __name__ == "__main__":
    main()
