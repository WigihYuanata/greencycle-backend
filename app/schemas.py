from pydantic import BaseModel
from datetime import datetime
from enum import Enum
from typing import Optional

class pilihan_provider(str, Enum):
    dana="DANA"
    gopay="GoPay"
    shopeepay="ShopeePay"
    ovo="OVO"
    bni="BNI"

class UserCreate(BaseModel):
    npm: str
    name: str
    faculty: str
    email: str

class UserResponse(BaseModel):
    id: int
    npm: str
    name: str
    email: str
    activation_token: Optional[str]

    class Config:
        from_attributes=True

class TransactionCreate(BaseModel):
    npm: str

    bottle_small: int=0
    bottle_medium: int=0
    bottle_large: int=0

class TransactionResponse(BaseModel):
    id: int
    user_id: int
    points: int
    created_at: datetime
    message: str

    class Config:
        from_attributes=True


class RewardCreate(BaseModel):
    npm: str
    amount: int
    provider: pilihan_provider
    account_number: str
    account_name: str

class RewardResponse(BaseModel):
    status: str
    sisa_point: int
    data_penarikan: dict

class RFIDPairing(BaseModel):
    activation_token: str
    rfid_uid: str

