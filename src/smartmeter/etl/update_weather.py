from datetime import date, datetime, timedelta
from io import StringIO

import argparse
import pandas as pd
import requests

from smartmeter.db import get_engine

WFS_URL = "https://opendata.meteo.be/service/ows"
BBOX = "3.122,49.620,6.073,51.348"
CHUNK_DAYS = 90

RENAME = {
    "precip_quantity": "PrecipQuantity", "temp_avg": "TempAvg", "temp_max": "TempMax",
    "temp_min": "TempMin", "temp_grass_pt100_avg": "TempGrassPt100Avg",
    "temp_soil_avg": "TempSoilAvg", "temp_soil_avg_5cm": "TempSoilAvg5cm",
    "temp_soil_avg_10cm": "TempSoilAvg10cm", "temp_soil_avg_20cm": "TempSoilAvg20cm",
    "temp_soil_avg_50cm": "TempSoilAvg50cm", "wind_speed_10m": "WindSpeed10m",
    "wind_speed_avg_30m": "WindSpeedAvg30m", "wind_gusts_speed": "WindGustsSpeed",
    "humidity_rel_shelter_avg": "HumidityRelShelterAvg", "pressure": "Pressure",
    "sun_duration": "SunDuration", "short_wave_from_sky_avg": "ShortWaveFromSkyAvg",
    "sun_int_avg": "SunIntAvg",
}

def fetch(start: datetime, end: datetime) -> pd.DataFrame:
    cql = (f"((BBOX(the_geom,{BBOX},'EPSG:4326')) AND (timestamp between '{start:%Y-%m-%d %H:%M:%S}' AND '{end:%Y-%m-%d %H:%M:%S}'))")
    params = {"service": "WFS", "version": "2.0.0", "request": "GetFeature",
              "typenames": "aws:aws_1day", "outputformat": "csv", "CQL_FILTER": cql}
    response = requests.get(WFS_URL, params=params, timeout=120)
    response.raise_for_status()
    if not response.text.strip():
        return pd.DataFrame()
    return pd.read_csv(StringIO(response.text))


def prepare(df: pd.DataFrame, engine) -> pd.DataFrame:
    df = df.drop(columns=["FID", "the_geom", "qc_flags"], errors="ignore").rename(columns=RENAME)

    stations = pd.read_sql("SELECT WeatherStationKey, WeatherStationID FROM DimWeatherStation", engine)
    stations["WeatherStationID"] = pd.to_numeric(stations["WeatherStationID"])
    df = df.merge(stations, how="inner", left_on="code", right_on="WeatherStationID")
    df = df.drop(columns=["code", "WeatherStationID"])

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["DateKey"] = df["timestamp"].dt.strftime("%Y%m%d").astype(int)
    df["FullTime"] = df["timestamp"].dt.strftime("%H:%M:%S")
    dim_time = pd.read_sql("SELECT TimeKey, FullTime FROM DimTime", engine)
    df = df.merge(dim_time, how="inner", on="FullTime")
    df = df.drop(columns=["FullTime", "timestamp"])
    return df.drop_duplicates(subset=["WeatherStationKey", "DateKey", "TimeKey"])


def main(start_override: date | None = None):
    engine = get_engine()

    last = pd.read_sql("SELECT MAX(DateKey) AS d FROM FactWeather", engine)["d"].iloc[0]
    if pd.notna(last):
        start = datetime.strptime(str(int(last)), "%Y%m%d") + timedelta(days=1)
    elif start_override:
        start = datetime.combine(start_override, datetime.min.time())
    else:
        raise SystemExit("FactWeather is empty: run with --from YYYY-MM-DD (e.g. 2023-01-01).")
    end = datetime.combine(date.today(), datetime.min.time())
    if start >= end:
        print("No new data to retrieve")
        return

    total, current = 0, start
    while current < end:
        next = min(current + timedelta(days=CHUNK_DAYS), end)
        raw = fetch(current, next)
        if not raw.empty:
            df = prepare(raw, engine)
            df.to_sql("FactWeather", engine, if_exists="append", index=False, chunksize=5000)
            total += len(df)
        current = next + timedelta(days=1)
    print(f"FactWeather: {total} rows inserted")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="start", type=date.fromisoformat, default=None)
    args = parser.parse_args()
    main(args.start)
