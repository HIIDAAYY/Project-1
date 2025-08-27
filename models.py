from sqlalchemy import create_engine, Column, Integer, String, JSON
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()
engine = create_engine('sqlite:///products.db')
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Product(Base):
    __tablename__ = 'products'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    stock = Column(Integer)
    colors = Column(JSON)

class Order(Base):
    __tablename__ = 'orders'
    id = Column(Integer, primary_key=True, index=True)
    user_number = Column(String)
    product_name = Column(String)
    quantity = Column(Integer)
    status = Column(String, default="pending")

Base.metadata.create_all(bind=engine)