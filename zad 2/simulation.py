"""Uproszczony model pomieszczenia do demonstracji regulatora w pętli zamkniętej.

Autorzy: Jakub Kleemann, Piotr Treder. Python >= 3.10, bez dodatkowych pakietów.
Model edukacyjny zakłada wentylator wywiewny i dopływ chłodniejszego,
suchszego powietrza o mniejszym stężeniu CO₂, a nie samą cyrkulację.
"""

from dataclasses import dataclass
import math

from fuzzy import INPUTS, infer


@dataclass
class Room:
    """Wirtualne pomieszczenie z temperaturą [°C], wilgotnością [%] i CO₂ [ppm]."""

    temperature: float = 30.0
    humidity: float = 75.0
    co2: float = 1800.0

    def values(self) -> tuple[float, float, float]:
        """Zwróć aktualne pomiary w kolejności wejść sterownika."""
        return self.temperature, self.humidity, self.co2

    def step(self, speed: float, seconds: float) -> None:
        """Zaktualizuj model metodą Eulera z podkrokami nie większymi niż 0,2 s.

        Parameters:
            speed: Prędkość wentylatora 0–100%.
            seconds: Nieujemny czas symulowany w sekundach.
        Returns:
            None; stan pomieszczenia zostaje zmieniony.
        Raises:
            ValueError: Parametry lub stan są poza zakresem / nieskończone.
        """
        for variable, value in zip(INPUTS, self.values()):
            variable.fuzzify(value)
        if not math.isfinite(speed) or not 0 <= speed <= 100:
            raise ValueError("Prędkość musi wynosić 0–100%.")
        if not math.isfinite(seconds) or not 0 <= seconds <= 60:
            raise ValueError("Krok symulacji musi wynosić 0–60 s.")
        substeps = max(1, math.ceil(seconds / 0.2))
        dt = seconds / substeps
        exchange = 0.002 + 0.025 * speed / 100
        for _ in range(substeps):
            self.temperature += dt * (0.045 + exchange * (18 - self.temperature))
            self.humidity += dt * (0.08 + exchange * (40 - self.humidity))
            self.co2 += dt * (8 + exchange * (420 - self.co2))
            self.temperature, self.humidity, self.co2 = (
                min(variable.maximum, max(variable.minimum, value))
                for variable, value in zip(INPUTS, self.values())
            )


def trajectory(duration: int = 120) -> list[tuple[float, ...]]:
    """Zwróć co sekundę (czas, temperatura, wilgotność, CO₂, obroty) dla demo.

    Parameters:
        duration: Całkowity czas symulowany 0–3600 sekund.
    Returns:
        Lista próbek obejmująca początek i koniec symulacji w pętli zamkniętej.
    """
    if not isinstance(duration, int) or not 0 <= duration <= 3600:
        raise ValueError("Czas demonstracji: liczba całkowita 0–3600 s.")
    room = Room()
    rows = []
    for second in range(duration + 1):
        result = infer(*room.values())
        rows.append((float(second), *room.values(), result.speed))
        if second < duration:
            room.step(result.speed, 1)
    return rows
