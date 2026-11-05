"""Sterowanie wentylacją z użyciem logiki rozmytej Mamdaniego.

Problem: dobór prędkości wentylatora na podstawie temperatury [°C],
wilgotności względnej [%] i stężenia CO₂ [ppm] jako wskaźnika wentylacji.
Autorzy: Jakub Kleemann, Piotr Treder.
Środowisko: Python >= 3.10, biblioteka standardowa; instalacja pakietów zbędna.
Start GUI: py -3 app.py. Konsola: py -3 app.py --cli 28 65 1400.
Metoda: https://www.mathworks.com/help/fuzzy/fuzzy-inference-process.html
"""

from dataclasses import dataclass
from itertools import product
import math


@dataclass(frozen=True)
class FuzzySet:
    """Nazwany trapez; powtórzone wierzchołki tworzą lewe/prawe ramię.

    Attributes:
        name: Polska nazwa lingwistyczna zbioru.
        points: Cztery rosnące niemalejąco współrzędne (a, b, c, d).
    """

    name: str
    points: tuple[float, float, float, float]

    def __post_init__(self) -> None:
        """Sprawdź geometrię trapezu; zgłoś ValueError dla błędnych punktów."""
        a, b, c, d = self.points
        if not all(math.isfinite(x) for x in self.points) or not a <= b <= c <= d or a == d:
            raise ValueError("Trapez wymaga a <= b <= c <= d oraz a < d.")

    def membership(self, value: float) -> float:
        """Zwróć stopień przynależności wartości do trapezu w przedziale [0, 1]."""
        a, b, c, d = self.points
        if value < a or value > d:
            return 0.0
        if b <= value <= c:
            return 1.0
        if value < b:
            return (value - a) / (b - a)
        return (d - value) / (d - c)


@dataclass(frozen=True)
class Variable:
    """Opis zmiennej: etykieta, jednostka, zakres i trzy zbiory rozmyte."""

    label: str
    unit: str
    minimum: float
    maximum: float
    sets: tuple[FuzzySet, FuzzySet, FuzzySet]

    def fuzzify(self, value: float) -> tuple[float, ...]:
        """Rozmyj skończoną wartość; poza zakresem zgłoś ValueError."""
        if not math.isfinite(value) or not self.minimum <= value <= self.maximum:
            raise ValueError(
                f"{self.label}: podaj wartość od {self.minimum:g} do "
                f"{self.maximum:g} {self.unit}."
            )
        return tuple(fuzzy_set.membership(value) for fuzzy_set in self.sets)


INPUTS = (
    Variable("Temperatura", "°C", 0, 45, (
        FuzzySet("niska", (0, 0, 16, 23)),
        FuzzySet("umiarkowana", (18, 23, 27, 32)),
        FuzzySet("wysoka", (27, 34, 45, 45)),
    )),
    Variable("Wilgotność", "%", 0, 100, (
        FuzzySet("niska", (0, 0, 25, 45)),
        FuzzySet("umiarkowana", (30, 45, 55, 70)),
        FuzzySet("wysoka", (55, 75, 100, 100)),
    )),
    Variable("Stężenie CO₂", "ppm", 400, 2500, (
        FuzzySet("niskie", (400, 400, 650, 1000)),
        FuzzySet("podwyższone", (750, 1050, 1300, 1650)),
        FuzzySet("wysokie", (1300, 1800, 2500, 2500)),
    )),
)

OUTPUT = Variable("Prędkość wentylatora", "%", 0, 100, (
    FuzzySet("niska", (0, 0, 15, 35)),
    FuzzySet("średnia", (20, 50, 50, 80)),
    FuzzySet("wysoka", (65, 85, 100, 100)),
))


@dataclass(frozen=True)
class Rule:
    """Reguła AND: indeksy zbiorów trzech wejść i zbioru wyjściowego."""

    antecedents: tuple[int, int, int]
    consequent: int

    def description(self) -> str:
        """Zwróć czytelną postać reguły IF–THEN."""
        conditions = [
            f"{variable.label}: {variable.sets[index].name}"
            for variable, index in zip(INPUTS, self.antecedents)
        ]
        return " ORAZ ".join(conditions) + f" → obroty: {OUTPUT.sets[self.consequent].name}"


# Pełne 3 × 3 × 3 = 27 reguł. Największa potrzeba wentylacji ustala
# zbiór konsekwencji reguły, a NIE bezpośrednią wartość wyjściową.
RULES = tuple(Rule(indices, max(indices)) for indices in product(range(3), repeat=3))
OUTPUT_GRID = tuple(index / 4 for index in range(401))
OUTPUT_CURVES = tuple(
    tuple(fuzzy_set.membership(x) for x in OUTPUT_GRID) for fuzzy_set in OUTPUT.sets
)


@dataclass(frozen=True)
class Inference:
    """Wynik i dane objaśniające proces wnioskowania.

    Attributes:
        speed: Wyostrzona prędkość w procentach.
        memberships: Stopnie przynależności dla każdego z trzech wejść.
        activations: Siła każdej z 27 reguł, w kolejności RULES.
        output_strengths: Maksymalna aktywacja każdego zbioru wyjściowego.
        aggregate: Zagregowany zbiór wyjścia na siatce OUTPUT_GRID.
    """

    speed: float
    memberships: tuple[tuple[float, ...], ...]
    activations: tuple[float, ...]
    output_strengths: tuple[float, ...]
    aggregate: tuple[float, ...]


def infer(temperature: float, humidity: float, co2: float) -> Inference:
    """Oblicz obroty metodą Mamdaniego: AND=min, implikacja=min, agregacja=max.

    Parameters:
        temperature: Temperatura w zakresie 0–45 °C.
        humidity: Wilgotność względna w zakresie 0–100%.
        co2: Stężenie CO₂ w zakresie 400–2500 ppm.
    Returns:
        Wynik z prędkością [%], przynależnościami i aktywacjami reguł.
        Centroid jest przybliżany całkowaniem trapezowym co 0,25 p.p.
    Raises:
        ValueError: Dane są nieskończone, NaN lub poza zakresem.
        RuntimeError: Nie ma pokrycia reguł (błąd definicji sterownika).
    """
    memberships = tuple(
        variable.fuzzify(value)
        for variable, value in zip(INPUTS, (temperature, humidity, co2))
    )
    activations = tuple(
        min(memberships[i][index] for i, index in enumerate(rule.antecedents))
        for rule in RULES
    )
    strengths = tuple(
        max(strength for rule, strength in zip(RULES, activations) if rule.consequent == level)
        for level in range(3)
    )
    aggregate = tuple(
        max(min(strengths[level], OUTPUT_CURVES[level][i]) for level in range(3))
        for i in range(len(OUTPUT_GRID))
    )
    # W całkowaniu trapezowym końce mają wagę 1/2. Wspólny krok
    # siatki skraca się w ilorazie momentu do pola powierzchni.
    weights = tuple(
        mu * (0.5 if i in (0, len(aggregate) - 1) else 1.0)
        for i, mu in enumerate(aggregate)
    )
    area = sum(weights)
    if area <= 0:
        raise RuntimeError("Żadna reguła nie pokrywa podanych wejść.")
    speed = sum(x * weight for x, weight in zip(OUTPUT_GRID, weights)) / area
    return Inference(speed, memberships, activations, strengths, aggregate)
