"""Silnik rekomendacji filmów/seriali — demonstracja zadania 3.

Problem: 5 rekomendacji i 5 antyrekomendacji nieobejrzanych tytułów.
Autorzy: Jakub Kleemann, Piotr Treder.
Środowisko: Python >= 3.10; GUI wymaga Tkinter, brak zewnętrznych pakietów.
Start: py -3 app.py. CLI: py -3 app.py --user "Piotr Treder" --compare.
Przykłady: py -3 app.py --demo. Dane: data/ratings.csv.
Referencje: demo prowadzącego; szczegóły i źródła w README.md.
"""

import argparse
from dataclasses import asdict
import json
import sys

from recommender import METRICS, ROOT, Recommender, euclidean_score, pearson_score

SCENARIOS = ("Jakub Kleemann", "Piotr Treder", "Aleksander Kozłowicz")


def format_ranking(ranking) -> str:
    """Zwróć czytelny raport obu list wraz z pochodzeniem i wsparciem prognoz."""
    lines = [f"{ranking.user} | {ranking.metric} | kandydaci: {ranking.candidate_count}"]
    if not ranking.neighbors:
        lines.append("BRAK WIARYGODNYCH SĄSIADÓW: ranking ogólny, bez personalizacji.")
    for title, items in (("5 REKOMENDACJI", ranking.recommendations),
                         ("5 ANTYREKOMENDACJI (najniższe prognozy)", ranking.anti_recommendations)):
        lines.append(title)
        for i, item in enumerate(items, 1):
            lines.append(f"{i}. {item.title} | {item.score:.2f}/10 | ocen: {item.rating_count} | {item.source}")
    lines.append("SĄSIEDZI (min. 3 wspólne oceny):")
    for neighbor in ranking.neighbors:
        lines.append(f"  {neighbor.user}: wspólne={neighbor.common}, podobieństwo={neighbor.similarity:.4f}, waga={neighbor.weight:.4f}")
    return "\n".join(lines)


def comparison(engine: Recommender, user: str) -> str:
    """Porównaj top-5 i bottom-5 dwóch miar; nie deklaruj jakości bez walidacji."""
    left, right = (engine.rank(user, metric) for metric in METRICS)
    top_overlap = len({item.title for item in left.recommendations} & {item.title for item in right.recommendations})
    anti_overlap = len({item.title for item in left.anti_recommendations} & {item.title for item in right.anti_recommendations})
    return (f"Euclidean vs Pearson: wspólne top-5: {top_overlap}/5; wspólne bottom-5: {anti_overlap}/5.\n"
            f"Lider Euclidean: {left.recommendations[0].title} ({left.recommendations[0].score:.2f}); "
            f"lider Pearson: {right.recommendations[0].title} ({right.recommendations[0].score:.2f}).")


def save_scenarios(engine: Recommender) -> str:
    """Zapisz trzy scenariusze × dwie miary jako JSON oraz czytelny raport TXT."""
    rankings = [engine.rank(user, metric) for user in SCENARIOS for metric in METRICS]
    report = "\n\n".join(format_ranking(ranking) for ranking in rankings)
    report += "\n\n" + "\n".join(f"{user}: {comparison(engine, user)}" for user in SCENARIOS) + "\n"
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs/scenarios.json").write_text(json.dumps([asdict(r) for r in rankings], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "docs/scenarios.txt").write_text(report, encoding="utf-8")
    return report


