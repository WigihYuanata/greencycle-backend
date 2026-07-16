import os
import json
import gspread

ws_users=ws_trans=ws_reward=None
try:
    credentials_json=os.getenv("GOOGLE_CREDENTIALS")
    if not credentials_json:
        raise RuntimeError("GOOGLE_CREDENTIALS belum diatur")
    credentials_dict=json.loads(credentials_json)
    gc= gspread.service_account_from_dict(credentials_dict)
    sh= gc.open("GreenCycle")
    ws_users= sh.worksheet("Data_Kontributor")
    ws_trans= sh.worksheet("Transaksi")
    ws_reward=sh.worksheet("Reward")
    print(f"INFO: Koneksi API Google Sheet Berhasil")
except Exception as e:
    print(f"ERROR: Koneksi API Google Sheet Gagal - {e}")

def push_to_sheet(sheet, row_data):
    if sheet is None:
        return
    try:
        sheet.append_row(row_data, value_input_option="USER_ENTERED")
    except Exception as e:
        print(f"ERROR: Gagal mengirim data ke google Spreadsheet - {e}")

def update_status_sheet(r_id, new_status):
    if ws_reward is None:
        return
    try:
        cell= ws_reward.find(str(r_id), in_column=2)
        if cell:
            ws_reward.update_cell(cell.row, 9, new_status)
    except Exception as e:
        print(f"Peringatan: Gagal melakukan sinkronisasi update ke Google Sheets - {e}")