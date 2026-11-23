
from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Sequence
from PyPDF2 import PdfReader
from tqdm import tqdm

import csv
import re
import pdfplumber

from smartmeter.config import DATA_DIR

TARIFF_DIR = DATA_DIR / "tarrifs"
OUTPUT_FILE = DATA_DIR / "input" / "Energiekosten.csv"

COLUMNS = (
    "DateKey",
    "ContractName",
    "SingleMeterFixed",
    "DualMeterDayFixed",
    "DualMeterNightFixed",
    "ExclusiveNightMeterFixed",
    "SingleMeterVariableMeterFactor",
    "SingleMeterVariableBalancingCost",
    "DualMeterDayVariableMeterFactor",
    "DualMeterDayVariableBalancingCost",
    "DualMeterNightVariableMeterFactor",
    "DualMeterNightVariableBalancingCost",
    "ExclusiveNightMeterVariableMeterFactor",
    "ExclusiveNightMeterVariableBalancingCost",
    "DynamicMeterCost",
    "DynamicBalancingCost",
    "SingleMeterInjectionMeterFactor",
    "SingleMeterInjectionBalancingCost",
    "DualMeterDayInjectionMeterFactor",
    "DualMeterDayInjectionBalancingCost",
    "DualMeterNightInjectionMeterFactor",
    "DualMeterNightInjectionBalancingCost",
    "DynamicMeterInjectionMeterFactor",
    "DynamicMeterInjectionBalancingCost",
    "AdministrativeCosts",
    "GreenElectricity",
    "WKK",
)

INJECTION_PREFIXES = (
    "SingleMeterInjection",
    "DualMeterDayInjection",
    "DualMeterNightInjection",
)

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

NUMBER = r"[-+]?(?:\d{1,3}(?:[.\s]\d{3})+|\d+)(?:[,.]\d+)?"

BOLT_FORMULA_FRAGMENT_RE = re.compile(
    r"(?:Belpex|EPEX)(?:\s*[-–/(]?\s*(?:RLP|RLPM|SPP|BE)\)?)?\s*[*x×·]\s*(?P<factor>\d+(?:[.,]\d{1,4})?)"
    r"(?:\s*(?P<sign>[+\-−–])\s*(?P<balancing>\d+(?:[.,]\d+)?))?",
    re.IGNORECASE,
)
BOLT_FORMULA_ROWS = (
    ("SingleMeterVariable", r"Enkelvoudig"),
    ("DualMeterDayVariable", r"Dag"),
    ("DualMeterNightVariable", r"Nacht"),
    ("ExclusiveNightMeterVariable", r"Exclusiefnacht"),
    (None, r"Injectie\(mini-opwekkers\)"),
)
BOLT_GREEN_LABEL_RE = re.compile(
    r"(?:Kosten\s+)?groene?\s*certi.{1,2}caten"
    r"(?:\s*\(c€/kWh\))?\s*\*?\d*",
    re.IGNORECASE,
)
BOLT_WKK_LABEL_RE = re.compile(
    r"(?:Kosten\s+)?(?:WKK|WFF)"
    r"(?:\s*\(c€/kWh\))?\s*\*?\d*",
    re.IGNORECASE,
)
BOLT_VL_HEADER_RE = re.compile(
    r"^(?:VL|Vlaanderen)$",
    re.IGNORECASE,
)
BOLT_WAL_HEADER_RE = re.compile(
    r"^(?:WAL|Walloni[eë])$",
    re.IGNORECASE,
)
BOLT_DECIMAL_RE = re.compile(r"^\d+[,.]\d+$")
BOLT_TRAILING_COMMA_RE = re.compile(r"^\d+[,.]$")
BOLT_DIGITS_RE = re.compile(r"^\d+$")

