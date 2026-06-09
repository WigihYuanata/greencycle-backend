from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from enum import Enum
from typing import Optional

class UserCreate(BaseModel):
    npm: str
    name: str
    faculty: str
    email: str
    pin: str=Field(min_length=6, max_length=6)
    @field_validator('pin')
    @classmethod
    def pin_harus_angka(cls, v):
        if not v.isdigit():
            raise ValueError('PIN harus berupa angka 6 digit')
        return v
    

class UserLogin(BaseModel):
    npm: str
    pin: str
class UserUpdate(BaseModel):
    name: Optional[str]=None
    faculty:Optional[str]=None
class Token(BaseModel):
    access_token: str
    token_type: str

class ForgotPin(BaseModel):
    npm: str

class ResetPinExecute(BaseModel):
    npm: str
    kode_verifikasi: str
    new_pin: str= Field(min_length=6, max_length=6)
    @field_validator('new_pin')
    @classmethod
    def pin_harus_angka(cls, v):
        if not v.isdigit(): 
            raise ValueError('PIN harus berupa angka 6 digit')
        return v
        


class UserResponse(BaseModel):
    id: int
    npm: str
    name: str
    email: str


    class Config:
        from_attributes=True

class TransactionCreate(BaseModel):
    npm: str
    bottle_small: int=Field(default=0, ge=0)
    bottle_medium: int=Field(default=0, ge=0)
    bottle_large: int= Field(default=0, ge=0)

class TransactionResponse(BaseModel):
    id: int
    user_id: int
    points: int
    created_at: datetime
    message: str

    class Config:
        from_attributes=True


class RewardCreate(BaseModel):
    catalog_id: int

class RewardResponse(BaseModel):
    status: str
    voucher_code: str
    qr_code_url: str
    cafe_name: str
    sisa_point: int

    class Config:
        from_attributes=True

class CardRegistration(BaseModel):
    npm: str
    rfid_uid: str
class DayEnum(str, Enum):
    sabtu="Sabtu"
    minggu="Minggu"
class PickUpOrderCreate(BaseModel):
    pickup_address: str
    contact_number:str
    scheduled_day: DayEnum

class PickUpOrderResponse(BaseModel):
    id:int
    scheduled_day: str
    status: str
    created_at: datetime
    class Config:
        from_attributes=True

class VoucherCatalogCreate(BaseModel):
    name: str
    point_cost: int=Field(ge=1)
    cafe_name: str
    description: Optional[str]= None
    milestone_threshold: int=Field(default=0, ge=0)

class VoucherCatalogResponse(BaseModel):
    id: int
    name: str
    point_cost: int
    cafe_name: str
    description: Optional[str]
    is_active: bool
    milestone_threshold: int
    class Config:
        from_attributes=True
class TransactionHistory(BaseModel):
    id: int
    bottle_small: int
    bottle_medium: int
    bottle_large: int
    points: int
    created_at: datetime

    class Config():
        from_attributes=True

class RewardHistory(BaseModel):
    id: int
    voucher_code: str
    amount: int
    status: str
    created_at: datetime

    class Config:
        from_attributes=True