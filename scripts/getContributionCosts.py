from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable
from PyPDF2 import PdfReader

import calendar
import csv
import re

from smartmeter.config import DATA_DIR

TARIFF_DIR = DATA_DIR / "tarrifs"
OUTPUT_FILE = DATA_DIR / "input" / "Bijdragen.csv"
FILE_PREFIX = "DATS24_ELEKTRICITEIT"

COLUMNS = [
    "Van",
    "Tot",
    "Energiebijdrage",
    "Federale_bijdrage_0_3000",
    "Federale_bijdrage_3000_20000",
    "Federale_bijdrage_20000_50000",
    "Federale_bijdrage_50000_100000",
    "Bijdrage_energiefonds_residentiële_gebruiker",
    "Bijdrage_energiefonds_niet_residentiële_gebruiker",
]

MONTHS = {
    "januari": 1,
    "februari": 2,
    "maart": 3,
    "april": 4,
    "mei": 5,
    "juni": 6,
    "juli": 7,
    "augustus": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "december": 12,
}

NUMBER = r"\d+(?:[.,\s]\d{3})*"
NUMBER_RE = re.compile(NUMBER)
UNIT_RATE_RE = re.compile(r"(?:c\s*€|€\s*c)\s*/\s*k\s*Wh", re.I)
UNIT_MONTH_RE = re.compile(r"€\s*/\s*(?:maand|mois)", re.I)

@dataclass
class PdfLine:
    page_number: int
    y: float
    text: str

@dataclass
class ParsedContributions:
    energiebijdrage: Decimal
    federale_0_3000: Decimal
    federale_3000_20000: Decimal
    federale_20000_50000: Decimal
    federale_50000_100000: Decimal
    energiefonds_residentieel: Decimal
    energiefonds_niet_residentieel: Decimal

def contributions_to_csv(row: ParsedContributions, van: str, tot: str) -> None:
    return {
        "Van": van,
        "Tot": tot,
        "Energiebijdrage": format_rate(row.energiebijdrage),
        "Federale_bijdrage_0_3000": format_rate(row.federale_0_3000),
        "Federale_bijdrage_3000_20000": format_rate(row.federale_3000_20000),
        "Federale_bijdrage_20000_50000": format_rate(row.federale_20000_50000),
        "Federale_bijdrage_50000_100000": format_rate(row.federale_50000_100000),
        "Bijdrage_energiefonds_residentiële_gebruiker": format_fund(row.energiefonds_residentieel),
        "Bijdrage_energiefonds_niet_residentiële_gebruiker": format_fund(row.energiefonds_niet_residentieel),
    }

def to_decimal(raw: str) -> Decimal:
    cleaned = raw.strip().replace("\u00a0", "").replace(" ", "")
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid decimal string: {raw!r}") from exc

