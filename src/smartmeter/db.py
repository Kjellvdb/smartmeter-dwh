from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine

from smartmeter import config

def make_url(database: str | None = None) -> URL:
    return URL.create(
        "mssql+pyodbc",
        username=config.USERNAME,
        password=config.PASSWORD,
        host=config.SERVER,
        port=config.PORT,
        database=database or config.DATABASE,
        query={"driver": config.ODBC_DRIVER, "TrustServerCertificate": "yes"},
    )

def get_engine(database: str | None = None, **kwargs) -> Engine:
    return create_engine(make_url(database), fast_executemany=True, **kwargs)
