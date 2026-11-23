from tqdm import tqdm

import pandas as pd
import re

from smartmeter.config import DATA_DIR

DISTRIBUTION_DIR = DATA_DIR / "distribution"
OUTPUT_FILE = DATA_DIR / "input" / "Distributiekosten.csv"

TARGET_COLUMNS = [
    "Van",
    "Tot",
    "Intercommunale",
    "Capaciteitstarief_Digitale_meter",
    "Afnametarief_Digitale_meter_Normaal",
    "Afnametarief_Digitale_meter_Exclusief_nacht",
    "Capaciteitstarief_Klassieke_meter",
    "Afnametarief_Klassieke_meter_Normaal",
    "Afnametarief_Klassieke_meter_Exclusief_nacht",
    "Prosumententarief",
    "Tarief_databeheer_Jaar_en_maandgelezen_meters",
    "Tarief_databeheer_Kwartiergelezen_meters",
]

def extract_period(df: pd.DataFrame) -> tuple[str, str]:
    pattern = re.compile(r"geldt van\s+(\d{2}/\d{2}/\d{4})\s+t\.e\.m\.\s+(\d{2}/\d{2}/\d{4})")
    for value in df.stack():
        match = pattern.search(str(value))
        if match:
            return match.group(1), match.group(2)
    raise ValueError("Geldigheidsperiode niet gevonden in overzichtssheet")

def extract_intercommunales(df: pd.DataFrame) -> tuple[int, dict[int, str]]:
    for index, row in df.iterrows():
        if isinstance(row[3], str) and row[[0, 1, 2]].isna().all():
            names = {
                col: re.sub(r"\s+", " ", str(value)).strip()
                for col, value in row.items()
                if col >= 3 and pd.notna(value)
            }
            return index, names
    raise ValueError("Headerrij met intercommunales niet gevonden")

def classify_row(label: str) -> str | None:
    label = label.lower()
    if label.startswith("capaciteitstarief"):
        return "capaciteit"
    if label.startswith("totaal kwh-tarief - exclusief nacht"):
        return "kwh_excl_nacht"
    if label.startswith("totaal kwh-tarief"):
        return "kwh_normaal"
    if label.startswith("prosumententarief"):
        return "prosumenten"
    if label.startswith("tarief databeheer"):
        if "kwartier" in label:
            return "databeheer_kwartier"
        if "maandelijks" in label:
            return "databeheer_maand"
        return "databeheer_alle"
    return None

def extract_blocks(df: pd.DataFrame, header_index: int, names: dict[int, str]) -> dict:
    blocks: dict = {}
    current = None
    for index in range(header_index + 1, len(df)):
        col0, label = df.iloc[index, 0], df.iloc[index, 1]
        if isinstance(col0, str) and isinstance(label, str):
            col0_clean = col0.strip().lower()
            label_clean = label.strip().lower()

            if not col0_clean.startswith("inclusief"):
                current = None
                continue

            btw = "incl"
            meter = "digitaal" if "digitale" in label_clean else "klassiek"
            current = blocks.setdefault((btw, meter), {})
            continue

        if current is None or not isinstance(label, str):
            continue

        label_clean = label.strip().lower()
        if label_clean.startswith("opmerkingen"):
            break

        kind = classify_row(label)
        if kind is not None:
            row_values = {}
            for col, name in names.items():
                raw_val = df.iloc[index, col]
                try:
                    row_values[name] = float(raw_val)
                except (TypeError, ValueError):
                    continue
            current[kind] = row_values
    return blocks

def normalize_name(name: str, year: int) -> str:
    if year >= 2025 and name.startswith("Fluvius ") and "(" not in name:
        return f"Fluvius ({name.removeprefix('Fluvius ').strip()})"
    return name

def parse_file(file) -> pd.DataFrame:
    df = pd.read_excel(file, sheet_name=0, header=None)

    van, tot = extract_period(df)
    year = int(van[-4:])
    header_index, names = extract_intercommunales(df)
    blocks = extract_blocks(df, header_index, names)

    digitaal = blocks[("incl", "digitaal")]
    klassiek = blocks[("incl", "klassiek")]

    def databeheer(block: dict, key: str, name: str) -> float:
        return block[key][name] if key in block else block["databeheer_alle"][name]

    rows = []
    for name in names.values():
        rows.append({
            "Van": van,
            "Tot": tot,
            "Intercommunale": normalize_name(name, year),
            "Capaciteitstarief_Digitale_meter": digitaal["capaciteit"][name],
            "Afnametarief_Digitale_meter_Normaal": digitaal["kwh_normaal"][name] / 10,
            "Afnametarief_Digitale_meter_Exclusief_nacht": digitaal["kwh_excl_nacht"][name] / 10,
            "Capaciteitstarief_Klassieke_meter": klassiek["capaciteit"][name],
            "Afnametarief_Klassieke_meter_Normaal": klassiek["kwh_normaal"][name] / 10,
            "Afnametarief_Klassieke_meter_Exclusief_nacht": klassiek["kwh_excl_nacht"][name] / 10,
            "Prosumententarief": klassiek["prosumenten"][name],
            "Tarief_databeheer_Jaar_en_maandgelezen_meters": databeheer(digitaal, "databeheer_maand", name),
            "Tarief_databeheer_Kwartiergelezen_meters": databeheer(digitaal, "databeheer_kwartier", name),
        })
    return pd.DataFrame(rows, columns=TARGET_COLUMNS)

def main():
    files = sorted(DISTRIBUTION_DIR.glob("*.xlsx"))
    frames = [parse_file(file) for file in tqdm(files, desc="Processing Distribution files", unit="file")]

    df = pd.concat(frames, ignore_index=True)
    numeric = df.columns.difference(["Van", "Tot", "Intercommunale"])
    df[numeric] = df[numeric].round(6)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_FILE, index=False)

if __name__ == "__main__":
    main()
