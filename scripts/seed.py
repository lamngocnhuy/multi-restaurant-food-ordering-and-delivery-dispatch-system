#!/usr/bin/env python3
"""Seed development data. Explicitly requires SEED_DEMO=true."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from database.connection import Base,engine,SessionLocal
from properties.config import SEED_DEMO
from services.seed import seed
if __name__=='__main__':
    if not SEED_DEMO:raise SystemExit('Set SEED_DEMO=true only in a development environment to seed demo accounts.')
    Base.metadata.create_all(engine)
    with SessionLocal() as db:seed(db)
    print('Demo catalog and accounts are ready.')
