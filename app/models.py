from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, text, Boolean
from app.core.database import Base
from sqlalchemy.orm import relationship

class User(Base):
    __tablename__="users"
    id= Column(Integer, primary_key=True, index=True)
    npm= Column(String(20), unique=True, index=True)
    name= Column(String(100), nullable=False)
    faculty=Column(String(100), nullable=False)
    email=Column(String(100), unique=True, index=True, nullable=False)
    phone_number=Column(String(20), nullable=False, unique=True)

    hashed_pin= Column(String, index=True, nullable=False)
    reset_token= Column(String, index=True, nullable= True)
    reset_token_expire=Column(DateTime, nullable=True)
    is_verified=Column(Boolean, default=False)
    
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
    catalog_id=Column(Integer, ForeignKey('voucher_catalog.id'))
    amount= Column(Integer)

    voucher_code=Column(String, unique=True, index=True)
    secure_token=Column(String(36), unique=True, index=True, nullable=True)
    
    status=Column(String, default="Active")
    created_at= Column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    expires_at=Column(DateTime, nullable=True)

    user= relationship("User", back_populates="reward")
    catalog=relationship("VoucherCatalog")

class VoucherCatalog(Base):
    __tablename__="voucher_catalog"
    id=Column(Integer, primary_key=True, index=True)
    name=Column(String, nullable=False)
    point_cost=Column(Integer, nullable=False)
    cafe_name=Column(String, nullable=False, default="Selasar Caffe")
    description=Column(String, nullable=True)
    is_active=Column(Boolean, default=True)
    milestone_threshold=Column(Integer, default=0, nullable=False)
    voucher_duration_days=Column(Integer, default=7, nullable=False)

class MachineStatus(Base):
    __tablename__="machine_status"
    id=Column(Integer, primary_key=True, index=True)
    machine_id= Column(String(50), nullable=False, unique=True)
    capacity_current=Column(Integer, default=0)
    capacity_max=Column(Integer, nullable=False)
    last_notification_time=Column(DateTime, nullable=True)
    updated_at= Column(DateTime, server_default=text('CURRENT_TIMESTAMP'), onupdate=text('CURRENT_TIMESTAMP'))