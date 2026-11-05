"""Interaktywna demonstracja rozmytego sterowania wentylatorem.

Problem: temperatura, wilgotność i CO₂ → prędkość wentylatora [%].
Autorzy: Jakub Kleemann, Piotr Treder.
Środowisko: Python >= 3.10 z Tkinter (Windows: składnik instalatora Pythona).
Brak zewnętrznych pakietów. Start: py -3 app.py.
Konsola: py -3 app.py --cli 28 65 1400.
Demo CSV: py -3 app.py --demo --csv docs/demo.csv.
"""

import argparse
from collections import deque
import csv
import math
from pathlib import Path
import sys
import time

from fuzzy import INPUTS, OUTPUT, OUTPUT_GRID, RULES, infer
from simulation import Room, trajectory

COLORS = ("#0891b2", "#d97706", "#7c3aed")
BG = "#f1f5f9"
INK = "#0f172a"


class FanApp:
    """Okno Tkinter z suwakami, wykresami i symulacją w pętli zamkniętej."""

    def __init__(self, root) -> None:
        """Zbuduj interfejs w przekazanym oknie Tk i uruchom zegar GUI."""
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.root = root
        root.title("Zadanie 2 — Rozmyty sterownik wentylatora")
        root.geometry("1160x900")
        root.minsize(1100, 860)
        root.configure(bg=BG)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=INK, font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 22, "bold"))
        style.configure("Heading.TLabel", font=("Segoe UI", 12, "bold"))
        style.configure("Value.TLabel", font=("Segoe UI", 28, "bold"), foreground="#0f766e")
        style.configure("TButton", font=("Segoe UI", 10), padding=6)
        self.running = False
        self.updating = False
        self.elapsed = 0.0
        self.last_tick = time.monotonic()
        self.angle = 0.0
        self.history = deque(maxlen=120)
        self.result = None
        self.room = Room(28, 65, 1400)
        self.values = [tk.DoubleVar(root, value=x) for x in self.room.values()]
        self.readings = [tk.StringVar(root) for _ in INPUTS]

        body = ttk.Frame(root, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Rozmyty sterownik wentylatora", style="Title.TLabel").pack(anchor="w")
        ttk.Label(body, text="3 wejścia • 1 wyjście • Mamdani • 27 reguł • środek ciężkości").pack(anchor="w", pady=(2, 12))

        top = ttk.Frame(body)
        top.pack(fill="x")
        controls = ttk.Frame(top)
        controls.pack(side="left", fill="x", expand=True, padx=(0, 25))
        for i, variable in enumerate(INPUTS):
            row = ttk.Frame(controls)
            row.pack(fill="x", pady=4)
            ttk.Label(row, text=variable.label, width=17).pack(side="left")
            ttk.Scale(row, from_=variable.minimum, to=variable.maximum,
                      variable=self.values[i], command=self._on_slider).pack(side="left", fill="x", expand=True)
            ttk.Label(row, textvariable=self.readings[i], width=14, anchor="e").pack(side="left")
        presets = ttk.Frame(controls)
        presets.pack(fill="x", pady=(7, 0))
        for title, values in (("Chłodno / czysto", (18, 35, 500)),
                              ("Warunki pośrednie", (28, 65, 1400)),
                              ("Gorąco / duszno", (35, 80, 2000))):
            ttk.Button(presets, text=title, command=lambda v=values: self.preset(v)).pack(side="left", padx=(0, 6))
        summary = ttk.Frame(top)
        summary.pack(side="right")
        self.fan = tk.Canvas(summary, width=110, height=110, bg=BG, highlightthickness=0)
        self.fan.pack(side="left")
        value_box = ttk.Frame(summary)
        value_box.pack(side="left", padx=8)
        self.speed_text = tk.StringVar(root)
        ttk.Label(value_box, textvariable=self.speed_text, style="Value.TLabel").pack()
        ttk.Label(value_box, text="prędkość wentylatora").pack()

        bar = ttk.Frame(body)
        bar.pack(fill="x", pady=(14, 10))
        self.start_button = ttk.Button(bar, text="Start symulacji", command=self.toggle)
        self.start_button.pack(side="left")
        ttk.Button(bar, text="Reset", command=lambda: self.preset((28, 65, 1400))).pack(side="left", padx=8)
        self.status = tk.StringVar(root)
        ttk.Label(bar, textvariable=self.status).pack(side="left", padx=8)

        ttk.Label(body, text="1. Rozmywanie wejść — stopnie przynależności μ", style="Heading.TLabel").pack(anchor="w")
        charts = ttk.Frame(body)
        charts.pack(fill="x", pady=(5, 12))
        self.input_charts = []
        for i in range(3):
            charts.columnconfigure(i, weight=1)
            canvas = tk.Canvas(charts, width=330, height=145, bg="white", highlightthickness=0)
            canvas.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 0))
            self.input_charts.append(canvas)

        middle = ttk.Frame(body)
        middle.pack(fill="x")
        middle.columnconfigure(0, weight=1)
        middle.columnconfigure(1, weight=1)
        left = ttk.Frame(middle)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        ttk.Label(left, text="2. Agregacja wyjścia i wyostrzanie", style="Heading.TLabel").pack(anchor="w")
        self.output_chart = tk.Canvas(left, width=490, height=180, bg="white", highlightthickness=0)
        self.output_chart.pack(fill="x", pady=5)
        right = ttk.Frame(middle)
        right.grid(row=0, column=1, sticky="nsew")
        ttk.Label(right, text="Aktywne reguły — siła = minimum przesłanek", style="Heading.TLabel").pack(anchor="w")
        self.rules_text = tk.Text(right, height=10, width=58, wrap="word", font=("Segoe UI", 9),
                                  bg="white", fg=INK, relief="flat", padx=10, pady=8, state="disabled")
        self.rules_text.pack(fill="both", expand=True, pady=5)

        ttk.Label(body, text="3. Przebieg prędkości — ostatnie 120 próbek", style="Heading.TLabel").pack(anchor="w", pady=(8, 4))
        self.history_chart = tk.Canvas(body, width=1050, height=85, bg="white", highlightthickness=0)
        self.history_chart.pack(fill="both", expand=True)
        ttk.Label(body, text="Symulacja: 10 s modelu / 1 s rzeczywistą; odświeżanie co 0,2 s. Suwaki pozwalają wprowadzać zakłócenia.").pack(anchor="w", pady=(8, 0))
        ttk.Label(body, text="Wentylacja z dopływem świeżego powietrza • model edukacyjny • autorzy: Jakub Kleemann, Piotr Treder").pack(anchor="w")
        self._evaluate()
        for canvas in (*self.input_charts, self.output_chart, self.history_chart):
            canvas.bind("<Configure>", lambda event: self._render())
        root.after(200, self._tick)

    def _on_slider(self, unused=None) -> None:
        """Przelicz sterowanie po zmianie wejścia, także jako zakłócenie symulacji."""
        if not self.updating:
            self.room = Room(*(value.get() for value in self.values))
            self._evaluate()

    def _sync_values(self) -> None:
        """Przenieś pomiary z modelu do suwaków bez rekurencyjnych callbacków."""
        self.updating = True
        try:
            for variable, value in zip(self.values, self.room.values()):
                variable.set(value)
        finally:
            self.updating = False

    def preset(self, values: tuple[float, float, float]) -> None:
        """Wczytaj scenariusz, zatrzymaj symulację i wyzeruj czas oraz historię."""
        self.running = False
        self.start_button.configure(text="Start symulacji")
        self.room = Room(*values)
        self.elapsed = 0.0
        self.history.clear()
        self._sync_values()
        self._evaluate()

    def toggle(self) -> None:
        """Uruchom lub wstrzymaj model, zachowując jego bieżący stan."""
        self.running = not self.running
        self.last_tick = time.monotonic()
        self.start_button.configure(text="Pauza" if self.running else "Wznów symulację")
        self._update_status()

    def _update_status(self) -> None:
        """Wyświetl tryb i czas modelu bez sugerowania podłączenia czujników."""
        mode = "Symulacja działa" if self.running else "Tryb ręczny / pauza"
        self.status.set(f"{mode} | czas modelu: {self.elapsed:.1f} s")

    def _evaluate(self) -> None:
        """Oblicz wynik, zapisz próbkę i odśwież wykresy oraz objaśnienia."""
        self.result = infer(*self.room.values())
        for text, value, variable in zip(self.readings, self.room.values(), INPUTS):
            text.set(f"{value:.1f} {variable.unit}")
        self.speed_text.set(f"{self.result.speed:.1f}%")
        self.history.append(self.result.speed)
        self._update_status()
        active = [(i, strength) for i, strength in enumerate(self.result.activations) if strength > 0]
        active.sort(key=lambda item: (-item[1], item[0]))
        lines = []
        for i, strength in active:
            rule = RULES[i]
            labels = [var.sets[index].name for var, index in zip(INPUTS, rule.antecedents)]
            lines.append(f"R{i + 1:02} | μ={strength:.3f} | T: {labels[0]}, H: {labels[1]}, CO₂: {labels[2]} → {OUTPUT.sets[rule.consequent].name}")
        self.rules_text.configure(state="normal")
        self.rules_text.delete("1.0", "end")
        self.rules_text.insert("1.0", "\n".join(lines))
        self.rules_text.configure(state="disabled")
        self._render()

    def _axes(self, canvas, minimum: float, maximum: float, title: str, y_max: int = 1):
        """Narysuj osie i zwróć funkcje przeliczenia współrzędnych wykresu."""
        canvas.delete("all")
        width, height = max(100, canvas.winfo_width()), max(100, canvas.winfo_height())
        x0, y0, x1, y1 = 35, height - 42, width - 15, 34
        canvas.create_text(12, 14, text=title, anchor="w", fill=INK, font=("Segoe UI", 9, "bold"))
        canvas.create_line(x0, y1, x0, y0, x1, y0, fill="#94a3b8")
        canvas.create_text(x0 - 16, y1, text=str(y_max), fill="#64748b")
        canvas.create_text(x0 - 13, y0, text="0", fill="#64748b")
        canvas.create_text(x0, y0 + 12, text=f"{minimum:g}", fill="#64748b")
        canvas.create_text(x1, y0 + 12, text=f"{maximum:g}", fill="#64748b")
        return (lambda x: x0 + (x - minimum) / (maximum - minimum) * (x1 - x0),
                lambda y: y0 - y * (y0 - y1))

    def _render(self) -> None:
        """Narysuj zbiory wejść, agregat wyjścia, centroid i historię obrotów."""
        if self.result is None:
            return
        for i, (canvas, variable, value) in enumerate(zip(self.input_charts, INPUTS, self.room.values())):
            x, y = self._axes(canvas, variable.minimum, variable.maximum, variable.label)
            for j, fuzzy_set in enumerate(variable.sets):
                a, b, c, d = fuzzy_set.points
                canvas.create_line(x(a), y(0), x(b), y(1), x(c), y(1), x(d), y(0), fill=COLORS[j], width=2)
                canvas.create_text(12 + j * 108, canvas.winfo_height() - 10, anchor="w",
                                   text=f"{fuzzy_set.name}: {self.result.memberships[i][j]:.2f}", fill=COLORS[j], font=("Segoe UI", 8))
            canvas.create_line(x(value), y(0), x(value), y(1), fill=INK, dash=(3, 3))
        x, y = self._axes(self.output_chart, 0, 100, "Prędkość [%] | kolor: agregat; linia: centroid")
        polygon = [x(0), y(0)]
        for value, mu in zip(OUTPUT_GRID, self.result.aggregate):
            polygon.extend((x(value), y(mu)))
        polygon.extend((x(100), y(0)))
        self.output_chart.create_polygon(polygon, fill="#99f6e4", outline="#0f766e")
        self.output_chart.create_line(x(self.result.speed), y(0), x(self.result.speed), y(1), fill=INK, width=2)
        self.output_chart.create_text(x(self.result.speed), y(1) - 12, text=f"{self.result.speed:.1f}%", fill=INK)
        x, y = self._axes(self.history_chart, 0, 119, "Prędkość [%] (oś pozioma: kolejne próbki)", y_max=100)
        if len(self.history) > 1:
            points = [coordinate for i, speed in enumerate(self.history) for coordinate in (x(i), y(speed / 100))]
            self.history_chart.create_line(points, fill="#0f766e", width=2)
        self._draw_fan()

    def _draw_fan(self) -> None:
        """Narysuj umowny wirnik; animacja obrazuje względną prędkość, nie RPM."""
        self.fan.delete("all")
        self.fan.create_oval(8, 8, 102, 102, outline="#cbd5e1", width=2)
        for blade in range(3):
            points = []
            for radius, offset in ((7, -20), (40, -10), (42, 25), (14, 50)):
                angle = math.radians(self.angle + blade * 120 + offset)
                points.extend((55 + radius * math.cos(angle), 55 + radius * math.sin(angle)))
            self.fan.create_polygon(points, fill="#0f766e")
        self.fan.create_oval(47, 47, 63, 63, fill=INK, outline=INK)

    def _tick(self) -> None:
        """Co 0,2 s zastosuj wynik sterowania do modelu i odśwież animację."""
        now = time.monotonic()
        dt = min(0.5, now - self.last_tick)
        self.last_tick = now
        if self.running:
            self.room.step(self.result.speed, dt * 10)
            self.elapsed += dt * 10
            self._sync_values()
            self._evaluate()
        self.angle = (self.angle + self.result.speed * dt * 3) % 360
        self._draw_fan()
        self.root.after(200, self._tick)