class RecommendationApp:
    """GUI do wyboru użytkownika, porównania miar i prezentacji trzech scenariuszy."""

    def __init__(self, root, engine: Recommender) -> None:
        """Zbuduj okno i wyświetl domyślny scenariusz Jakuba Kleemanna."""
        import tkinter as tk
        from tkinter import ttk

        self.engine, self.root = engine, root
        self.user = tk.StringVar(root, value=SCENARIOS[0])
        self.metric = tk.StringVar(root, value="Pearson")
        self.summary, self.details = tk.StringVar(root), tk.StringVar(root)
        self.comparison_text, self.warning = tk.StringVar(root), tk.StringVar(root)
        self.predictions = {}
        root.title("Zadanie 3 — Rekomendacje filmów i seriali")
        root.geometry("1180x900")
        root.minsize(1140, 880)
        root.configure(bg="#f1f5f9")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background="#f1f5f9")
        style.configure("TLabel", background="#f1f5f9", foreground="#0f172a", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 22, "bold"))
        style.configure("Heading.TLabel", font=("Segoe UI", 12, "bold"))
        style.configure("Warning.TLabel", foreground="#9a3412")
        style.configure("Treeview", rowheight=30, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        style.configure("TButton", padding=6, font=("Segoe UI", 10))
        style.configure("TRadiobutton", background="#f1f5f9", font=("Segoe UI", 10))
        body = ttk.Frame(root, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Co obejrzeć następnie?", style="Title.TLabel").pack(anchor="w")
        ttk.Label(body, text="Silnik filmów i seriali • filtracja kolaboratywna user–user • Euclidean / Pearson").pack(anchor="w", pady=(3, 12))
        controls = ttk.Frame(body)
        controls.pack(fill="x")
        ttk.Label(controls, text="Użytkownik:").pack(side="left", padx=(0, 8))
        users = ttk.Combobox(controls, textvariable=self.user, values=sorted(engine.ratings), state="readonly", width=30)
        users.pack(side="left", padx=(0, 20))
        users.bind("<<ComboboxSelected>>", lambda event: self.refresh())
        for metric in METRICS:
            ttk.Radiobutton(controls, text=metric, variable=self.metric, value=metric, command=self.refresh).pack(side="left", padx=8)
        scenarios = ttk.Frame(body)
        scenarios.pack(fill="x", pady=(12, 10))
        ttk.Label(scenarios, text="Scenariusze:").pack(side="left", padx=(0, 8))
        for i, user in enumerate(SCENARIOS, 1):
            ttk.Button(scenarios, text=f"{i}. {user}", command=lambda selected=user: self.select(selected)).pack(side="left", padx=(0, 8))
        ttk.Label(body, textvariable=self.summary).pack(anchor="w")
        ttk.Label(body, textvariable=self.warning, style="Warning.TLabel").pack(anchor="w", pady=(3, 8))
        tables = ttk.Frame(body)
        tables.pack(fill="x")
        tables.columnconfigure(0, weight=1)
        tables.columnconfigure(1, weight=1)
        self.tables = []
        for i, title in enumerate(("5 rekomendacji", "5 antyrekomendacji — najniższe prognozy")):
            panel = ttk.Frame(tables)
            panel.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 12, 0))
            ttk.Label(panel, text=title, style="Heading.TLabel").pack(anchor="w", pady=(0, 7))
            tree = ttk.Treeview(panel, columns=("title", "score", "votes", "source"), show="headings", height=5, selectmode="browse")
            for column, label, width in (("title", "Tytuł", 290), ("score", "Ocena*", 65),
                                          ("votes", "Ocen", 45), ("source", "Źródło", 105)):
                tree.heading(column, text=label)
                tree.column(column, width=width, minwidth=width, stretch=column == "title", anchor="w" if column == "title" else "center")
            tree.pack(fill="x")
            tree.bind("<<TreeviewSelect>>", lambda event, table=tree: self.explain(table))
            self.tables.append(tree)
        ttk.Label(body, text="* Prognozowana ocena w skali 0–10. CF = sąsiedzi + prior; ogólna = tylko średnia bayesowska.").pack(anchor="w", pady=(8, 4))
        ttk.Label(body, textvariable=self.details, wraplength=1110).pack(anchor="w", pady=(0, 10))
        ttk.Label(body, text="Podobni użytkownicy — minimum 3 wspólne oceny", style="Heading.TLabel").pack(anchor="w", pady=(0, 6))
        neighbor_panel = ttk.Frame(body)
        neighbor_panel.pack(fill="x")
        self.neighbor_table = ttk.Treeview(neighbor_panel, columns=("user", "common", "similarity", "weight"), show="headings", height=4)
        for column, label, width in (("user", "Użytkownik", 340), ("common", "Wspólne oceny", 150),
                                      ("similarity", "Podobieństwo (jak w demo)", 250), ("weight", "Waga po korekcie małej próby", 260)):
            self.neighbor_table.heading(column, text=label)
            self.neighbor_table.column(column, width=width, anchor="w" if column == "user" else "center")
        self.neighbor_table.pack(side="left", fill="x", expand=True)
        scrollbar = ttk.Scrollbar(neighbor_panel, orient="vertical", command=self.neighbor_table.yview)
        scrollbar.pack(side="right", fill="y")
        self.neighbor_table.configure(yscrollcommand=scrollbar.set)
        ttk.Label(body, text="Porównanie dwóch miar", style="Heading.TLabel").pack(anchor="w", pady=(12, 5))
        ttk.Label(body, textvariable=self.comparison_text, wraplength=1110).pack(anchor="w")
        ttk.Label(body, text="Antyrekomendacje to najmniej obiecujące propozycje modelu, nie pewność, że dany tytuł się nie spodoba.", style="Warning.TLabel").pack(anchor="w", pady=(14, 3))
        ttk.Label(body, text="Autorzy: Jakub Kleemann, Piotr Treder • dane: ankieta grupy • obejrzane tytuły są wykluczane").pack(anchor="w")
        self.refresh()

    def select(self, user: str) -> None:
        """Przełącz na jeden z trzech powtarzalnych scenariuszy demonstracyjnych."""
        self.user.set(user)
        self.refresh()

    def refresh(self) -> None:
        """Przelicz ranking, porównanie i objaśnienia po zmianie osoby lub miary."""
        user, metric = self.user.get(), self.metric.get()
        ranking = self.engine.rank(user, metric)
        self.summary.set(f"{user} | ocen: {len(self.engine.ratings[user])} | obejrzane: {len(self.engine.watched[user])} | kandydaci: {ranking.candidate_count} | miara: {metric}")
        self.warning.set("Brak wiarygodnych sąsiadów — wyniki ogólne, bez personalizacji." if not ranking.neighbors
                         else "Wyniki łączą opinie podobnych użytkowników z ostrożną prognozą ogólną.")
        self.predictions = {}
        for tree, items in zip(self.tables, (ranking.recommendations, ranking.anti_recommendations)):
            tree.delete(*tree.get_children())
            for i, item in enumerate(items):
                tree.insert("", "end", iid=str(i), values=(item.title, f"{item.score:.2f}", item.rating_count, "CF + prior" if item.neighbors else "ogólna"))
                self.predictions[tree, str(i)] = item
        self.neighbor_table.delete(*self.neighbor_table.get_children())
        for neighbor in ranking.neighbors:
            self.neighbor_table.insert("", "end", values=(neighbor.user, neighbor.common, f"{neighbor.similarity:.4f}", f"{neighbor.weight:.4f}"))
        self.details.set("Kliknij tytuł, aby zobaczyć pełną nazwę i osoby wspierające prognozę.")
        self.comparison_text.set(comparison(self.engine, user))

    def explain(self, tree) -> None:
        """Pokaż pełny tytuł i sąsiadów wspierających zaznaczoną prognozę."""
        if tree.selection():
            item = self.predictions.get((tree, tree.selection()[0]))
            if item:
                self.details.set(f"{item.title} — {item.source}. Sąsiedzi filmu: {', '.join(item.neighbors) or 'brak'}.")


