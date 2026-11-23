from __future__ import annotations

import io
import pandas as pd
import requests

from smartmeter.config import DATA_DIR

WFS_URL = "https://opendata.meteo.be/service/ows"
OUTPUT_FILE = DATA_DIR / "input" / "aws_station.csv"

def fetch_aws_stations() -> pd.DataFrame:
    params = {
        "service": "wfs",
        "version": "2.0.0",
        "request": "getFeature",
        "typeNames": "aws:aws_station",
        "outputformat": "csv",
    }

    response = requests.get(WFS_URL, params=params, timeout=30)
    response.raise_for_status()

    df = pd.read_csv(io.StringIO(response.text))
    if df.empty:
        raise ValueError("Geen AWS-stations gevonden.")

    if "code" in df.columns:
        df["code"] = pd.to_numeric(df["code"], errors="coerce").astype("Int64")
        df = df.sort_values(by="code", na_position="last").reset_index(drop=True)

    if "altitude" in df.columns:
        df["altitude"] = pd.to_numeric(df["altitude"], errors="coerce")

    df.drop(columns=["wigos_id"], inplace=True, errors="ignore")
    return df

def main() -> None:
    df = fetch_aws_stations()
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_FILE, index=False)

if __name__ == "__main__":
    main()
