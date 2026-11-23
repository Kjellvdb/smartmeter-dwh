from pathlib import Path
from dotenv import load_dotenv

import os

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATA_DIR = Path(os.getenv("DATA_DIR", ROOT / "data"))
LOG_DIR = Path(os.getenv("LOG_DIR", ROOT / "logs"))
SQL_DIR = ROOT / "sql"
SAMPLES_DIR = Path(DATA_DIR / "P6269_1_50_DMK_Sample_Elek")
ENERGY_CHARTS_URL = "https://api.energy-charts.info/price"

SERVER = os.getenv("DB_SERVER", "localhost")
PORT = int(os.getenv("DB_PORT", "1433"))
DATABASE = os.getenv("DB_DATABASE", "DigitalMeterDWH")
USERNAME = os.getenv("DB_USERNAME", "sa")
PASSWORD = os.getenv("DB_PASSWORD", "")
ODBC_DRIVER = os.getenv("ODBC_DRIVER", "ODBC Driver 18 for SQL Server")

API_KEY = os.getenv("API_KEY", "")
MAX_LOGFILE_SIZE_MB = int(os.getenv("MAX_LOGFILE_SIZE_MB", "5"))