def format_rate(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.00001'), rounding=ROUND_HALF_UP):.5f}"

def format_fund(value: Decimal) -> str:
    if value == 0:
        return "0"
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"

def reconstruct_lines(reader: PdfReader) -> list[PdfLine]:
    result = []
    unit_fragment = re.compile(r"(?:c\s*€|€\s*c)\s*/\s*k\s*Wh|€\s*/\s*(?:maand|mois)", re.I)
    for page_number, page in enumerate(reader.pages, start=1):
        fragments = []
        orphaned_pairs = []
        last_tariff_label = None
        label_pattern = re.compile(
            r"Energiebijdrage|Cotisation sur l’énergie|Federale Accijns|Accise fédérale|"
            r"Verbruik tussen|Consommation entre|Tweede verblijf|Résidence secondaire|"
            r"Hoofdverblijf|Résidence principale|Aansluitingsvergoeding|Redevance de raccordement",
            re.I,
        )
        def visitor(text, _cm, tm, _font_dict, _font_size):
            nonlocal last_tariff_label
            value = text.replace("\r", " ").replace("\n", " ").strip()
            if not value:
                return
            x, y = float(tm[4]), float(tm[5])
            if abs(x) < 0.01 and abs(y) < 0.01 and unit_fragment.search(value):
                if last_tariff_label:
                    orphaned_pairs.append((last_tariff_label, value))
            elif abs(x) > 0.01 or abs(y) > 0.01:
                fragments.append((y, x, value))
                if label_pattern.search(value):
                    last_tariff_label = value
        try:
            page.extract_text(visitor_text=visitor)
        except TypeError as exc:
            raise RuntimeError(f"PDF parsing failed on page {page_number}") from exc
        fragments.sort(key=lambda item: (-item[0], item[1]))
        grouped = []
        for fragment in fragments:
            y = fragment[0]
            if not grouped or abs(grouped[-1][0][0] - y) > 1.8:
                grouped.append([fragment])
            else:
                grouped[-1].append(fragment)
        page_lines = []
        for group in grouped:
            group.sort(key=lambda item: item[1])
            page_lines.append(
                PdfLine(page_number, group[0][0], " ".join(item[2] for item in group))
            )
        for label, value in orphaned_pairs:
            unit = unit_fragment.search(value)
            if not unit:
                continue
            amount_match = re.search(r"(\d+(?:[,.]\d+)?)\s*$", value[: unit.start()])
            if not amount_match:
                continue
            amount = amount_match.group(1)
            for index, line in enumerate(page_lines):
                if label in line.text:
                    old = page_lines[index]
                    page_lines[index] = PdfLine(
                        old.page_number, old.y, f"{old.text} {amount} {unit.group(0)}"
                    )
                    break
        result.extend(page_lines)
    return result

def extract_pdf(path: Path) -> tuple[str, list[PdfLine]]:
    reader = PdfReader(str(path))
    lines = reconstruct_lines(reader)
    text = "\n".join(line.text for line in lines)
    return text, lines

def month_period(year: int, month: int) -> tuple[str, str]:
    last_day = calendar.monthrange(year, month)[1]
    return (
        date(year, month, 1).strftime("%d/%m/%Y"),
        date(year, month, last_day).strftime("%d/%m/%Y"),
    )

def find_period(path: Path, text: str) -> tuple[str, str] | None:
    match = re.search(r"(20\d{2})[-_.]?(0[1-9]|1[0-2])(?!\d)", path.stem)
    if match:
        return month_period(int(match.group(1)), int(match.group(2)))
    match = re.search(r"(0[1-9]|1[0-2])[-_.](20\d{2})", path.stem)
    if match:
        return month_period(int(match.group(2)), int(match.group(1)))
    match = re.search(
        r"(\d{1,2})[/.](\d{1,2})[/.](20\d{2}).{0,60}?"
        r"(\d{1,2})[/.](\d{1,2})[/.](20\d{2})",
        text,
        flags=re.S,
    )
    if match:
        day1, month1, year1, day2, month2, year2 = map(int, match.groups())
        return (
            date(year1, month1, day1).strftime("%d/%m/%Y"),
            date(year2, month2, day2).strftime("%d/%m/%Y"),
        )
    month_names = "|".join(MONTHS)
    match = re.search(rf"\b({month_names})\s+(20\d{{2}})\b", text, flags=re.I)
    if match:
        return month_period(int(match.group(2)), MONTHS[match.group(1).lower()])
    return None

def numbers_before_unit(line: str, unit_pattern: re.Pattern[str]) -> list[Decimal]:
    values = []
    for unit in unit_pattern.finditer(line):
        prefix = line[: unit.start()]
        match = re.search(r"(\d+(?:[,.]\d+)?)\s*$", prefix)
        if match:
            values.append(to_decimal(match.group(1)))
    return values

def range_from_line(line: str) -> tuple[int, int] | None:
    patterns = (
        rf"(?:verbruik|consommation)\s+(?:tussen|entre)\s+({NUMBER})\s*k\s*Wh\s+"
        rf"(?:en|et)\s+({NUMBER})\s*k\s*Wh",
        rf"(?:van|de)\s+({NUMBER})\s*k\s*Wh\s+(?:tot|à)\s+({NUMBER})\s*k\s*Wh",
        rf"({NUMBER})\s*k\s*Wh\s*(?:-|–|tot|à)\s*({NUMBER})\s*k\s*Wh",
    )
    for pattern in patterns:
        match = re.search(pattern, line, flags=re.I)
        if match:
            lower = int(re.sub(r"[.,\s]", "", match.group(1)))
            upper = int(re.sub(r"[.,\s]", "", match.group(2)))
            return lower, upper
    return None

def find_section(lines: list[PdfLine], start_label: str, end_label: str | None) -> list[PdfLine]:
    start = next((index for index, line in enumerate(lines) if re.search(start_label, line.text, re.I)), None)
    if start is None:
        raise ValueError(f"Sectie niet gevonden: {start_label}")
    end = len(lines)
    if end_label:
        for index in range(start + 1, len(lines)):
            if re.search(end_label, lines[index].text, re.I):
                end = index
                break
    return lines[start:end]

def unique_value(values: Iterable[Decimal], description: str, prefix: str) -> Decimal:
    unique = sorted(set(values))
    if len(unique) != 1:
        raise ValueError(f"{prefix}{description} niet eenduidig gevonden: {unique}")
    return unique[0]

def parse_energiebijdrage(lines: list[PdfLine], prefix: str) -> Decimal:
    candidates: list[Decimal] = []
    for line in lines:
        if re.search(r"\bEnergiebijdrage\b|Cotisation\s+sur\s+l[’']énergie", line.text, re.I):
            candidates.extend(numbers_before_unit(line.text, UNIT_RATE_RE))
    return unique_value(candidates, "Energiebijdrage", prefix)

def parse_federal_tiers(lines: list[PdfLine], prefix: str) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    section = find_section(lines, r"Federale\s+Accijns|Accise\s+fédérale", r"Bijdrage\s+Energiefonds|Cotisation\s+Fonds\s+énergie|Contribution\s+Fonds\s+énergie")
    intervals = {}
    for line in section:
        interval = range_from_line(line.text)
        if interval is None:
            continue
        rates = numbers_before_unit(line.text, UNIT_RATE_RE)
        if len(rates) != 1:
            raise ValueError(
                f"{prefix}Federale rij {interval} bevat niet exact één c€/kWh-tarief: {rates}"
            )
        if interval in intervals and intervals[interval] != rates[0]:
            raise ValueError(f"{prefix}Tegenstrijdige federale tarieven voor interval {interval}")
        intervals[interval] = rates[0]
    first = intervals.get((0, 3000))
    second = intervals.get((3000, 20000))
    combined = intervals.get((0, 20000))
    if combined is not None:
        first = first if first is not None else combined
        second = second if second is not None else combined
    third = intervals.get((20000, 50000))
    fourth = intervals.get((50000, 1000000))
    missing = [
        label
        for label, value in (
            ("0-3.000 kWh", first),
            ("3.000-20.000 kWh", second),
            ("20.000-50.000 kWh", third),
            ("50.000-1.000.000 kWh", fourth),
        )
        if value is None
    ]
    if missing:
        raise ValueError(f"{prefix}Federale verbruiksschijven ontbreken: {', '.join(missing)}")
    return first, second, third, fourth

def parse_energiefonds(lines: list[PdfLine], prefix: str) -> tuple[Decimal, Decimal]:
    section = find_section(
        lines,
        r"Bijdrage\s+Energiefonds|Cotisation\s+Fonds\s+énergie|Contribution\s+Fonds\s+énergie",
        r"Aansluitingsvergoeding|Redevance\s+de\s+raccordement",
    )
    residential = []
    non_residential_monthly = []
    for line in section:
        if re.search(r"Hoofdverblijf|domicilie|résidence\s+principale", line.text, re.I):
            residential.extend(numbers_before_unit(line.text, UNIT_MONTH_RE))
        if re.search(r"Tweede\s+verblijf|résidence\s+secondaire", line.text, re.I):
            non_residential_monthly.extend(numbers_before_unit(line.text, UNIT_MONTH_RE))
    residential_monthly = unique_value(residential, "Energiefonds hoofdverblijf", prefix)
    non_residential_monthly_value = unique_value(
        non_residential_monthly, "Energiefonds tweede verblijf", prefix
    )
    return residential_monthly * 12, non_residential_monthly_value * 12

def parse_contributions(lines: list[PdfLine], file_label: str = "") -> ParsedContributions:
    prefix = f"[{file_label}] " if file_label else ""
    energiebijdrage = parse_energiebijdrage(lines, prefix)
    federal = parse_federal_tiers(lines, prefix)
    fund_residential, fund_non_residential = parse_energiefonds(lines, prefix)
    return ParsedContributions(
        energiebijdrage=energiebijdrage,
        federale_0_3000=federal[0],
        federale_3000_20000=federal[1],
        federale_20000_50000=federal[2],
        federale_50000_100000=federal[3],
        energiefonds_residentieel=fund_residential,
        energiefonds_niet_residentieel=fund_non_residential,
    )

def sort_key(row: dict[str, str]) -> tuple[int, int, int]:
    day, month, year = map(int, row["Van"].split("/"))
    return year, month, day

def main() -> None:
    if not TARIFF_DIR.is_dir():
        raise FileNotFoundError(f"Tariefmap bestaat niet: {TARIFF_DIR}")
    pdf_files = sorted(
        path
        for path in TARIFF_DIR.iterdir()
        if path.is_file()
        and path.name.upper().startswith(FILE_PREFIX)
        and path.suffix.lower() == ".pdf"
    )
    if not pdf_files:
        raise FileNotFoundError(f"Geen PDF-bestanden met prefix {FILE_PREFIX} in {TARIFF_DIR}")

    rows = []
    errors = []
    for path in pdf_files:
        try:
            text, lines = extract_pdf(path)
            period = find_period(path, text)
            if period is None:
                raise ValueError("Periode (Van/Tot) kon niet worden bepaald")
            values = parse_contributions(lines, path.name)
            rows.append(contributions_to_csv(values, *period))
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")

    if errors:
        details = "\n".join(errors)
        raise RuntimeError(
            f"{len(errors)} van {len(pdf_files)} PDF-bestanden konden niet worden verwerkt. "
            f"Er is geen gedeeltelijke CSV weggeschreven.\n{details}"
        )

    rows.sort(key=sort_key)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

if __name__ == "__main__":
    main()