def main() -> None:
    """Uruchom GUI, pojedyncze wnioskowanie w konsoli albo demonstrację CSV."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Rozmyty sterownik wentylatora — Mamdani")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--cli", type=float, nargs=3, metavar=("TEMP", "HUM", "CO2"), help="przelicz °C, %% i ppm bez GUI")
    mode.add_argument("--demo", action="store_true", help="wykonaj powtarzalną symulację bez GUI")
    parser.add_argument("--duration", type=int, default=120, help="czas demo 0–3600 sekund (domyślnie 120)")
    parser.add_argument("--csv", type=Path, help="zapisz próbki demonstracji w pliku CSV")
    args = parser.parse_args()
    if args.csv is not None and not args.demo:
        parser.error("--csv wymaga --demo")
    try:
        if args.cli:
            result = infer(*args.cli)
            print(f"Temperatura: {args.cli[0]:g} °C | wilgotność: {args.cli[1]:g}% | CO₂: {args.cli[2]:g} ppm")
            print(f"Prędkość wentylatora: {result.speed:.2f}%")
            for i, (rule, strength) in enumerate(zip(RULES, result.activations), start=1):
                if strength > 0:
                    print(f"R{i:02} | {strength:.3f} | {rule.description()}")
        elif args.demo:
            rows = trajectory(args.duration)
            if args.csv is not None:
                args.csv.parent.mkdir(parents=True, exist_ok=True)
                with args.csv.open("w", newline="", encoding="utf-8") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(("time_s", "temperature_c", "humidity_percent", "co2_ppm", "fan_percent"))
                    writer.writerows(tuple(round(value, 4) for value in row) for row in rows)
            print("czas [s] | T [°C] | H [%] | CO₂ [ppm] | wentylator [%]")
            selected = [row for i, row in enumerate(rows) if i % 20 == 0 or i == len(rows) - 1]
            for t, temperature, humidity, co2, speed in selected:
                print(f"{t:8.0f} | {temperature:6.2f} | {humidity:5.2f} | {co2:9.2f} | {speed:13.2f}")
            if args.csv:
                print(f"Zapisano: {args.csv}")
        else:
            import tkinter as tk
            root = tk.Tk()
            FanApp(root)
            root.mainloop()
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
