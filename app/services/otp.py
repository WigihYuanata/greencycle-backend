import secrets
from datetime import datetime, timezone, timedelta

def generate_otp():
    otp_token=str(secrets.randbelow(900000)+100000)
    waktu_expire=datetime.now(timezone.utc)+timedelta(minutes=15)
    return otp_token, waktu_expire