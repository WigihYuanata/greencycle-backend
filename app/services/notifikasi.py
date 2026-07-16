import requests as req
from app.core.config import settings

WHATSAPP_API_URL=settings.WHATSAPP_API_URL
WHATSAPP_API_TOKEN= settings.WHATSAPP_API_TOKEN

TELEGRAM_BOT_TOKEN=settings.TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID=settings.TELEGRAM_CHAT_ID
TELEGRAM_API_URL=f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

def notifikasi_admin_telegram(text: str):
    try:
        req.post(TELEGRAM_API_URL, json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=10)
    except Exception as e:
        print(f"ERROR: Gagal mengirim notifikasi ke telegram - {e}")

def send_registration_whatsapp(target_phone, otp_code):
    message=(
        f"*[GCM SYSTEM - Verifikasi Pendaftaran]*\n\n"
        f"Selamat datang di Green Collective Movement!\n"
        f"Kode OTP Anda untuk menyelesaikan pendaftaran akun:\n\n"

        f"*{otp_code}*\n\n"

        f"_Kode ini berlaku selama 15 menit. Jangan berikan kepada siapapun termasuk Tim GCM._"
    )
    try:
        resp= req.post(WHATSAPP_API_URL, headers={"Authorization":WHATSAPP_API_TOKEN}, json={"target": target_phone, "message": message}, timeout=10)
        try:
            resp_data=resp.json()
        except ValueError:
            resp_data={}
        gagal_dari_gateway=resp.status_code != 200 or resp_data.get("status") is False

        if gagal_dari_gateway:
            print(f"ERROR: Gateway WA menolak/gagal mengirim OTP ke {target_phone} - status_code: {resp.status_code}, response: {resp_data}")
            notifikasi_admin_telegram(f"[GCM - PERINGATAN] Gagal kirim OTP pendaftaran ke {target_phone}. \nResponse gateway WA: {resp_data}")
        else:
            print(f"INFO: Pesan pendaftaran berhasil dikirim ke Nomor: {target_phone}")
    except Exception as e:
        print(f"ERROR: Gagal mengirim pesan OTP pendaftaran ke {target_phone} : {e} ")
        notifikasi_admin_telegram(f"[GCM - PERINGATAN] Exception saat mengirim OTP ke {target_phone}: {e}")

def send_forgot_pin_wa(target_phone, otp_code):
    message=(
        f"*[GCM SYSTEM - Reset PIN]*\n\n"
        f"Kami menerima permintaan reset PIN untuk akun GCM anda.\n"
        f"Kode verifikasi reset PIN Anda:\n\n"

        f"*{otp_code}*\n\n"
        f"Kode ini berlaku selama 15 menit. Jangan berikan kode ini kepada siapaun termasuk tim GCM. Jika anda tidak meminta reset PIN, abaikan pesan ini"
    )
    try:
        resp=req.post(WHATSAPP_API_URL, headers={"Authorization":WHATSAPP_API_TOKEN}, json={"target": target_phone, "message": message}, timeout=10)
        try:
            resp_data=resp.json()
        except ValueError:
            resp_data={}
        gagal_dari_gateway=resp.status_code !=200 or resp_data.get("status") is False

        if gagal_dari_gateway:
            print(f"ERROR: Gateway WA menolak/gagal mengirim OTP reset PIN ke {target_phone} - status_code: {resp.status_code}, response: {resp_data}")
            notifikasi_admin_telegram(f"[GCM - PERINGATAN] Ggagl Kirim OTP reset PIN ke nomor {target_phone}. \nResponse gateway WA: {resp_data}")
        else:
            print(f"INFO: Pesan reset PIN berhasil dikirim ke nomor: {target_phone}")
    except Exception as e:
        print(f"ERROR: Gagal mengirim pesan OTP reset PIN ke {target_phone}: {e}")
        notifikasi_admin_telegram(f"[GCM - PERINGATAN] Exception saat  mengirim OTP reset PIN ke {target_phone}: {e}")

def send_capacity_alert(machine_id, pct: float):
    message=(
        f"[GCM ALERT] Kapasitas Mesin Hampir Penuh!\n\n"
        f"Mesin ID: {machine_id}\n"
        f"Kapasitas saat ini: {pct*100:.0f}%\n\n"
        f"Segera kosongkan mesin agar transaksi tidak terganggu.\n\n"
        f"GCM System - Auto Notification")
    try:
        resp= req.post(TELEGRAM_API_URL, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message
        }, timeout=10 )
        if resp.status_code==200 and resp.json().get("ok"):
            print(f"INFO: Pesan peringatan kapasitas hampir makasimal berhasil dikirim ke Telegram Group")
        else:
            print(f"ERROR: Telegram menolak pesan - status {resp.status_code}, response: {resp.text}")
    except Exception as e:
        print(f"ERROR: Gagal mengirim pesan peringatan ke telegram - {e}")