DATS24_FORMULA_RE = re.compile(
    r"BE_spot(?P<index>RLP|SPP)\s*(?:\*|×|x|·)\s*(?P<factor>\d+(?:[.,]\d+)?)"
    r"\s*(?P<sign>[+\-−–])\s*(?P<balancing>\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)

ENECO_CONSUMPTION_RE = re.compile(
    r"\(?\s*(?P<factor>\d+(?:[.,]\d+)?)\s*[x×*·]\s*BELPEX[-_ ]?RLP(?:-M)?\s*(?P<sign>[+\-−–])\s*(?P<offset>\d+(?:[.,]\d+)?)\s*\)?(?:\s*[x×*·]\s*(?P<vat>\d+(?:[.,]\d+)?))?",
    re.IGNORECASE,
)
ENECO_INJECTION_RE = re.compile(
    r"(?P<factor>\d+(?:[.,]\d+)?)\s*[x×*·]\s*BELPEX(?:-\d+)?"
    r"(?:\s*(?P<sign>[+\-−–])\s*(?P<balancing>\d+(?:[.,]\d+)?))?",
    re.IGNORECASE,
)
ENECO_VAT_TOKEN_RE = re.compile(r"[x×*·]\s*(?P<vat>\d+(?:[.,]\d+)?)", re.IGNORECASE)
ENECO_FIXED_AMOUNT_RE = re.compile(r"(?<!\d)(?P<whole>\d+)[.,](?P<cents>\d{2})(?=\d|\s|€|$)")
ENECO_DECIMAL_RE = re.compile(r"(?<!\d)\d+(?:[.,]\d{1,4})(?!\d)")
ENECO_VL_GREEN_RE = re.compile(
    r"Bijdrage\s+groene\s+stroom(?:\s+en\s+WKK)?\s+Vlaanderen"
    r"(?:\s*\(?€?\s*cent\s*/\s*kWh\)?)?"
    r"[^0-9A-Za-z,\n]{0,8}"
    r"(?P<val>\d+[.,]\d{1,4})",
    re.IGNORECASE,
)

OCTAPLUS_CONSUMPTION_RE = re.compile(
    r"(?P<label>Enkelvoudige\s+meter|Tweevoudige\s+meter\s*[–-]\s*Piek|"
    r"Tweevoudige\s+meter\s*[–-]\s*Dal|Exclusief\s+Nachtmeter)\s*:\s*"
    r"Belpex\s*(?:RLP|M|SPP)?\s*\*\s*(?P<factor>\d+(?:[.,]\d+)?)\s*"
    r"(?P<sign>[+\-−–])\s*(?P<balancing>\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
OCTAPLUS_INJECTION_RE = re.compile(
    r"(?P<label>enkelvoudig|tweevoudig/piekuren|tweevoudig/daluren)\s*:\s*"
    r"Belpex(?:\s+(?:RLP|M|SPP))?\s*\*\s*(?P<factor>\d+(?:[.,]\d+)?)\s*"
    r"(?P<sign>[+\-−–])\s*(?P<balancing>\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
OCTAPLUS_ADMIN_RE = re.compile(
    r"(?:Vaste\s+vergoeding(?:\s*\(€/jaar\))?\s*(?:Gratis\s*)?(?P<val1>\d+[.,]\d{2})|"
    r"(?:Gratis\s*)?(?P<val2>\d+[.,]\d{2})\s*Vaste\s+vergoeding(?:\s*\(€/jaar\))?)",
    re.IGNORECASE,
)
OCTAPLUS_GREEN_RE = re.compile(
    r"Kosten\s+groene\s+stroom\s+(?:\d+[.,]\d+\s+)?(?P<green>\d+[.,]\d+)",
    re.IGNORECASE,
)
OCTAPLUS_WKK_RE = re.compile(
    r"Kosten\s+WKK\s*(?P<sign>[+\-−–])?\s*(?P<wkk>\d+[.,]\d+)",
    re.IGNORECASE,
)

OCTAPLUS_FIXED = re.compile(
    r"""
    (?:
        (?:Enkelvoudige\s*meter|Compteur\s*monohoraire)
        (?:\s+-?\d+,\d{{2}})?\s+(-?\d+,\d{2})
    )
    |
    (?:
        (?:Piekuren|Heures\s*pleines)
        (?:\s+-?\d+,\d{{2}})?\s+(-?\d+,\d{2})
        |
        (-?\d+,\d{2})(?=\s*(?:Piekuren|Heures\s*pleines)\b)
    )
    |
    (?:
        (?:Daluren|Heures\s*creuses)\s+(-?\d+,\d{2})
        |
        (-?\d+,\d{2})(?=\s*(?:Daluren|Heures\s*creuses)\b)
    )
    |
    (?:
        (?:Uitsluitend\s*nachtmeter|Compteur\s*exclusif\s*nuit)\s+(-?\d+,\d{2})
        |
        (-?\d+,\d{2})(?=\s*(?:Uitsluitend\s*nachtmeter|Compteur\s*exclusif\s*nuit)\b)
    )
    """,
    re.IGNORECASE | re.DOTALL | re.VERBOSE,
)
OCTAPLUS_FIXED_NUMBER_RE = re.compile(r"(?<!\d)-?\d+[.,]\d+(?!\d)")
OCTAPLUS_FIXED_DECIMAL_RE = re.compile(r"^-?\d{1,2},\d{2}$")
OCTAPLUS_FIXED_ADMIN_RE = re.compile(
    r"(?:"
    r"Redevance\s+fixe(?:\s*\([^)]*\))?\s*(?:Gratuit\s*)?(?P<val1>\d+[.,]\d{2})"
    r"|"
    r"(?P<val2>\d+[.,]\d{2})\s*(?:Gratuit\s*)?Redevance\s+fixe(?:\s*\([^)]*\))?"
    r"|"
    r"Vaste\s+vergoeding(?:\s*\([^)]*\))?\s*(?:Gratis\s*)?(?P<val3>\d+[.,]\d{2})"
    r"|"
    r"(?P<val4>\d+[.,]\d{2})\s*(?:Gratis\s*)?Vaste\s+vergoeding(?:\s*\([^)]*\))?"
    r")",
    re.IGNORECASE,
)
OCTAPLUS_FIXED_GREEN_RE = re.compile(
    r"(?:"
    r"Kosten\s+groene\s+stroom"
    r"|"
    r"Co[uû]ts?\s+(?:(?:de\s+)?(?:l['’]\s*)?)?[eé]nergie\s+verte"
    r")"
    r"\s+(?:\d+[.,]\d+\s+)?(?P<green>\d+[.,]\d+)",
    re.IGNORECASE,
)
OCTAPLUS_FIXED_WKK_RE = re.compile(
    r"(?:"
    r"Kosten\s+WKK"
    r"|"
    r"Co[uû]ts?\s+(?:de\s+)?(?:cog[eé]n[eé]ration|WKK)"
    r")"
    r"\s*(?P<sign>[+\-−–])?\s*(?P<wkk>\d+[.,]\d+)",
    re.IGNORECASE,
)

@dataclass
class TariffRow:
    date_key: str
    contract_name: str
    values: dict[str, Decimal] = field(default_factory=dict)

    def set(self, column: str, value: Decimal | str | int) -> None:
        if column not in COLUMNS[2:]:
            raise ValueError(f"Unknown or non-numeric tariff column: {column}")
        number = to_decimal(str(value))
        if not number.is_finite():
            raise ValueError(f"Non-finite value for {column}: {value!r}")
        self.values[column] = number

    def to_csv_dict(self) -> dict[str, str]:
        result = {column: "" for column in COLUMNS}
        result["DateKey"] = self.date_key
        result["ContractName"] = self.contract_name
        result.update({column: decimal_to_string(value) for column, value in self.values.items()})
        return result

@dataclass
class PdfFragment:
    page_number: int
    x: float
    y: float
    text: str
    font_size: float = 0.0
    order: int = 0

@dataclass
class PdfLine:
    page_number: int
    y: float
    text: str
    fragments: tuple[PdfFragment, ...]

    @property
    def x_min(self) -> float:
        return min((fragment.x for fragment in self.fragments), default=0.0)

    @property
    def x_max(self) -> float:
        return max((fragment.x for fragment in self.fragments), default=0.0)

@dataclass
class PlumberWord:
    page_number: int
    x0: float
    x1: float
    top: float
    bottom: float
    text: str

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2.0

def to_decimal(raw_value: str) -> Decimal:
    value = raw_value.strip().replace("\xa0", "").replace(" ", "")
    if not value:
        raise ValueError("Empty numeric value")

    if "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    elif "," in value:
        value = value.replace(",", ".")

    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"Invalid numeric value: {raw_value!r}") from error

    if not result.is_finite():
        raise ValueError(f"Invalid non-finite numeric value: {raw_value!r}")

    return result

def decimal_to_string(value: Decimal) -> str:
    return format(value.normalize(), "f")

def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()

def normalize_bolt_token(raw_value: str) -> str:
    return raw_value.strip().replace("\xa0", "").replace(" ", "")

def despace(text: str) -> str:
    return re.sub(r"\s+", "", text)

def matrix_point(current_matrix: Sequence[float], text_matrix: Sequence[float]) -> tuple[float, float]:
    x = float(text_matrix[4]) * float(current_matrix[0]) + float(text_matrix[5]) * float(current_matrix[2]) + float(current_matrix[4])
    y = float(text_matrix[4]) * float(current_matrix[1]) + float(text_matrix[5]) * float(current_matrix[3]) + float(current_matrix[5])

    return x, y

def cluster_fragments(fragments: list[PdfFragment], y_tolerance: float) -> list[list[PdfFragment]]:
    clusters = []
    for fragment in sorted(fragments, key=lambda fragment: (-fragment.y, fragment.x)):
        best_cluster = None
        best_distance = float("inf")
        for cluster in clusters[-4:]:
            baseline = sum(item.y for item in cluster) / len(cluster)
            maximum_font_size = max((item.font_size for item in cluster), default=0.0)
            tolerance = max(y_tolerance, min(fragment.font_size, maximum_font_size) * 0.22)
            distance = abs(baseline - fragment.y)
            if distance <= tolerance and distance < best_distance:
                best_cluster = cluster
                best_distance = distance

        if best_cluster is None:
            clusters.append([fragment])
        else:
            best_cluster.append(fragment)
    return clusters

def reconstruct_lines(reader: PdfReader, *, y_tolerance: float = 2.2) -> list[PdfLine]:
    output_lines = []
    for page_number, page in enumerate(reader.pages, start=1):
        fragments = []

        def extract_fragment(text: str, current_matrix: Sequence[float], text_matrix: Sequence[float], _font_dictionary: dict | None, font_size: float) -> None:
            cleaned_text = re.sub(r"[\r\n]+", " ", text).strip()
            if not cleaned_text:
                return

            try:
                x, y = matrix_point(current_matrix, text_matrix)
            except (IndexError, TypeError, ValueError):
                return

            fragments.append(PdfFragment(
                page_number=page_number,
                x=x,
                y=y,
                text=cleaned_text,
                font_size=float(font_size or 0.0),
                order=len(fragments),
            ))

        try:
            page.extract_text(visitor_text=extract_fragment)
        except TypeError as error:
            raise RuntimeError("PyPDF2 visitor_text API is unavailable; install PyPDF2 3.0.1.") from error
        except Exception as error:
            raise RuntimeError(f"Text extraction failed on page {page_number}: {error}") from error

        for cluster in cluster_fragments(fragments, y_tolerance):
            ordered_fragments = sorted(cluster, key=lambda fragment: fragment.order)
            horizontal_fragments = sorted(cluster, key=lambda fragment: fragment.x)

            pieces = []
            previous_fragment = None
            for fragment in ordered_fragments:
                if previous_fragment is None:
                    pieces.append(fragment.text)
                else:
                    estimated_width = max(0.0, len(previous_fragment.text) * max(previous_fragment.font_size, 1.0) * 0.48)
                    horizontal_gap = fragment.x - (previous_fragment.x + estimated_width)
                    gap_threshold = max(1.0, min(previous_fragment.font_size, fragment.font_size or previous_fragment.font_size) * 0.42)

                    separator = "" if horizontal_gap <= gap_threshold else " "
                    pieces.append(separator + fragment.text)
                previous_fragment = fragment

            line_text = normalize_text("".join(pieces))
            output_lines.append(PdfLine(
                page_number=page_number,
                y=sum(fragment.y for fragment in horizontal_fragments) / len(horizontal_fragments),
                text=line_text,
                fragments=tuple(ordered_fragments),
            ))

    return sorted(output_lines, key=lambda line: (line.page_number, -line.y, line.x_min))

def extract_pdf(path: Path) -> tuple[str, list[PdfLine]]:
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        try:
            if reader.decrypt("") == 0:
                raise ValueError("PDF is encrypted and cannot be opened with an empty password")
        except Exception as error:
            raise ValueError(f"Cannot read encrypted PDF {path.name}: {error}") from error

    lines = reconstruct_lines(reader)
    if not lines:
        raise ValueError(f"No selectable text found in {path.name}; OCR is not implemented")

    extracted_text = "\n".join(line.text for line in lines)
    return extracted_text, lines

def get_page_lines(lines: Sequence[PdfLine], page_number: int) -> list[PdfLine]:
    return [line for line in lines if line.page_number == page_number]

def identify_product(path: Path) -> str | None:
    file_name = path.stem.lower().replace("_", "-").replace(" ", "-")
    products = {
        "dats24": "DATS24 Elektriciteit",
        "eneco": "Eneco Zon & Wind Flex",
        "octaplus-eco-clear": "Octa+ Eco Clear",
        "octaplus-fixed": "Octa+ Fixed",
        "bolt": "Bolt Elektriciteit",
    }
    return next((contract_name for identifier, contract_name in products.items() if identifier in file_name), None)

def find_date_key(path: Path, text: str) -> str:
    file_name = path.stem.lower()
    date_match = re.search(r"(?<!\d)(20\d{2})[-_. ]?(0[1-9]|1[0-2])(?!\d)", file_name,)
    if date_match:
        return f"{date_match.group(1)}{date_match.group(2)}01"

    for month_name, month_number in MONTHS.items():
        month_match = re.search(rf"\b{month_name}[-_ ]+(20\d{{2}})\b", file_name)
        if month_match:
            return f"{month_match.group(1)}{month_number:02d}01"

    for month_name, month_number in MONTHS.items():
        month_match = re.search(rf"\b{month_name}\s+(20\d{{2}})\b", text, re.IGNORECASE)
        if month_match:
            return f"{month_match.group(1)}{month_number:02d}01"
    raise ValueError(f"Could not determine tariff month for {path.name}")


def extract_plumber_page_words(pdf_path: Path, page_number: int) -> list[PlumberWord]:
    with pdfplumber.open(str(pdf_path)) as pdf:
        if page_number < 1 or page_number > len(pdf.pages):
            raise ValueError(f"Bolt: pagina {page_number} bestaat niet in {pdf_path.name}")
        page = pdf.pages[page_number - 1]
        raw_words = page.extract_words(
            keep_blank_chars=False,
            use_text_flow=False,
            extra_attrs=["size"],
        )

    words = []
    for word_data in raw_words:
        word_text = str(word_data.get("text", "")).strip()
        if not word_text:
            continue
        words.append(PlumberWord(
            page_number=page_number,
            x0=float(word_data["x0"]),
            x1=float(word_data["x1"]),
            top=float(word_data["top"]),
            bottom=float(word_data["bottom"]),
            text=word_text,
        ))
    return words

def find_label_y(words: Sequence[PlumberWord], label_regex: re.Pattern[str], label_name: str, *, near_y: float | None = None, max_y_delta: float = 30.0) -> tuple[float, float]:
    sorted_words = sorted(words, key=lambda word: (word.top, word.x0))
    line_buckets = []
    for word in sorted_words:
        placed = False
        for bucket in line_buckets:
            average_top = sum(item.top for item in bucket) / len(bucket)
            if abs(word.top - average_top) <= 5.5:
                bucket.append(word)
                placed = True
                break
        if not placed:
            line_buckets.append([word])

    matches = []
    for bucket in line_buckets:
        sorted_bucket = sorted(bucket, key=lambda word: word.x0)
        joined_text = "".join(word.text for word in sorted_bucket)
        if (label_regex.search(joined_text) or label_regex.search(despace(joined_text))):
            label_words = [word for word in sorted_bucket if not re.fullmatch(
                r"[\d,.\-+*€/%]+",
                normalize_bolt_token(word.text),
            )] or sorted_bucket
            average_y = sum(word.center_y for word in label_words) / len(label_words)
            maximum_x1 = max(word.x1 for word in label_words)
            matches.append((average_y, maximum_x1, joined_text))
    if not matches:
        raise ValueError(f"Bolt: label {label_name!r} niet gevonden via pdfplumber")

    if len(matches) > 1:
        concise_matches = [match for match in matches if len(match[2]) <= 80]
        if concise_matches:
            matches = concise_matches

        if near_y is not None and len(matches) > 1:
            nearby_matches = [match for match in matches if abs(match[0] - near_y) <= max_y_delta]
            if nearby_matches:
                matches = nearby_matches

        if len(matches) > 1:
            matches.sort(key=lambda match: (
                abs(match[0] - near_y)
                if near_y is not None
                else match[0],
                len(match[2]),
            ))

    return matches[0][0], matches[0][1]

def find_vl_column_bounds(words: Sequence[PlumberWord], *, green_y: float, fallback_x_min: float) -> tuple[float, float | None]:
    vl_headers = [word for word in words if (
        BOLT_VL_HEADER_RE.match(despace(word.text))
        and -110.0 <= (word.center_y - green_y) <= 25.0
        and word.x0 >= fallback_x_min - 30.0
    )]
    if not vl_headers:
        return fallback_x_min, None

    vl_header = min(vl_headers, key=lambda word: (abs(word.center_y - green_y), word.x0))
    x_min = vl_header.x0 - 20.0
    wal_headers = [word for word in words if (
        BOLT_WAL_HEADER_RE.match(despace(word.text))
        and word.x0 > vl_header.x1 + 5.0
        and abs(word.center_y - vl_header.center_y) <= 10.0
    )]
    x_max = None
    if wal_headers:
        candidate_x_max = min(word.x0 for word in wal_headers) - 6.0
        if candidate_x_max > x_min + 10.0:
            x_max = candidate_x_max

    return x_min, x_max

def parse_bolt_cell_decimal(cell_words: Sequence[PlumberWord], target_y: float, label_name: str) -> Decimal:
    if not cell_words:
        raise ValueError(f"Bolt: geen woorden in Vlaamse cel voor {label_name} rond y={target_y:.1f}")

    decimals = []
    for word in cell_words:
        token = normalize_bolt_token(word.text)
        if BOLT_DECIMAL_RE.match(token):
            decimals.append((abs(word.center_y - target_y), word.x0, to_decimal(token)))
    if decimals:
        decimals.sort(key=lambda decimal: (decimal[0], decimal[1]))
        chosen_value = decimals[0][2]
        return chosen_value

    ordered_words = sorted(cell_words, key=lambda word: (abs(word.center_y - target_y), word.x0))
    for first_index, first_word in enumerate(ordered_words):
        first_token = normalize_bolt_token(first_word.text)
        if not BOLT_TRAILING_COMMA_RE.match(first_token):
            continue

        for second_word in ordered_words[first_index + 1:]:
            second_token = normalize_bolt_token(second_word.text)
            if not BOLT_DIGITS_RE.match(second_token):
                continue

            if (abs(second_word.x0 - first_word.x0) > 40.0 or abs(second_word.center_y - first_word.center_y) > 20.0):
                continue

            combined_token = f"{first_token}{second_token}"
            if BOLT_DECIMAL_RE.match(combined_token):
                extracted_value = to_decimal(combined_token)
                return extracted_value

    raise ValueError(f"Bolt: kon geen geldig decimaal bedrag bepalen voor {label_name} rond y={target_y:.1f}; woorden={[word.text for word in cell_words]!r}")

def extract_bolt_formulas(lines: Sequence[PdfLine]) -> tuple[dict[str, tuple[Decimal, Decimal]], tuple[Decimal, Decimal]]:
    consumption_candidates: list[PdfFragment] = []
    injection_candidates: list[PdfFragment] = []
    pages_with_formulas: set[int] = set()

    for line in lines:
        compact_line = despace(line.text)
        line_matches = list(BOLT_FORMULA_FRAGMENT_RE.finditer(compact_line))
        if not line_matches or len(line_matches) > 6 or compact_line.count(".") > 2:
            continue

        pages_with_formulas.add(line.page_number)
        x_positions = [fragment.x for fragment in sorted(line.fragments, key=lambda item: item.x)]
        min_x = x_positions[0] if x_positions else 0.0
        max_x = x_positions[-1] if x_positions else 0.0
        is_injection_line = "inject" in compact_line.lower()

        created_for_line: list[PdfFragment] = []
        for idx, match in enumerate(line_matches):
            frag_x = (
                min_x + (idx / max(len(line_matches) - 1, 1)) * (max_x - min_x)
                if len(line_matches) > 1 else min_x
            )
            created_for_line.append(PdfFragment(
                page_number=line.page_number,
                x=frag_x,
                y=line.y,
                text=match.group(0),
                font_size=line.fragments[0].font_size if line.fragments else 0.0,
                order=line.fragments[0].order + idx if line.fragments else idx,
            ))

        if is_injection_line and len(created_for_line) > 1:
            consumption_candidates.extend(created_for_line[:-1])
            injection_candidates.append(created_for_line[-1])
        elif is_injection_line:
            injection_candidates.append(created_for_line[0])
        else:
            consumption_candidates.extend(created_for_line)

    if len(pages_with_formulas) != 1:
        raise ValueError(f"Bolt: formulafragmenten gevonden op pagina's {sorted(pages_with_formulas)}; verwacht precies één pagina")

    page_number = next(iter(pages_with_formulas))
    consumption_candidates.sort(key=lambda fragment: (-fragment.y, fragment.x))
    injection_candidates.sort(key=lambda fragment: (-fragment.y, fragment.x))

    if not consumption_candidates or not injection_candidates:
        raise ValueError(
            f"Bolt: onvoldoende formules op pagina {page_number}: "
            f"verbruik={[f.text for f in consumption_candidates]!r}, injectie={[f.text for f in injection_candidates]!r}"
        )

    consumption_prefixes = [prefix for prefix, _ in BOLT_FORMULA_ROWS if prefix is not None]
    parsed_consumption: list[tuple[Decimal, Decimal]] = []
    for formula_fragment in consumption_candidates:
        formula_match = BOLT_FORMULA_FRAGMENT_RE.search(despace(formula_fragment.text))
        if formula_match is None:
            raise ValueError(f"Bolt: ongeldige verbruiksformule {formula_fragment.text!r}")
        factor = to_decimal(formula_match.group("factor"))
        sign = formula_match.group("sign")
        balancing = Decimal("0") if sign is None else to_decimal(formula_match.group("balancing"))
        if sign in {"-", "−", "–"}:
            balancing = -balancing
        parsed_consumption.append((factor, balancing))

    consumption_formulas: dict[str, tuple[Decimal, Decimal]] = {}
    for index, prefix in enumerate(consumption_prefixes):
        consumption_formulas[prefix] = parsed_consumption[min(index, len(parsed_consumption) - 1)]

    injection_match = BOLT_FORMULA_FRAGMENT_RE.search(despace(injection_candidates[-1].text))
    if injection_match is None:
        raise ValueError(f"Bolt: ongeldige injectieformule {injection_candidates[-1].text!r}")
    inj_factor = to_decimal(injection_match.group("factor"))
    inj_sign = injection_match.group("sign")
    inj_balancing = Decimal("0") if inj_sign is None else to_decimal(injection_match.group("balancing"))
    if inj_sign in {"-", "−", "–"}:
        inj_balancing = -inj_balancing

    return consumption_formulas, (inj_factor, inj_balancing)

def extract_bolt_green_and_wkk_plumber(pdf_path: Path, lines: Sequence[PdfLine]) -> tuple[Decimal, Decimal]:
    green_lines = [line for line in lines if (
        len(line.text) <= 120
        and BOLT_GREEN_LABEL_RE.search(despace(line.text))
    )]
    if len(green_lines) != 1:
        raise ValueError(f"Bolt: verwacht één groene-certificatenlabel, gevonden {len(green_lines)}")

    page_number = green_lines[0].page_number
    words = extract_plumber_page_words(pdf_path, page_number)
    green_y, green_x1 = find_label_y(words, BOLT_GREEN_LABEL_RE, "GreenElectricity")
    fallback_wkk_y = green_y + 14.0
    try:
        wkk_y, wkk_x1 = find_label_y(words, BOLT_WKK_LABEL_RE, "WKK", near_y=fallback_wkk_y, max_y_delta=25.0)
    except ValueError:
        wkk_y = fallback_wkk_y
        wkk_x1 = green_x1

    fallback_x_min = max(green_x1, wkk_x1)
    x_min, x_max = find_vl_column_bounds(words, green_y=green_y, fallback_x_min=fallback_x_min)
    y_min = min(green_y, wkk_y) - 12.0
    y_max = max(green_y, wkk_y) + 12.0

    vl_words = [word for word in words if (
        word.x0 >= x_min
        and (x_max is None or word.x0 <= x_max)
        and y_min <= word.center_y <= y_max
    )]
    green_cell = [word for word in vl_words if abs(word.center_y - green_y) <= 8.0]
    wkk_cell = [word for word in vl_words if abs(word.center_y - wkk_y) <= 8.0]

    green_value = parse_bolt_cell_decimal(green_cell, green_y, "GreenElectricity")
    wkk_value = parse_bolt_cell_decimal(wkk_cell, wkk_y, "WKK")
    return green_value, wkk_value

def parse_bolt(row: TariffRow, lines: Sequence[PdfLine], pdf_path: Path) -> None:
    consumption_formulas, injection_formula = extract_bolt_formulas(lines)
    injection_factor, injection_balancing = injection_formula

    for prefix, (consumption_factor, balancing_cost) in consumption_formulas.items():
        row.set(f"{prefix}MeterFactor", consumption_factor)
        row.set(f"{prefix}BalancingCost", balancing_cost)

    for prefix in INJECTION_PREFIXES:
        row.set(f"{prefix}MeterFactor", injection_factor)
        row.set(f"{prefix}BalancingCost", injection_balancing)

    green_electricity, wkk = extract_bolt_green_and_wkk_plumber(pdf_path, lines)
    row.set("GreenElectricity", green_electricity)
    row.set("WKK", wkk)


def parse_dats24_formula_fragment(raw_formula: str) -> tuple[str, Decimal, Decimal]:
    compact = despace(raw_formula)
    match = DATS24_FORMULA_RE.search(compact)
    if match is None:
        raise ValueError(f"DATS24: could not parse formula from {raw_formula!r}")

    index_name = match.group("index").upper()
    factor = to_decimal(match.group("factor"))
    sign = match.group("sign")
    balancing = to_decimal(match.group("balancing"))
    if sign in {"-", "−", "–"}:
        balancing = -balancing

    return index_name, factor, balancing

def extract_dats24_admin_cost(lines: Sequence[PdfLine]) -> Decimal | None:
    for line in lines:
        if line.page_number != 1:
            continue
        compact = despace(line.text).lower()
        if "vastevergoeding" in compact or "redevancefixe" in compact:
            amounts = re.findall(r"\d+[.,]\d+", line.text)
            if amounts:
                return to_decimal(amounts[0])

    raise ValueError("DATS24: vaste vergoeding not found on page 1")

def extract_dats24_cert_value(lines: Sequence[PdfLine], cert_name: str) -> Decimal:
    target = cert_name.upper()
    for index, line in enumerate(lines):
        if line.page_number != 1:
            continue
        compact = despace(line.text).upper()
        has_cert = target in compact or (target == "GSC" and "∃SC" in compact)
        if not has_cert:
            continue

        amounts = re.findall(r"\d+[.,]\d+", line.text)
        if amounts:
            return to_decimal(amounts[0])

        if index + 1 < len(lines):
            next_amounts = re.findall(r"\d+[.,]\d+", lines[index + 1].text)
            if next_amounts:
                return to_decimal(next_amounts[0])

    raise ValueError(f"DATS24: {cert_name} value not found on page 1")

def extract_dats24_formulas(lines: Sequence[PdfLine]) -> dict[str, tuple[Decimal, Decimal]]:
    page2_lines = [line for line in lines if line.page_number == 2]
    formulas_by_row: dict[str, tuple[Decimal, Decimal]] = {}

    row_markers = (
        ("single", ("enkelvoudigemeter", "compteursimple")),
        ("day", ("dag", "heurespleines")),
        ("night", ("nacht", "heurescreuses")),
        ("excl_night", ("uitsluitendnachtmeter", "excl.nuit", "exclnuit")),
        ("injection", ("teruglevering", "restitution")),
    )

    for line in page2_lines:
        compact = despace(line.text).lower()
        if DATS24_FORMULA_RE.search(despace(line.text)) is None:
            continue
        for key, markers in row_markers:
            if key in formulas_by_row:
                continue
            if any(marker in compact for marker in markers):
                _, factor, balancing = parse_dats24_formula_fragment(line.text)
                formulas_by_row[key] = (factor, balancing)

    for idx, line in enumerate(page2_lines):
        compact = despace(line.text).lower()
        if DATS24_FORMULA_RE.search(despace(line.text)) is None:
            continue
        for match in DATS24_FORMULA_RE.finditer(despace(line.text)):
            index_name = match.group("index").upper()
            factor = to_decimal(match.group("factor"))
            sign = match.group("sign")
            balancing = to_decimal(match.group("balancing"))
            if sign in {"-", "−", "–"}:
                balancing = -balancing

            if index_name == "SPP" and "injection" not in formulas_by_row:
                formulas_by_row["injection"] = (factor, balancing)
            elif index_name == "RLP":
                prev_compact = despace(page2_lines[idx - 1].text).lower() if idx > 0 else ""
                combined_context = f"{prev_compact} {compact}"
                if "enkelvoudig" in combined_context or "compteursimple" in combined_context:
                    formulas_by_row.setdefault("single", (factor, balancing))
                elif "dag" in combined_context or "heurespleines" in combined_context:
                    formulas_by_row.setdefault("day", (factor, balancing))
                elif "uitsluitendnacht" in combined_context or "excl.nuit" in combined_context or "exclnuit" in combined_context:
                    formulas_by_row.setdefault("excl_night", (factor, balancing))
                elif "nacht" in combined_context or "heurescreuses" in combined_context:
                    formulas_by_row.setdefault("night", (factor, balancing))

    required = ("single", "day", "night", "excl_night", "injection")
    missing = [name for name in required if name not in formulas_by_row]
    if missing:
        raise ValueError(f"DATS24: missing parsed formulas for {missing}; found={list(formulas_by_row)}")

    return formulas_by_row

def parse_dats24(row: TariffRow, lines: Sequence[PdfLine]) -> None:
    formulas = extract_dats24_formulas(lines)

    meter_mapping = {
        "single": "SingleMeterVariable",
        "day": "DualMeterDayVariable",
        "night": "DualMeterNightVariable",
        "excl_night": "ExclusiveNightMeterVariable",
    }
    for key, prefix in meter_mapping.items():
        factor, balancing = formulas[key]
        row.set(f"{prefix}MeterFactor", factor)
        row.set(f"{prefix}BalancingCost", balancing)

    inj_factor, inj_balancing = formulas["injection"]
    for prefix in INJECTION_PREFIXES:
        row.set(f"{prefix}MeterFactor", inj_factor)
        row.set(f"{prefix}BalancingCost", inj_balancing)

    admin_cost = extract_dats24_admin_cost(lines)
    row.set("AdministrativeCosts", admin_cost)
    row.set("GreenElectricity", extract_dats24_cert_value(lines, "GSC"))
    row.set("WKK", extract_dats24_cert_value(lines, "WKC"))


def extract_eneco_admin_cost(lines: Sequence[PdfLine]) -> Decimal:
    top_lines = [
        line for line in lines
        if line.page_number == 1 and line.y >= 570.0
    ]
    for line in top_lines:
        for match in ENECO_FIXED_AMOUNT_RE.finditer(line.text):
            amount = to_decimal(f"{match.group('whole')}.{match.group('cents')}")
            if Decimal("20") <= amount <= Decimal("500"):
                return amount

    for line in top_lines:
        if "vaste vergoeding" in line.text.lower() or "€/jaar" in line.text.lower():
            for match in ENECO_DECIMAL_RE.finditer(line.text):
                amount = to_decimal(match.group(0))
                if Decimal("20") <= amount <= Decimal("500"):
                    return amount

    raise ValueError("Eneco: vaste vergoeding niet gevonden")

def extract_eneco_consumption_formula(lines: Sequence[PdfLine]) -> tuple[Decimal, Decimal]:
    energy_lines = [
        line for line in lines
        if line.page_number == 1 and line.y >= 570.0
    ]
    candidates = energy_lines or list(lines)

    for index, line in enumerate(candidates):
        match = ENECO_CONSUMPTION_RE.search(line.text)
        if not match:
            continue

        factor = to_decimal(match.group("factor"))
        offset = to_decimal(match.group("offset"))
        if match.group("sign") in {"-", "−", "–"}:
            offset = -offset

        vat = to_decimal(match.group("vat")) if match.group("vat") else None
        if vat is None:
            for follow in candidates[index + 1 : min(len(candidates), index + 4)]:
                if abs(follow.y - line.y) <= 20.0:
                    vat_match = ENECO_VAT_TOKEN_RE.search(follow.text)
                    if vat_match:
                        vat = to_decimal(vat_match.group("vat"))
                        break

        if vat is None:
            vat = Decimal("1")
        return factor * vat, offset * vat

    raise ValueError("Eneco: verbruiksformule niet gevonden")

def extract_eneco_injection_formula(lines: Sequence[PdfLine]) -> tuple[Decimal, Decimal]:
    page_lines = [line for line in lines if line.page_number == 2]
    candidates = [line for line in page_lines if "belpex" in line.text.lower()] or [
        line for line in lines if "belpex" in line.text.lower()
    ]

    for index, line in enumerate(candidates):
        match = ENECO_INJECTION_RE.search(line.text)
        if not match:
            continue

        factor = to_decimal(match.group("factor"))
        sign = match.group("sign")
        raw_balancing = match.group("balancing")

        if raw_balancing is None and index + 1 < len(candidates):
            follow_match = re.search(
                r"^\s*(?P<sign>[+\-−–])\s*(?P<balancing>\d+(?:[.,]\d+)?)",
                candidates[index + 1].text,
            )
            if follow_match:
                sign = follow_match.group("sign")
                raw_balancing = follow_match.group("balancing")

        if raw_balancing is None:
            balancing = Decimal("0")
        else:
            balancing = to_decimal(raw_balancing)
            if sign in {"-", "−", "–"}:
                balancing = -balancing

        return factor, balancing
    raise ValueError("Eneco: injectieformule niet gevonden")

def extract_vlaanderen_decimal(text: str) -> str | None:
    after_vl = re.search(
        r"Vlaanderen(?:\s*\(?€?\s*cent\s*/\s*kWh\)?)?[^0-9A-Za-z,\n]{0,8}(?P<val>\d+[.,]\d{1,4})",
        text,
        re.IGNORECASE,
    )
    if after_vl:
        return after_vl.group("val")

    before_vl = re.search(
        r"(?P<val>\d+[.,]\d{1,4})\s*\)?\s*Bijdrage\s+groene\s+stroom(?:\s+en\s+WKK)?\s+Vlaanderen",
        text,
        re.IGNORECASE,
    )
    if before_vl:
        return before_vl.group("val")

    label_val = re.search(
        r"Bijdrage\s+groene\s+stroom(?:\s+en\s+WKK)?\s+Vlaanderen(?:(?!Bijdrage\s+groene\s+stroom|FLUVIUS|Walloni[eë]|Brussel).){0,350}?\(\s*€?\s*cent\s*/\s*kWh\s*\)\s*(?P<val>\d+[.,]\d{1,4})",
        text,
        re.IGNORECASE,
    )
    if label_val:
        return label_val.group("val")

    return None

def extract_eneco_2024_green_fallback(lines: Sequence[PdfLine]) -> Decimal | None:
    vl_lines = [
        line
        for line in lines
        if line.page_number == 1
        and "vlaanderen" in line.text.lower()
        and ("groene" in line.text.lower() or "wkk" in line.text.lower())
    ]
    for vl_line in vl_lines:
        nearby_below = [
            candidate
            for candidate in lines
            if candidate.page_number == 1
            and (vl_line.y - 12.0) <= candidate.y <= (vl_line.y + 2.0)
        ]
        nearby_below.sort(key=lambda candidate: abs(candidate.y - vl_line.y))
        for candidate in nearby_below:
            cleaned = re.sub(r"FLUVIUS\b.*$", " ", candidate.text, flags=re.IGNORECASE)
            match = re.search(
                r"(?:cent\s*/\s*kWh\s*\)?\s*|^\s*\(?\s*)(?P<val>\d+[.,]\d{1,4})",
                cleaned,
                re.IGNORECASE,
            )
            if match:
                value = to_decimal(match.group("val"))
                if Decimal("0.1") <= value <= Decimal("50"):
                    return value
    return None

def extract_eneco_vl_green(lines: Sequence[PdfLine]) -> Decimal:
    for _, line in enumerate(lines):
        match = ENECO_VL_GREEN_RE.search(line.text)
        if match:
            value = to_decimal(match.group("val"))
            if Decimal("0.1") <= value <= Decimal("50"):
                return value

        compact = despace(line.text).lower()
        if "groenestroom" in compact or ("vlaanderen" in compact and "wkk" in compact):
            nearby = [
                candidate
                for candidate in lines
                if candidate.page_number == line.page_number
                and abs(candidate.y - line.y) <= 25.0
            ]
            combined_text = " ".join(candidate.text for candidate in nearby)

            candidate_raw = extract_vlaanderen_decimal(combined_text)
            source_tag = "vlaanderen_window"

            if candidate_raw is None:
                vl_lines = [
                    candidate
                    for candidate in lines
                    if candidate.page_number == line.page_number
                    and "vlaanderen" in candidate.text.lower()
                    and "groene stroom" in candidate.text.lower()
                ]
                for vl_line in vl_lines:
                    vl_window = " ".join(
                        candidate.text
                        for candidate in lines
                        if candidate.page_number == vl_line.page_number
                        and abs(candidate.y - vl_line.y) <= 12.0
                    )
                    vl_match = re.search(
                        r"Vlaanderen[^0-9A-Za-z,\n]{0,25}(?P<val>\d+[.,]\d{1,4})",
                        vl_window,
                        re.IGNORECASE,
                    )
                    if vl_match:
                        candidate_raw = vl_match.group("val")
                        source_tag = "vlaanderen_line_fallback"
                        break

            if candidate_raw is not None:
                value = to_decimal(candidate_raw)
                if Decimal("0.1") <= value <= Decimal("50"):
                    return value

    value = extract_eneco_2024_green_fallback(lines)
    if value is not None:
        return value

    raise ValueError("Eneco: Vlaamse groene stroom/WKK niet gevonden")

def parse_eneco(row: TariffRow, lines: Sequence[PdfLine]) -> None:
    cons_factor, cons_balancing = extract_eneco_consumption_formula(lines)
    for prefix in (
        "SingleMeterVariable",
        "DualMeterDayVariable",
        "DualMeterNightVariable",
        "ExclusiveNightMeterVariable",
    ):
        row.set(f"{prefix}MeterFactor", cons_factor)
        row.set(f"{prefix}BalancingCost", cons_balancing)

    inj_factor, inj_balancing = extract_eneco_injection_formula(lines)
    for prefix in INJECTION_PREFIXES:
        row.set(f"{prefix}MeterFactor", inj_factor)
        row.set(f"{prefix}BalancingCost", inj_balancing)

    admin_costs = extract_eneco_admin_cost(lines)
    row.set("AdministrativeCosts", admin_costs)
    green_val = extract_eneco_vl_green(lines)
    row.set("GreenElectricity", green_val)


def extract_octaplus_visible_page_text(
    lines: Sequence[PdfLine],
    page_number: int,
    *,
    max_x: float | None = None,
    max_font_size: float | None = None,
) -> str:
    visible_pieces: list[str] = []
    matched_lines = 0

    for line in get_page_lines(lines, page_number):
        if line.y >= 1000.0:
            continue

        if max_x is None and max_font_size is None:
            visible_pieces.append(line.text)
            matched_lines += 1
            continue

        filtered_fragments = [
            fragment
            for fragment in line.fragments
            if (max_x is None or fragment.x < max_x)
            and (max_font_size is None or fragment.font_size <= max_font_size)
        ]
        if not filtered_fragments:
            continue

        ordered = sorted(filtered_fragments, key=lambda fragment: fragment.order)
        line_snippet = normalize_text(" ".join(fragment.text for fragment in ordered))
        if line_snippet:
            visible_pieces.append(line_snippet)
            matched_lines += 1

    return normalize_text(" ".join(visible_pieces))

def extract_octaplus_admin_cost(lines: Sequence[PdfLine]) -> Decimal:
    page1_text = extract_octaplus_visible_page_text(lines, 1)
    match = OCTAPLUS_ADMIN_RE.search(page1_text)
    if match is None:
        raise ValueError("Octa+ Eco Clear: vaste vergoeding niet gevonden op pagina 1")
    raw_value = match.group("val1") or match.group("val2")
    assert raw_value is not None
    value = to_decimal(raw_value)
    return value

def extract_octaplus_green_and_wkk(
    lines: Sequence[PdfLine],
) -> tuple[Decimal, Decimal]:
    page2_text = extract_octaplus_visible_page_text(
        lines, 2, max_x=360.0, max_font_size=8.0
    )
    green_match = OCTAPLUS_GREEN_RE.search(page2_text)
    wkk_match = OCTAPLUS_WKK_RE.search(page2_text)

    if green_match is None or wkk_match is None:
        raise ValueError(
            "Octa+ Eco Clear: groene stroom of WKK niet gevonden op pagina 2"
        )

    green_value = to_decimal(green_match.group("green"))
    wkk_value = to_decimal(wkk_match.group("wkk"))

    return green_value, wkk_value

def extract_octaplus_formulas(
    lines: Sequence[PdfLine],
) -> tuple[dict[str, tuple[Decimal, Decimal]], dict[str, tuple[Decimal, Decimal]]]:
    page2_text = extract_octaplus_visible_page_text(lines, 2, max_x=360.0, max_font_size=8.0)

    consumption_map = {
        "enkelvoudige": "SingleMeterVariable",
        "piek": "DualMeterDayVariable",
        "dal": "DualMeterNightVariable",
        "exclusief": "ExclusiveNightMeterVariable",
    }
    injection_map = {
        "enkelvoudig": "SingleMeterInjection",
        "piekuren": "DualMeterDayInjection",
        "daluren": "DualMeterNightInjection",
    }

    consumption_formulas: dict[str, tuple[Decimal, Decimal]] = {}
    for match in OCTAPLUS_CONSUMPTION_RE.finditer(page2_text):
        label_lower = match.group("label").lower()
        prefix = next((target for key, target in consumption_map.items() if key in label_lower), None)
        if prefix is None:
            continue
        factor = to_decimal(match.group("factor"))
        balancing = to_decimal(match.group("balancing"))
        if match.group("sign") in {"-", "−", "–"}:
            balancing = -balancing
        consumption_formulas[prefix] = (factor, balancing)

    injection_formulas: dict[str, tuple[Decimal, Decimal]] = {}
    for match in OCTAPLUS_INJECTION_RE.finditer(page2_text):
        label_lower = match.group("label").lower()
        prefix = next((target for key, target in injection_map.items() if key in label_lower), None)
        if prefix is None:
            continue
        factor = to_decimal(match.group("factor"))
        balancing = to_decimal(match.group("balancing"))
        if match.group("sign") in {"-", "−", "–"}:
            balancing = -balancing
        injection_formulas[prefix] = (factor, balancing)

    if len(consumption_formulas) != 4 or len(injection_formulas) != 3:
        raise ValueError(
            "Octa+ Eco Clear: onvolledige formules op pagina 2 "
            f"(verbruik={sorted(consumption_formulas)}, injectie={sorted(injection_formulas)})"
        )

    return consumption_formulas, injection_formulas

def parse_octaplus_eco_clear(row: TariffRow, lines: Sequence[PdfLine]) -> None:
    consumption_formulas, injection_formulas = extract_octaplus_formulas(lines)

    for prefix, (factor, balancing) in consumption_formulas.items():
        row.set(f"{prefix}MeterFactor", factor)
        row.set(f"{prefix}BalancingCost", balancing)

    for prefix, (factor, balancing) in injection_formulas.items():
        row.set(f"{prefix}MeterFactor", factor)
        row.set(f"{prefix}BalancingCost", balancing)

    admin_cost = extract_octaplus_admin_cost(lines)
    green_electricity, wkk = extract_octaplus_green_and_wkk(lines)

    row.set("AdministrativeCosts", admin_cost)
    row.set("GreenElectricity", green_electricity)
    row.set("WKK", wkk)


def extract_octaplus_fixed_formulas(
    lines: Sequence[PdfLine],
    pdf_path: Path | None = None,
) -> list[Decimal]:
    if pdf_path is None:
        raise ValueError("pdf_path is required for Octa+ Fixed extraction")

    words = extract_plumber_page_words(pdf_path, 1)
    if not words:
        raise ValueError(f"Octa+ Fixed: geen woorden gevonden op pagina 1 van {pdf_path.name}")

    row_specs = (
        ("single", re.compile(r"enkelvoudige\s*meter|compteur\s*monohoraire", re.IGNORECASE)),
        ("day", re.compile(r"piekuren|heures\s*pleines", re.IGNORECASE)),
        ("night", re.compile(r"daluren|heures\s*creuses", re.IGNORECASE)),
        ("excl_night", re.compile(r"uitsluitend\s*nachtmeter|compteur\s*exclusif\s*nuit", re.IGNORECASE)),
    )

    y_bands: list[tuple[float, list[PlumberWord]]] = []
    for word in sorted(words, key=lambda w: (w.center_y, w.x0)):
        for idx, (band_y, band_words) in enumerate(y_bands):
            if abs(word.center_y - band_y) <= 4.5:
                band_words.append(word)
                y_bands[idx] = (sum(item.center_y for item in band_words) / len(band_words), band_words)
                break
        else:
            y_bands.append((word.center_y, [word]))

    values_by_key: dict[str, Decimal] = {}
    for key, pattern in row_specs:
        target_y: float | None = None

        for band_y, band_words in y_bands:
            ordered_band = sorted(band_words, key=lambda item: item.x0)
            spaced_text = " ".join(w.text for w in ordered_band)
            compact_text = despace(spaced_text)
            if pattern.search(spaced_text) or pattern.search(compact_text):
                target_y = band_y
                break

        if target_y is None:
            continue

        row_words = sorted(
            (w for w in words if abs(w.center_y - target_y) <= 3.5),
            key=lambda w: w.x0,
        )
        row_text = normalize_bolt_token("".join(w.text for w in row_words))
        after_label = pattern.sub("", row_text, count=1)
        num_match = re.search(r"-?\d+,\d{2}", after_label)
        if num_match:
            values_by_key[key] = abs(to_decimal(num_match.group(0)))

    ordered_keys = ("single", "day", "night", "excl_night")
    if not all(k in values_by_key for k in ordered_keys):
        sample_rows = [
            f"y={band_y:.1f}: {despace(''.join(w.text for w in sorted(bw, key=lambda i: i.x0)))!r}"
            for band_y, bw in y_bands
            if 390.0 <= band_y <= 470.0
        ]
        raise ValueError(
            f"Octa+ Fixed: onvolledige waarden op pagina 1 van {pdf_path.name} "
            f"(gevonden={values_by_key}; regels_390_470={sample_rows})"
        )

    result = [values_by_key[k] for k in ordered_keys]
    return result

def extract_octaplus_fixed_admin_cost(lines: Sequence[PdfLine]) -> Decimal:
    page1_text = extract_octaplus_visible_page_text(lines, 1)
    match = OCTAPLUS_FIXED_ADMIN_RE.search(page1_text)
    if match is None:
        raise ValueError("Octa+ Fixed: vaste vergoeding niet gevonden op pagina 1")
    raw_value = next(
        (match.group(name) for name in ("val1", "val2", "val3", "val4") if match.group(name) is not None),
        None,
    )
    assert raw_value is not None
    value = to_decimal(raw_value)
    return value

def extract_octaplus_fixed_green_and_wkk(
    lines: Sequence[PdfLine],
) -> tuple[Decimal, Decimal]:
    page2_text = extract_octaplus_visible_page_text(
        lines, 2, max_x=600.0, max_font_size=10.0
    )
    green_match = OCTAPLUS_FIXED_GREEN_RE.search(page2_text)
    wkk_match = OCTAPLUS_FIXED_WKK_RE.search(page2_text)

    if green_match is None or wkk_match is None:
        raise ValueError(
            "Octa+ Fixed: groene stroom of WKK niet gevonden op pagina 2"
        )

    green_value = to_decimal(green_match.group("green"))
    wkk_value = to_decimal(wkk_match.group("wkk"))

    return green_value, wkk_value

def parse_octaplus_fixed(row: TariffRow, lines: Sequence[PdfLine], pdf_path: Path | None = None) -> None:
    extracted_values = extract_octaplus_fixed_formulas(lines, pdf_path=pdf_path)

    row.set("SingleMeterFixed", extracted_values[0])
    row.set("DualMeterDayFixed", extracted_values[1])
    row.set("DualMeterNightFixed", extracted_values[2])
    row.set("ExclusiveNightMeterFixed", extracted_values[3])

    admin_cost = extract_octaplus_fixed_admin_cost(lines)
    green_electricity, wkk = extract_octaplus_fixed_green_and_wkk(lines)

    row.set("AdministrativeCosts", admin_cost)
    row.set("GreenElectricity", green_electricity)
    row.set("WKK", wkk)


def parse_pdf(path: Path) -> TariffRow:
    contract_name = identify_product(path)
    if contract_name is None:
        raise ValueError(f"Unsupported supplier/product filename: {path.name}")
    
    text, lines = extract_pdf(path)
    row = TariffRow(date_key=find_date_key(path, text), contract_name=contract_name)

    match contract_name:
        case "Bolt Elektriciteit":
            parse_bolt(row, lines, path)
        case "DATS24 Elektriciteit":
            parse_dats24(row, lines)
        case "Eneco Zon & Wind Flex":
            parse_eneco(row, lines)
        case "Octa+ Eco Clear":
            parse_octaplus_eco_clear(row, lines)
        case "Octa+ Fixed":
            parse_octaplus_fixed(row, lines, path)
        case _:
            raise ValueError(f"Unsupported supplier/product: {contract_name}")
    return row


def main() -> None:
    if not TARIFF_DIR.is_dir():
        raise FileNotFoundError(f"Tariff directory does not exist: {TARIFF_DIR}")

    pdf_files = sorted(path for path in TARIFF_DIR.glob("*.pdf") if identify_product(path))
    if not pdf_files:
        raise FileNotFoundError(f"No supported PDF files found in {TARIFF_DIR}")

    rows = []
    for pdf_path in tqdm(pdf_files, desc="Parsing PDFs", unit="file"):
        try:
            tariff_row = parse_pdf(pdf_path)
            rows.append(tariff_row.to_csv_dict())
        except Exception as exception:
            raise RuntimeError(f"Failed to parse {pdf_path.name}: {exception}") from exception

    rows.sort(key=lambda row: (row["DateKey"], row["ContractName"]))

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", newline="", encoding="utf-8") as output_stream:
        writer = csv.DictWriter(output_stream, fieldnames=COLUMNS, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)

if __name__ == "__main__":
    main()
