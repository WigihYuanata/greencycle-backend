from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, text
from app.core.database import Base
from sqlalchemy.orm import relationship
from datetime import datetime

class User(Base):
    __tablename__="users"
    id= Column(Integer, primary_key=True, index=True)
    npm= Column(String(20), unique=True, index=True)
    name= Column(String(100), nullable=False)
    faculty=Column(String(100), nullable=False)
    email=Column(String, unique=True, index=True, nullable=False)
    rfid_uid=Column(String, unique=True, index=True, nullable=True)

    activation_token= Column(String(6), unique=True, index=True, nullable=True)

    transactions= relationship("Transaction", back_populates="user")
    reward=relationship("reward", back_populates="user")



class Transaction(Base):
    __tablename__="transactions"
    id=Column(Integer, primary_key=True, index=True)
    user_id=Column(Integer, ForeignKey("users.id"))

    bottle_small= Column(Integer, default=0)
    bottle_medium= Column(Integer, default=0)
    bottle_large= Column(Integer, default=0)

    points= Column(Integer)
    created_at=Column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    user= relationship("User", back_populates="transactions")

class reward(Base):
    __tablename__= "rewards"
    id =Column(Integer, primary_key=True, index=True)
    user_id= Column(Integer, ForeignKey('users.id'))
    amount= Column(Integer)
    provider=Column(String)
    account_number=Column(String)
    account_name=Column(String)
    status=Column(String, default="pending")
    created_at= Column(DateTime, server_default=text('CURRENT_TIMESTAMP'))

    user= relationship("User", back_populates="reward")

