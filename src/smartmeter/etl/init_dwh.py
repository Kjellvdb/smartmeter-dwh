from sqlalchemy import text

import argparse
import re
import time

from smartmeter import config
from smartmeter.db import get_engine

def read_sql_file(path):
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-16"):
        try:
            return raw.decode(enc)
        except UnicodeError:
            continue
    return raw.decode("latin-1")

def batches(sql: str):
    parts = re.split(r"(?im)^\s*GO\s*$|(?=^\s*CREATE\s+OR\s+ALTER\b)", sql)
    return [p.strip() for p in parts if p and p.strip()]

def wait_for_server(retries: int = 30):
    for _ in range(retries):
        try:
            with get_engine("master").connect() as connection:
                connection.execute(text("SELECT 1"))
            return
        except Exception:
            time.sleep(2)
    raise SystemExit("SQL Server not reachable. Check DB_SERVER / DB_PASSWORD / ODBC driver.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--triggers", action="store_true")
    args = parser.parse_args()

    wait_for_server()
    master = get_engine("master", isolation_level="AUTOCOMMIT")
    with master.connect() as connection:
        connection.execute(text(f"IF DB_ID('{config.DATABASE}') IS NULL CREATE DATABASE [{config.DATABASE}]"))

    files = ["03_trigger.sql"] if args.triggers else ["01_create_dwh.sql", "02_procedures.sql"]
    engine = get_engine(isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        for name in files:
            print(f"Running {name} ...")
            for batch in batches(read_sql_file(config.SQL_DIR / name)):
                if re.match(r"(?is)\s*(create|drop)\s+database\b", batch):
                    continue
                connection.exec_driver_sql(batch)
    print("Done.")

if __name__ == "__main__":
    main()
