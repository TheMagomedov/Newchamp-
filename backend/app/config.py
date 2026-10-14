from pathlib import Path
import os
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env')
DATABASE = os.getenv('CHAMP_DATABASE', 'ChampTraining_20261013')
SERVER = os.getenv('CHAMP_SERVER', 'localhost')
DRIVER = os.getenv('CHAMP_DRIVER', 'ODBC Driver 17 for SQL Server')
SECRET = os.getenv('CHAMP_SECRET', '')
RUNTIME = ROOT / 'runtime'
RUNTIME.mkdir(exist_ok=True)

def odbc(database=DATABASE):
    return f'DRIVER={{{DRIVER}}};SERVER={SERVER};DATABASE={database};Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;'

