from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "postgresql://ems_4zv5_user:Tics5GBQlO3mQUsAhxKmW8qlxutq98vv@dpg-d8423qcvikkc738pl31g-a/ems_4zv5"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()