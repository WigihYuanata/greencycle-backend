from pydantic import BaseModel, Field, field_validator, AfterValidator
from datetime import datetime
from enum import Enum
from typing import Optional, Annotated


def validasi_npm(v: str) -> str:
    if not v.isdigit():
        raise ValueError('NPM harus berupa angka (digit) saja')
    if len(v)<10:
        raise ValueError('NPM minimal harus terdiri dari 10 digit')
    return v

NpmStr= Annotated[str, AfterValidator(validasi_npm)]

class UserCreate(BaseModel):
    npm: NpmStr
    name: str
    faculty: str
    email: str
    phone_number: str=Field(min_length=9, max_length=15)
    pin: str=Field(min_length=6, max_length=6)
    @field_validator('pin')
    @classmethod
    def pin_harus_angka(cls, v):
        if not v.isdigit():
            raise ValueError('PIN harus berupa angka 6 digit')
        return v
    @field_validator('phone_number')
    @classmethod
    def phone_number_harus_angka(cls, v):
        if not v.replace('+', '').replace('-', '').isdigit():
            raise ValueError('Nomor telepon tidak valid.')
        return v
    

class UserLogin(BaseModel):
    npm: NpmStr
    pin: str
    
class Token(BaseModel):
    access_token: str
    token_type: str

class ForgotPin(BaseModel):
    npm: NpmStr

class ResetPinExecute(BaseModel):
    npm: NpmStr
    kode_verifikasi: str
    new_pin: str= Field(min_length=6, max_length=6)
    @field_validator('new_pin')
    @classmethod
    def pin_harus_angka(cls, v):
        if not v.isdigit(): 
            raise ValueError('PIN harus berupa angka 6 digit')
        return v
        

class TransactionCreate(BaseModel):
    npm: NpmStr
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
    expires_at: datetime

    class Config:
        from_attributes=True

class MachineStatusUpdate(BaseModel):
    machine_id: str
    capacity_current: int=Field(ge=0)
    capacity_max: int=Field(ge=1)


class VoucherCatalogCreate(BaseModel):
    name: str
    point_cost: int=Field(ge=1)
    cafe_name: str
    description: Optional[str]= None
    milestone_threshold: int=Field(default=0, ge=0)
    voucher_duration_days: int=Field(default=7, ge=1)
    image_url: Optional[str]=None

class VoucherCatalogResponse(BaseModel):
    id: int
    name: str
    point_cost: int
    cafe_name: str
    description: Optional[str]
    is_active: bool
    milestone_threshold: int
    voucher_duration_days: int
    image_url: Optional[str]=None

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
    expires_at: Optional[datetime]=None

    class Config:
        from_attributes=True

class QRVerifyRequest(BaseModel):
    npm: NpmStr

class OTPVerify(BaseModel):
    npm: NpmStr
    otp_code: str

class ResendOTP(BaseModel):
    npm: NpmStr