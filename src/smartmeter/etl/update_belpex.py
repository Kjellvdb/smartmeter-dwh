from datetime import date, datetime, timedelta
from sqlalchemy import text

import pandas as pd
import argparse
import requests

from smartmeter.config import ENERGY_CHARTS_URL
from smartmeter.db import get_engine

CHUNK_DAYS = 31

def parse_response(payload: dict) -> pd.DataFrame:
    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    try:
        seconds, prices = data["unix_seconds"], data["price"]
    except (KeyError, TypeError):
        raise ValueError(f"Unexpected payload, got keys: {list(data)[:10] if hasattr(data, '__iter__') else data}")

    df = pd.DataFrame({"ts": pd.to_datetime(seconds, unit="s", utc=True), "BelpexPrice": prices})
    df = df.dropna(subset=["BelpexPrice"])
    df["ts"] = df["ts"].dt.tz_convert("Europe/Brussels").dt.tz_localize(None)
    df = df.set_index("ts").resample("h").mean().dropna().reset_index()
    df["DateKey"] = df["ts"].dt.strftime("%Y%m%d").astype(int)
    df["FullTime"] = df["ts"].dt.strftime("%H:%M:%S")
    return df[["DateKey", "FullTime", "BelpexPrice"]]

def fetch(start: date, end: date) -> pd.DataFrame:
    request = requests.get(
      ENERGY_CHARTS_URL,
      params={"bzn": "BE", "start": start.isoformat(), "end": end.isoformat()},
      timeout=60
    )
    request.raise_for_status()
    return parse_response(request.json())

def main(start_override: date | None = None):
    engine = get_engine()
    last = pd.read_sql("SELECT MAX(DateKey) AS d FROM FactBelpex", engine)["d"].iloc[0]

    if pd.notna(last):
        start = datetime.strptime(str(int(last)), "%Y%m%d").date()
    elif start_override:
        start = start_override
    else:
        raise SystemExit("FactBelpex is empty: run with --from YYYY-MM-DD (e.g. 2023-01-01).")

    end = date.today() - timedelta(days=1)
    new = fetch(start, end)
    if new.empty:
        print("No new data to retrieve")
        return

    dim_time = pd.read_sql("SELECT TimeKey, FullTime FROM DimTime", engine)
    new = new.merge(dim_time, how="inner", on="FullTime").drop(columns=["FullTime"])

    existing = pd.read_sql(f"SELECT DateKey, TimeKey FROM FactBelpex WHERE DateKey >= {int(new['DateKey'].min())}", engine)
    new = new.merge(existing, how="left", on=["DateKey", "TimeKey"], indicator=True)
    new = new[new["_merge"] == "left_only"].drop(columns=["_merge"])
    if new.empty:
        print("FactBelpex is up to date")
        return
    new["Belpex_RLP_MPrice"] = None

    first = int(new["DateKey"].min())
    with engine.begin() as connection:
        connection.execute(text("IF OBJECT_ID('dbo.UpdateFactBelpex','TR') IS NOT NULL DISABLE TRIGGER dbo.UpdateFactBelpex ON dbo.FactBelpex"))
        new.to_sql("FactBelpex", connection, if_exists="append", index=False, chunksize=5000)
        connection.execute(text("IF OBJECT_ID('dbo.UpdateFactBelpex','TR') IS NOT NULL ENABLE TRIGGER dbo.UpdateFactBelpex ON dbo.FactBelpex"))
        connection.execute(text("UPDATE dbo.FactBelpex SET BelpexPrice = BelpexPrice WHERE DateKey >= :d"), {"d": first})
    print(f"FactBelpex: {len(new)} rows inserted")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="start", type=date.fromisoformat, default=None)
    args = parser.parse_args()
    main(args.start)
