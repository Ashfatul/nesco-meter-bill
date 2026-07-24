import sys
import os
import re
from urllib.parse import quote_plus
from sqlalchemy import create_engine, MetaData, Table

def clean_postgres_uri(url):
    """Ensure password is URL-encoded and scheme is postgresql://"""
    if not url:
        return url
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    
    match = re.match(r"^(postgresql://)([^:]+):(.*)@([^@/]+)(/.*)?$", url)
    if match:
        scheme, username, password, hostinfo, path = match.groups()
        if "%" not in password:
            password = quote_plus(password)
        url = f"{scheme}{username}:{password}@{hostinfo}{path or ''}"
    return url

def migrate(sqlite_uri, postgres_uri):
    # Ensure password is encoded
    postgres_uri = clean_postgres_uri(postgres_uri)
    
    print("🔌 Connecting to local SQLite database...")
    sqlite_engine = create_engine(sqlite_uri)
    
    print("🔌 Connecting to remote Supabase PostgreSQL database...")
    postgres_engine = create_engine(postgres_uri)

    metadata = MetaData()
    metadata.reflect(bind=sqlite_engine)

    # Tables in dependency order (parents first, children last)
    tables_order = ['users', 'meters', 'balances', 'recharges', 'monthly_usages']

    try:
        # Verify tables exist on PostgreSQL by importing app context and running create_all
        print("🗄️ Ensuring tables exist on remote database...")
        from app import app, db
        app.config['SQLALCHEMY_DATABASE_URI'] = postgres_uri
        with app.app_context():
            db.create_all()
        print("✅ Tables verified/created successfully.")

        # Migrate data table by table
        for table_name in tables_order:
            if table_name not in metadata.tables:
                print(f"⚠️ Table '{table_name}' not found in SQLite DB. Skipping.")
                continue

            print(f"🔄 Migrating table '{table_name}'...")
            sqlite_table = Table(table_name, metadata, autoload_with=sqlite_engine)
            
            # Read from SQLite
            with sqlite_engine.connect() as sqlite_conn:
                rows = sqlite_conn.execute(sqlite_table.select()).fetchall()
            
            print(f"   Found {len(rows)} records in SQLite.")

            # Reflect PostgreSQL tables
            postgres_metadata = MetaData()
            postgres_metadata.reflect(bind=postgres_engine)
            postgres_table = Table(table_name, postgres_metadata, autoload_with=postgres_engine)

            # Write to PostgreSQL inside a transaction block
            with postgres_engine.begin() as pg_conn:
                # Clear target table to avoid duplicate primary/unique keys
                pg_conn.execute(postgres_table.delete())
                
                # Insert rows one by one
                count = 0
                for row in rows:
                    data = dict(row._mapping)
                    pg_conn.execute(postgres_table.insert().values(**data))
                    count += 1
                
            print(f"   Successfully migrated {count} records into PostgreSQL.")

        print("\n🎉 SQLite to Supabase migration completed successfully!")
    except Exception as e:
        print(f"\n❌ Error during migration: {e}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("❌ Error: Missing connection string.")
        print("Usage: python migrate_data.py \"postgresql://postgres.ref:PASSWORD@host:6543/postgres\"")
        sys.exit(1)
        
    postgres_uri = sys.argv[1]
    sqlite_uri = "sqlite:///instance/nesco.db"
    migrate(sqlite_uri, postgres_uri)