def main() -> None:
    """Obsłuż GUI, CLI, porównanie podobieństw i eksport trzech scenariuszy."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Zadanie 3: rekomendacje filmów i seriali")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--user", help="użytkownik do rekomendacji w konsoli")
    mode.add_argument("--demo", action="store_true", help="zapisz trzy scenariusze dla obu miar")
    mode.add_argument("--pair", nargs=2, metavar=("USER1", "USER2"), help="porównaj podobieństwo dwóch użytkowników jak w demo")
    parser.add_argument("--metric", choices=METRICS, default="Pearson")
    parser.add_argument("--compare", action="store_true", help="pokaż rankingi dla obu miar (wymaga --user)")
    args = parser.parse_args()
    if args.compare and not args.user:
        parser.error("--compare wymaga --user")
    try:
        engine = Recommender.load()
        if args.user:
            for metric in METRICS if args.compare else (args.metric,):
                print(format_ranking(engine.rank(args.user, metric)), "\n")
            if args.compare:
                print(comparison(engine, args.user))
        elif args.demo:
            print(save_scenarios(engine))
        elif args.pair:
            function = euclidean_score if args.metric == "Euclidean" else pearson_score
            common = len(engine.ratings.get(args.pair[0], {}).keys() & engine.ratings.get(args.pair[1], {}).keys())
            print(f"{args.metric}: {function(engine.ratings, *args.pair):.6f}; wspólne oceny: {common}")
        else:
            import tkinter as tk
            root = tk.Tk()
            RecommendationApp(root, engine)
            root.mainloop()
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
