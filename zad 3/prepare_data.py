"""Import i audyt ankiety: osoba, tytuł, ocena, tytuł, ocena, ...

Problem: przygotowanie danych dla silnika rekomendacji filmów/seriali.
Autorzy: Jakub Kleemann, Piotr Treder. Python >= 3.10, bez pakietów pip.
Użycie: py -3 prepare_data.py. Pliki są odczytywane względem tego modułu.
Źródło: ankieta dostarczona przez użytkownika, zachowana w data/source.tsv.
"""

from collections import defaultdict
import csv
import json
from pathlib import Path
import re
import statistics
import unicodedata

ROOT = Path(__file__).resolve().parent


def title_key(title: str) -> str:
    """Zwróć klucz bez różnic wielkości liter, diakrytyki i interpunkcji."""
    normalized = unicodedata.normalize("NFKD", title.casefold().replace("ł", "l"))
    plain = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", plain))


def parse_survey(text: str, aliases: dict[str, str]) -> tuple[list[dict], dict]:
    """Oczyść ankietę, zachowując obejrzane tytuły bez ocen i raportując duplikaty.

    Parameters:
        text: Wiersze TSV z osobą, następnie parami tytuł/ocena.
        aliases: Jawne mapowanie rozpoznanych wariantów tytułu.
    Returns:
        Wiersze user/title/rating i raport zmian. Sprzeczne duplikaty
        zastępuje średnia; pusta ocena pozostaje None, zero jest prawdziwą oceną.
    Raises:
        ValueError: Osierocona ocena lub liczba poza skalą 0–10.
    """
    alias_map = {title_key(key): value for key, value in aliases.items()}
    titles = {}
    entries = defaultdict(list)
    changes = []
    source_ratings = 0
    for line_number, line in enumerate(text.splitlines(), 1):
        tokens = [token.strip() for token in line.split("\t") if token.strip()]
        if not tokens:
            continue
        user, *tokens = tokens
        index = 0
        while index < len(tokens):
            original = tokens[index]
            # 1670 i 2012 są poprawnymi numerycznymi tytułami, nie ocenami.
            if re.fullmatch(r"(?:[0-9]|10)(?:[.,]0+)?", original):
                raise ValueError(f"Wiersz {line_number}: ocena bez tytułu: {original}")
            if re.fullmatch(r"-?\d+(?:[.,]\d+)?", original) and not re.fullmatch(r"\d{4}", original):
                raise ValueError(f"Wiersz {line_number}: błędna ocena: {original}")
            canonical = alias_map.get(title_key(original), original)
            key = title_key(canonical)
            canonical = titles.setdefault(key, canonical)
            if canonical != original:
                changes.append({"user": user, "from": original, "to": canonical})
            rating = None
            if index + 1 < len(tokens):
                candidate = tokens[index + 1].replace(",", ".")
                if re.fullmatch(r"\d+(?:\.\d+)?", candidate) and float(candidate) <= 10:
                    rating = float(candidate)
                    source_ratings += 1
                    index += 1
                elif re.fullmatch(r"-?\d+(?:\.\d+)?", candidate) and float(candidate) < 0:
                    raise ValueError(f"Wiersz {line_number}: ujemna ocena: {candidate}")
                elif re.fullmatch(r"\d+(?:\.\d+)?", candidate) and not re.fullmatch(r"\d{4}", candidate):
                    raise ValueError(f"Wiersz {line_number}: ocena poza skalą: {candidate}")
            entries[user, canonical].append(rating)
            index += 1
    rows, duplicates, missing = [], [], []
    for (user, title), values in sorted(entries.items()):
        ratings = [value for value in values if value is not None]
        rating = statistics.mean(ratings) if ratings else None
        rows.append({"user": user, "title": title, "rating": rating})
        if len(values) > 1:
            duplicates.append({"user": user, "title": title, "original": values, "mean": rating})
        if not ratings:
            missing.append({"user": user, "title": title})
    report = {
        "users": len({row["user"] for row in rows}),
        "titles": len(titles),
        "source_ratings": source_ratings,
        "unique_ratings": sum(row["rating"] is not None for row in rows),
        "zero_ratings": sum(row["rating"] == 0 for row in rows),
        "missing_ratings": missing,
        "duplicates": duplicates,
        "title_changes": changes,
    }
    return rows, report


def main() -> None:
    """Zapisz odtwarzalne ratings.csv i cleaning_report.json na podstawie źródła."""
    aliases = json.loads((ROOT / "data/aliases.json").read_text(encoding="utf-8"))
    rows, report = parse_survey((ROOT / "data/source.tsv").read_text(encoding="utf-8-sig"), aliases)
    with (ROOT / "data/ratings.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("user", "title", "rating"))
        writer.writeheader()
        writer.writerows(rows)
    (ROOT / "data/cleaning_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    compatible = {user: {} for user in sorted({row["user"] for row in rows})}
    for row in rows:
        if row["rating"] is not None:
            compatible[row["user"]][row["title"]] = row["rating"]
    (ROOT / "data/ratings.json").write_text(
        json.dumps(compatible, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Users: {report['users']}, titles: {report['titles']}, ratings: {report['unique_ratings']}")


if __name__ == "__main__":
    main()
