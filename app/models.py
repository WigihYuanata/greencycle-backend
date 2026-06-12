from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, text, Boolean
from app.core.database import Base
from sqlalchemy.orm import relationship

class User(Base):
    __tablename__="users"
    id= Column(Integer, primary_key=True, index=True)
    npm= Column(String(20), unique=True, index=True)
    name= Column(String(100), nullable=False)
    faculty=Column(String(100), nullable=False)
    email=Column(String, unique=True, index=True, nullable=False)
    rfid_uid=Column(String, unique=True, index=True, nullable=True)

    hashed_pin= Column(String, index=True, nullable=False)
    reset_token= Column(String, index=True, nullable= True)
    reset_token_expire=Column(DateTime, nullable=True)

    transactions= relationship("Transaction", back_populates="user")
    reward=relationship("reward", back_populates="user")
    pickup_orders= relationship("PickUpOrder", back_populates="user")

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
    catalog_id=Column(Integer, ForeignKey('voucher_catalog.id'))
    amount= Column(Integer)

    voucher_code=Column(String, unique=True, index=True)
    secure_token=Column(String(36), unique=True, index=True, nullable=True)
    
    status=Column(String, default="Active")
    created_at= Column(DateTime, server_default=text('CURRENT_TIMESTAMP'))

    user= relationship("User", back_populates="reward")
    catalog=relationship("VoucherCatalog")

class VoucherCatalog(Base):
    __tablename__="voucher_catalog"
    id=Column(Integer, primary_key=True, index=True)
    name=Column(String, nullable=False)
    point_cost=Column(Integer, nullable=False)
    cafe_name=Column(String, nullable=False)
    description=Column(String, nullable=True)
    is_active=Column(Boolean, default=True)
    milestone_threshold=Column(Integer, default=0, nullable=False)


class PickUpOrder(Base):
    __tablename__= "pickup_orders"
    id=Column(Integer, primary_key=True, index=True)
    user_id= Column(Integer, ForeignKey("users.id"))
    pickup_address=Column(String, nullable=False)
    contact_number=Column(String, nullable=False)
    scheduled_day=Column(String, nullable=False)
    status=Column(String, default="Pending")
    created_at= Column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    user=relationship("User", back_populates="pickup_orders")