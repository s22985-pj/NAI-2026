"""Porównanie Euclidean, Pearson i średniej bayesowskiej metodą leave-one-out.

Autorzy: Jakub Kleemann, Piotr Treder. Python >= 3.10, bez zależności.
Start: py -3 evaluate.py. Wyniki: docs/evaluation.json.
Każda oceniana obserwacja jest usuwana przed obliczeniem wszystkich statystyk.
"""

import json
import math

from recommender import METRICS, ROOT, Recommender


def evaluate(engine: Recommender) -> dict:
    """Oblicz MAE i RMSE na tych samych obserwacjach dla dwóch miar i prior.

    Tytuły bez żadnej innej oceny po odłożeniu próbki są pomijane.
    Wyniki badają przewidywanie ocen, a nie trafność top-5 w przyszłości.
    """
    errors = {metric: [] for metric in (*METRICS, "Prior")}
    personalized = {metric: 0 for metric in METRICS}
    total = sum(len(items) for items in engine.ratings.values())
    for user, items in engine.ratings.items():
        for title, actual in items.items():
            if len(engine.by_title[title]) < 2:
                continue
            train = {person: dict(ratings) for person, ratings in engine.ratings.items()}
            del train[user][title]
            model = Recommender(train)
            for metric in METRICS:
                prediction = model.predict(user, title, model.neighbors(user, metric))
                errors[metric].append(prediction.score - actual)
                personalized[metric] += bool(prediction.neighbors)
            errors["Prior"].append(model.predict(user, title, ()).score - actual)
    return {"method": "leave-one-out, no held-out rating in training statistics",
            "total_ratings": total,
            "evaluated": len(errors["Prior"]),
            "skipped_unique_titles": total - len(errors["Prior"]),
            "metrics": {metric: {"mae": sum(abs(e) for e in values) / len(values) if values else None,
                                 "rmse": math.sqrt(sum(e * e for e in values) / len(values)) if values else None,
                                 "personalized_predictions": personalized.get(metric, 0)}
                        for metric, values in errors.items()}}


def main() -> None:
    """Zapisz odtwarzalne wyniki walidacji dla danych ankiety."""
    result = evaluate(Recommender.load())
    (ROOT / "docs").mkdir(exist_ok=True)
    payload = json.dumps(result, indent=2) + "\n"
    (ROOT / "docs/evaluation.json").write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
