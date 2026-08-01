import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
import re
from urllib.parse import quote_plus
from datetime import datetime

load_dotenv()
db_url = os.environ.get('DATABASE_URL')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
match = re.match(r"^(postgresql://)([^:]+):(.*)@([^@/]+)(/.*)?$", db_url)
if match:
    scheme, username, password, hostinfo, path = match.groups()
    if "%" not in password:
        password = quote_plus(password)
    db_url = f"{scheme}{username}:{password}@{hostinfo}{path or ''}"

engine = create_engine(db_url)

with engine.connect() as conn:
    print("=== RECHARGES ===")
    result = conn.execute(text("SELECT date, amount, energy_cost FROM recharges ORDER BY date DESC LIMIT 10"))
    for row in result:
        print(f"{row[0]}: amount={row[1]}, energy_cost={row[2]}")
