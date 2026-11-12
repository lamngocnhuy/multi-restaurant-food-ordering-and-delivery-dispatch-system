#!/usr/bin/env python3
"""Privately provision an initial administrator; password is never a CLI argument."""
import argparse
import getpass
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from database.connection import Base,engine,SessionLocal
from models.entities import User,Driver
from utilities.security import hash_password
from forms.schemas import Register

def main():
    parser=argparse.ArgumentParser(description='Provision an account. Use the admin workspace to provision restaurant partners.')
    parser.add_argument('--email',required=True);parser.add_argument('--name',required=True);parser.add_argument('--phone',default='');parser.add_argument('--role',choices=['admin','driver','customer'],default='admin')
    args=parser.parse_args();password=getpass.getpass('Password (at least 8 characters): ')
    if password!=getpass.getpass('Confirm password: '):raise SystemExit('Passwords did not match.')
    data=Register(email=args.email,name=args.name,password=password,phone=args.phone)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email==data.email)):raise SystemExit('That email is already registered.')
        u=User(email=data.email,name=data.name,phone=data.phone,password_hash=hash_password(data.password),role=args.role,active=True);db.add(u);db.flush()
        if args.role=='driver':db.add(Driver(id=u.id,online=False,available=True))
        db.commit();print(f'Created {args.role} account: {u.email}')
if __name__=='__main__':main()
