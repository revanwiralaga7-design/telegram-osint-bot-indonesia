#!/usr/bin/env python3
"""
Telegram OSINT Bot with Inline Keyboard
Multi-search: Phone, NIK, Name, Plate Number, Email
Database: osint_Backup.db (2.2GB)
"""

import os
import re
import html
import sqlite3
import asyncio
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ==================== CONFIG ====================
DB_PATH = os.getenv("OSINT_DB_PATH", "/home/user/osint_Backup.db")
BOT_TOKEN = os.getenv("BOT_TOKEN", "DUMMY_TOKEN_FOR_TESTING")

# Validate token only when actually running the bot
def validate_token():
    if not os.getenv("BOT_TOKEN"):
        raise ValueError("BOT_TOKEN environment variable is required")

# ==================== LOGGING ====================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== DATABASE ====================
class OSINTDatabase:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = None
    
    def get_conn(self):
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn
    
    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    # --- Search by Phone ---
    def search_by_phone(self, phone: str) -> List[Dict]:
        """Search phone_registry by phone number"""
        conn = self.get_conn()
        cursor = conn.cursor()
        
        # Normalize phone
        phone = phone.replace("+62", "62").replace("0", "62", 1) if phone.startswith("0") else phone
        phone = phone.replace("+", "").replace(" ", "").replace("-", "")
        
        # Search in phone_registry
        cursor.execute("""
            SELECT phone, nik, provider, date, source
            FROM phone_registry
            WHERE phone LIKE ?
            LIMIT 20
        """, (f"%{phone}%",))
        
        results = [dict(row) for row in cursor.fetchall()]
        
        # Enrich with citizen_data if NIK found
        for r in results:
            nik = r.get("nik")
            if nik:
                citizen = self.get_citizen_by_nik(nik)
                if citizen:
                    r['citizen'] = citizen
        
        return results

    # --- Search by NIK ---
    def search_by_nik(self, nik: str) -> Dict[str, Any]:
        """Comprehensive search by NIK across all tables"""
        nik = nik.strip()
        result = {"nik": nik}
        
        # Citizen data
        citizen = self.get_citizen_by_nik(nik)
        if citizen:
            result["citizen_data"] = citizen
        
        # Phone numbers
        phones = self.get_phones_by_nik(nik)
        if phones:
            result["phones"] = phones
        
        # SIM data
        sims = self.get_sim_by_nik(nik)
        if sims:
            result["sim_data"] = sims
        
        # Vehicle data
        vehicles = self.get_vehicles_by_nik(nik)
        if vehicles:
            result["vehicles"] = vehicles
        
        # Government letters
        letters = self.get_gov_letters_by_nik(nik)
        if letters:
            result["government_letters"] = letters
        
        # Shopping/e-commerce data
        ecommerce = self.get_ecommerce_by_nik(nik)
        if ecommerce:
            result["ecommerce"] = ecommerce
        
        # Member data (education)
        members = self.get_members_by_nik(nik)
        if members:
            result["member_data"] = members
        
        return result

    def get_citizen_by_nik(self, nik: str) -> Optional[Dict]:
        conn = self.get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM citizen_data WHERE nik = ? LIMIT 1", (nik,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_phones_by_nik(self, nik: str) -> List[Dict]:
        conn = self.get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT phone, provider, date, source
            FROM phone_registry
            WHERE nik = ?
            LIMIT 10
        """, (nik,))
        return [dict(row) for row in cursor.fetchall()]

    def get_sim_by_nik(self, nik: str) -> List[Dict]:
        conn = self.get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT pencarian, no_peserta, instansi, tanggal, source
            FROM sim_data
            WHERE pencarian LIKE ? OR no_peserta LIKE ?
            LIMIT 10
        """, (f"%{nik}%", f"%{nik}%"))
        return [dict(row) for row in cursor.fetchall()]

    def get_vehicles_by_nik(self, nik: str) -> List[Dict]:
        conn = self.get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT plate_number, bpkb, name, address, brand, type, 
                   vin_number, engine_number, color, year, source
            FROM vehicle_data
            WHERE nik = ?
            LIMIT 10
        """, (nik,))
        return [dict(row) for row in cursor.fetchall()]

    def get_gov_letters_by_nik(self, nik: str) -> List[Dict]:
        conn = self.get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT title, pengirim, nip, suggestion, tgl_surat, no_surat, source
            FROM government_letters
            WHERE nip LIKE ? OR pengirim LIKE ?
            LIMIT 10
        """, (f"%{nik}%", f"%{nik}%"))
        return [dict(row) for row in cursor.fetchall()]

    def get_ecommerce_by_nik(self, nik: str) -> Dict[str, List]:
        conn = self.get_conn()
        cursor = conn.cursor()
        result = {}
        
        # Bukalapak
        cursor.execute("SELECT * FROM bukalapak_data WHERE user_id LIKE ? LIMIT 5", (f"%{nik}%",))
        rows = cursor.fetchall()
        if rows:
            result["bukalapak"] = [dict(r) for r in rows]
        
        # Shopee (search by buyer_name or address)
        cursor.execute("SELECT * FROM shopee_data WHERE buyer_name LIKE ? OR address LIKE ? LIMIT 5", 
                       (f"%{nik}%", f"%{nik}%"))
        rows = cursor.fetchall()
        if rows:
            result["shopee"] = [dict(r) for r in rows]
        
        # Indo Store
        cursor.execute("SELECT * FROM indo_store_data WHERE telepon LIKE ? OR email LIKE ? LIMIT 5",
                       (f"%{nik}%", f"%{nik}%"))
        rows = cursor.fetchall()
        if rows:
            result["indo_store"] = [dict(r) for r in rows]
        
        # BSI Bank
        cursor.execute("SELECT * FROM bsi_bank_data WHERE phone LIKE ? OR phone62 LIKE ? OR email LIKE ? LIMIT 5",
                       (f"%{nik}%", f"%{nik}%", f"%{nik}%"))
        rows = cursor.fetchall()
        if rows:
            result["bsi_bank"] = [dict(r) for r in rows]
        
        # Shopping Indo
        cursor.execute("SELECT * FROM shopping_indo_data WHERE phone LIKE ? OR active_phone LIKE ? LIMIT 5",
                       (f"%{nik}%", f"%{nik}%"))
        rows = cursor.fetchall()
        if rows:
            result["shopping_indo"] = [dict(r) for r in rows]
        
        # SG Shopping
        cursor.execute("SELECT * FROM sg_shopping_data WHERE mobile LIKE ? OR home_phone LIKE ? LIMIT 5",
                       (f"%{nik}%", f"%{nik}%"))
        rows = cursor.fetchall()
        if rows:
            result["sg_shopping"] = [dict(r) for r in rows]
        
        # Indihome
        cursor.execute("SELECT * FROM indihome_data WHERE mobile LIKE ? OR email LIKE ? LIMIT 5",
                       (f"%{nik}%", f"%{nik}%"))
        rows = cursor.fetchall()
        if rows:
            result["indihome"] = [dict(r) for r in rows]
        
        # Visa Card
        cursor.execute("SELECT * FROM visa_card_data WHERE raw_data LIKE ? LIMIT 5", (f"%{nik}%",))
        rows = cursor.fetchall()
        if rows:
            result["visa_card"] = [dict(r) for r in rows]
        
        # Police
        cursor.execute("SELECT * FROM police_data WHERE nama LIKE ? OR hp LIKE ? OR email LIKE ? LIMIT 5",
                       (f"%{nik}%", f"%{nik}%", f"%{nik}%"))
        rows = cursor.fetchall()
        if rows:
            result["police"] = [dict(r) for r in rows]
        
        return result

    def get_members_by_nik(self, nik: str) -> List[Dict]:
        conn = self.get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM member_data
            WHERE phone_number LIKE ?
            LIMIT 5
        """, (f"%{nik}%",))
        return [dict(row) for row in cursor.fetchall()]

    # --- Search by Name ---
    def search_by_name(self, name: str) -> Dict[str, List]:
        name = name.strip().upper()
        conn = self.get_conn()
        cursor = conn.cursor()
        result = {}
        
        # Citizen data
        cursor.execute("SELECT * FROM citizen_data WHERE UPPER(nama) LIKE ? LIMIT 10", (f"%{name}%",))
        rows = cursor.fetchall()
        if rows:
            result["citizen_data"] = [dict(r) for r in rows]
        
        # Vehicle data
        cursor.execute("SELECT * FROM vehicle_data WHERE UPPER(name) LIKE ? LIMIT 10", (f"%{name}%",))
        rows = cursor.fetchall()
        if rows:
            result["vehicles"] = [dict(r) for r in rows]
        
        # Member data
        cursor.execute("SELECT * FROM member_data WHERE UPPER(nama_lengkap) LIKE ? LIMIT 10", (f"%{name}%",))
        rows = cursor.fetchall()
        if rows:
            result["member_data"] = [dict(r) for r in rows]
        
        # Government letters
        cursor.execute("SELECT * FROM government_letters WHERE UPPER(pengirim) LIKE ? LIMIT 10", (f"%{name}%",))
        rows = cursor.fetchall()
        if rows:
            result["government_letters"] = [dict(r) for r in rows]
        
        # Shopee buyer
        cursor.execute("SELECT * FROM shopee_data WHERE UPPER(buyer_name) LIKE ? LIMIT 10", (f"%{name}%",))
        rows = cursor.fetchall()
        if rows:
            result["shopee_buyer"] = [dict(r) for r in rows]
        
        # Indo store
        cursor.execute("SELECT * FROM indo_store_data WHERE UPPER(nama) LIKE ? LIMIT 10", (f"%{name}%",))
        rows = cursor.fetchall()
        if rows:
            result["indo_store"] = [dict(r) for r in rows]
        
        # BSI Bank
        cursor.execute("SELECT * FROM bsi_bank_data WHERE UPPER(name) LIKE ? LIMIT 10", (f"%{name}%",))
        rows = cursor.fetchall()
        if rows:
            result["bsi_bank"] = [dict(r) for r in rows]
        
        # Shopping Indo
        cursor.execute("SELECT * FROM shopping_indo_data WHERE UPPER(first_name) LIKE ? OR UPPER(last_name) LIKE ? LIMIT 10",
                       (f"%{name}%", f"%{name}%"))
        rows = cursor.fetchall()
        if rows:
            result["shopping_indo"] = [dict(r) for r in rows]
        
        # SG Shopping
        cursor.execute("SELECT * FROM sg_shopping_data WHERE UPPER(name) LIKE ? LIMIT 10", (f"%{name}%",))
        rows = cursor.fetchall()
        if rows:
            result["sg_shopping"] = [dict(r) for r in rows]
        
        # Pertamina
        cursor.execute("SELECT * FROM pertamina_data WHERE UPPER(name) LIKE ? LIMIT 10", (f"%{name}%",))
        rows = cursor.fetchall()
        if rows:
            result["pertamina"] = [dict(r) for r in rows]
        
        # Police
        cursor.execute("SELECT * FROM police_data WHERE UPPER(nama) LIKE ? LIMIT 10", (f"%{name}%",))
        rows = cursor.fetchall()
        if rows:
            result["police"] = [dict(r) for r in rows]
        
        # Visa Card (search in raw_data)
        cursor.execute("SELECT * FROM visa_card_data WHERE UPPER(raw_data) LIKE ? LIMIT 10", (f"%{name}%",))
        rows = cursor.fetchall()
        if rows:
            result["visa_card"] = [dict(r) for r in rows]
        
        return result

    # --- Search by Plate Number ---
    def search_by_plate(self, plate: str) -> List[Dict]:
        plate = plate.strip().upper().replace(" ", "")
        conn = self.get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT plate_number, bpkb, name, nik, address, brand, type,
                   vin_number, engine_number, color, year, source
            FROM vehicle_data
            WHERE REPLACE(UPPER(plate_number), ' ', '') LIKE ?
            LIMIT 10
        """, (f"%{plate}%",))
        return [dict(row) for row in cursor.fetchall()]

    # --- Search by Email ---
    def search_by_email(self, email: str) -> Dict[str, List]:
        email = email.strip().lower()
        conn = self.get_conn()
        cursor = conn.cursor()
        result = {}
        
        tables = [
            ("bukalapak", "bukalapak_data", "email"),
            ("shopee", "shopee_data", "buyer_name"),
            ("indo_store", "indo_store_data", "email"),
            ("bsi_bank", "bsi_bank_data", "email"),
            ("shopping_indo", "shopping_indo_data", "email"),
            ("sg_shopping", "sg_shopping_data", "email"),
            ("indihome", "indihome_data", "email"),
            ("pertamina", "pertamina_data", "email"),
            # Microsoft tables
            ("ms_contacts", "ms_contacts", "email"),
            ("ms_leads", "ms_leads", "email"),
            ("ms_users", "ms_users", "email"),
            ("ms_incidents", "ms_incidents", "email"),
            # Police (has email column)
            ("police", "police_data", "email"),
        ]
        
        for key, table, col in tables:
            try:
                cursor.execute(f"SELECT * FROM {table} WHERE LOWER({col}) LIKE ? LIMIT 10", (f"%{email}%",))
                rows = cursor.fetchall()
                if rows:
                    result[key] = [dict(r) for r in rows]
            except sqlite3.OperationalError:
                pass
        
        return result

    # --- Search Microsoft by Name ---
    def search_microsoft_by_name(self, name: str) -> Dict[str, List]:
        name = name.strip()
        conn = self.get_conn()
        cursor = conn.cursor()
        result = {}
        
        ms_tables = [
            ("ms_contacts", "ms_contacts", "name"),
            ("ms_leads", "ms_leads", "name"),
            ("ms_users", "ms_users", "name"),
            ("ms_incidents", "ms_incidents", "title"),
        ]
        
        for key, table, col in ms_tables:
            try:
                cursor.execute(f"SELECT * FROM {table} WHERE {col} LIKE ? LIMIT 10", (f"%{name}%",))
                rows = cursor.fetchall()
                if rows:
                    result[key] = [dict(r) for r in rows]
            except sqlite3.OperationalError:
                pass
        
        return result

    # --- Search Microsoft by Phone ---
    def search_microsoft_by_phone(self, phone: str) -> Dict[str, List]:
        # Normalize: remove all non-digits for matching
        phone_digits = "".join(c for c in phone if c.isdigit())
        conn = self.get_conn()
        cursor = conn.cursor()
        result = {}
        
        # For Microsoft tables, phone has formats like "+1 (425) 7277334"
        # Use REPLACE to strip common non-digit chars
        phone_clean_expr = "REPLACE(REPLACE(REPLACE(REPLACE({col}, '+', ''), '(', ''), ')', ''), ' ', '')"
        
        ms_tables = [
            ("ms_contacts", "ms_contacts"),
            ("ms_leads", "ms_leads"),
            ("ms_users", "ms_users"),
        ]
        
        for key, table in ms_tables:
            try:
                expr = phone_clean_expr.format(col="phone")
                cursor.execute(f"SELECT * FROM {table} WHERE {expr} LIKE ? LIMIT 10", (f"%{phone_digits}%",))
                rows = cursor.fetchall()
                if rows:
                    result[key] = [dict(r) for r in rows]
            except sqlite3.OperationalError:
                pass
        
        # Police data (hp column)
        try:
            expr = phone_clean_expr.format(col="hp")
            cursor.execute(f"SELECT * FROM police_data WHERE {expr} LIKE ? LIMIT 10", (f"%{phone_digits}%",))
            rows = cursor.fetchall()
            if rows:
                result["police"] = [dict(r) for r in rows]
        except sqlite3.OperationalError:
            pass
        
        return result

    # --- Auto-detect search type ---
    def detect_search_type(self, query: str) -> str:
        """Detect if query is phone, NIK, name, plate, or email"""
        query = query.strip()
        
        # Email check
        if "@" in query and "." in query:
            return "email"
        
        # NIK check (16 digits)
        if query.isdigit() and len(query) == 16:
            return "nik"
        
        # Phone check (starts with 62, 08, +62, or 8)
        phone_clean = query.replace("+", "").replace(" ", "").replace("-", "")
        if phone_clean.startswith(("62", "08")) or (phone_clean.startswith("8") and len(phone_clean) >= 10):
            return "phone"
        
        # Plate check (contains letters and numbers, typical Indonesian format)
        # e.g., B1234ABC, KT1234ZF, etc.
        if any(c.isalpha() for c in query) and any(c.isdigit() for c in query):
            # Check if it looks like a plate (2-3 letters, numbers, 1-3 letters)
            import re
            if re.match(r'^[A-Z]{1,3}\s?\d{1,4}\s?[A-Z]{1,3}$', query.upper().replace(" ", "")):
                return "plate"
        
        # Default to name search
        return "name"


# ==================== FORMATTERS ====================
def format_citizen(data: Dict) -> str:
    lines = ["🆔 <b>DATA KEPENDUDUKAN</b>"]
    fields = [
        ("NIK", "nik"),
        ("Nama", "nama"),
        ("Jenis Kelamin", "jenis_kelamin"),
        ("Tempat Lahir", "tempat_lahir"),
        ("Tanggal Lahir", "tanggal_lahir"),
        ("Agama", "agama"),
        ("Status Kawin", "status_kawin"),
        ("Pendidikan", "pendidikan"),
        ("Pekerjaan", "pekerjaan"),
        ("Nama Ibu", "nama_ibu"),
        ("Nama Ayah", "nama_ayah"),
        ("No KK", "no_kk"),
        ("Source", "source"),
    ]
    for label, key in fields:
        val = data.get(key)
        if val:
            lines.append(f"  {label}: <code>{val}</code>")
    return "\n".join(lines)

def format_phone(data: Dict) -> str:
    return f"📱 <b>Nomor:</b> <code>{data.get('phone','-')}</code> | <b>Provider:</b> {data.get('provider','-')} | <b>Date:</b> {data.get('date','-')} | <b>Source:</b> {data.get('source','-')}"

def format_vehicle(data: Dict) -> str:
    lines = ["🚘 <b>KENDARAAN</b>"]
    fields = [
        ("Plat", "plate_number"),
        ("BPKB", "bpkb"),
        ("Nama", "name"),
        ("NIK", "nik"),
        ("Alamat", "address"),
        ("Merk", "brand"),
        ("Tipe", "type"),
        ("VIN", "vin_number"),
        ("Engine", "engine_number"),
        ("Warna", "color"),
        ("Tahun", "year"),
        ("Source", "source"),
    ]
    for label, key in fields:
        val = data.get(key)
        if val:
            lines.append(f"  {label}: <code>{val}</code>")
    return "\n".join(lines)

def format_sim(data: Dict) -> str:
    return f"🆔 <b>SIM:</b> Pencarian: <code>{data.get('pencarian','-')}</code> | Peserta: {data.get('no_peserta','-')} | Instansi: {data.get('instansi','-')} | Tanggal: {data.get('tanggal','-')} | Source: {data.get('source','-')}"

def format_gov_letter(data: Dict) -> str:
    return f"📄 <b>Surat:</b> {data.get('title','-')} | Dari: {data.get('pengirim','-')} | NIP: {data.get('nip','-')} | No: {data.get('no_surat','-')} | Tgl: {data.get('tgl_surat','-')}"

def format_ecommerce(key: str, data: Dict) -> str:
    icons = {
        "bukalapak": "🛒",
        "shopee": "🛍️",
        "indo_store": "🏪",
        "bsi_bank": "🏦",
        "shopping_indo": "🛒",
        "sg_shopping": "🛒",
        "indihome": "🌐",
        "pertamina": "⛽",
    }
    icon = icons.get(key, "📦")
    lines = [f"{icon} <b>{key.upper()}</b>"]
    for k, v in data.items():
        if v and k not in ("id", "source", "password_hash"):
            lines.append(f"  {k}: <code>{v}</code>")
    return "\n".join(lines)

def format_ms_contact(data: Dict) -> str:
    lines = ["👤 <b>MICROSOFT CONTACT</b>"]
    fields = [
        ("Email", "email"),
        ("Name", "name"),
        ("Phone", "phone"),
        ("Company", "company"),
        ("Title", "title"),
        ("City", "city"),
        ("Country", "country"),
        ("Department", "department"),
        ("Address", "address"),
        ("Source", "source"),
    ]
    for label, key in fields:
        val = data.get(key)
        if val:
            lines.append(f"  {label}: <code>{val}</code>")
    return "\n".join(lines)

def format_ms_lead(data: Dict) -> str:
    lines = ["🎯 <b>MICROSOFT LEAD</b>"]
    fields = [
        ("Email", "email"),
        ("Name", "name"),
        ("Phone", "phone"),
        ("Company", "company"),
        ("Title", "title"),
        ("City", "city"),
        ("Country", "country"),
        ("Industry", "industry"),
        ("Address", "address"),
        ("Source", "source"),
    ]
    for label, key in fields:
        val = data.get(key)
        if val:
            lines.append(f"  {label}: <code>{val}</code>")
    return "\n".join(lines)

def format_ms_user(data: Dict) -> str:
    lines = ["👤 <b>MICROSOFT USER</b>"]
    fields = [
        ("Email", "email"),
        ("Name", "name"),
        ("Username", "username"),
        ("Phone", "phone"),
        ("Department", "department"),
        ("Title", "title"),
        ("Domain", "domain"),
        ("Source", "source"),
    ]
    for label, key in fields:
        val = data.get(key)
        if val:
            lines.append(f"  {label}: <code>{val}</code>")
    return "\n".join(lines)

def format_ms_incident(data: Dict) -> str:
    lines = ["🚨 <b>MICROSOFT INCIDENT</b>"]
    fields = [
        ("Title", "title"),
        ("Description", "description"),
        ("Email", "email"),
        ("Contact", "contact"),
        ("Priority", "priority"),
        ("Status", "status"),
        ("Category", "category"),
        ("Created", "created"),
        ("Source", "source"),
    ]
    for label, key in fields:
        val = data.get(key)
        if val:
            lines.append(f"  {label}: <code>{val}</code>")
    return "\n".join(lines)


# ==================== KEYBOARDS ====================


def format_visa_card(data: Dict) -> str:
    raw = data.get('raw_data', '')
    parts = raw.split('|') if raw else []
    lines = ["💳 <b>VISA CARD</b>"]
    if len(parts) >= 4:
        lines.append(f"  Card: <code>{parts[0]}</code>")
        lines.append(f"  Exp: {parts[1]}/{parts[2]}")
        lines.append(f"  CVV: <code>{parts[3]}</code>")
    lines.append(f"  Source: {data.get('source', '-')}")
    return "\n".join(lines)

def format_police(data: Dict) -> str:
    lines = ["👮 <b>POLICE DATA</b>"]
    fields = [
        ("Pangkat", "pangkat"),
        ("Nama", "nama"),
        ("Tugas/Unit", "tugas"),
        ("HP", "hp"),
        ("Email", "email"),
        ("Source", "source"),
    ]
    for label, key in fields:
        val = data.get(key)
        if val and val != '-':
            lines.append(f"  {label}: <code>{val}</code>")
    return "\n".join(lines)

def format_member(data: Dict) -> str:
    lines = ["🎓 <b>DATA MEMBER/PELAJAR</b>"]
    fields = [
        ("Nama", "nama_lengkap"),
        ("Tempat Lahir", "tempat_lahir"),
        ("Tanggal Lahir", "tanggal_lahir"),
        ("Alamat", "alamat"),
        ("Phone", "phone_number"),
        ("Jurusan", "jurusan"),
        ("Prodi", "program_studi"),
        ("Fakultas", "fakultas"),
        ("Tahun Ajaran", "tahun_ajaran"),
        ("Gender", "gender"),
    ]
    for label, key in fields:
        val = data.get(key)
        if val:
            lines.append(f"  {label}: <code>{val}</code>")
    return "\n".join(lines)

def get_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Cari Lagi", callback_data="search_again")],
        [InlineKeyboardButton("📊 Stats Database", callback_data="db_stats"),
         InlineKeyboardButton("❓ Bantuan", callback_data="help")],
        [InlineKeyboardButton("🗑️ Hapus Riwayat", callback_data="clear_history")],
    ])

def get_result_keyboard(search_type: str, query: str) -> InlineKeyboardMarkup:
    buttons = []
    
    if search_type == "phone":
        buttons.append([InlineKeyboardButton("🆔 Cari NIK Terkait", callback_data=f"nik_search_{query}")])
    elif search_type == "nik":
        buttons.append([InlineKeyboardButton("📱 Cari Nomor Lain", callback_data=f"phone_by_nik_{query}")])
        buttons.append([InlineKeyboardButton("🚘 Cari Kendaraan", callback_data=f"vehicle_by_nik_{query}")])
    elif search_type == "name":
        buttons.append([InlineKeyboardButton("🔎 Cari Lebih Detail", callback_data=f"name_detail_{query}")])
    elif search_type == "plate":
        buttons.append([InlineKeyboardButton("👤 Cari Pemilik (NIK)", callback_data=f"owner_by_plate_{query}")])
    elif search_type == "email":
        buttons.append([InlineKeyboardButton("🗂️ Cari di Semua Tabel", callback_data=f"email_deep_{query}")])
    
    buttons.append([InlineKeyboardButton("⬅️ Kembali ke Menu", callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)


# Telegram limits text messages to 4,096 UTF-16 code units. Keep chunks
# comfortably below that limit so emoji and formatting never push them over.
TELEGRAM_SAFE_MESSAGE_LIMIT = 3500


def telegram_text_length(text: str) -> int:
    """Return Telegram's approximate message length (UTF-16 code units)."""
    return len(text.encode("utf-16-le")) // 2


def split_plain_text(text: str, limit: int) -> List[str]:
    """Split plain text without cutting a Unicode character in half."""
    parts = []
    current = []
    current_length = 0

    for char in text:
        char_length = 2 if ord(char) > 0xFFFF else 1
        if current and current_length + char_length > limit:
            parts.append("".join(current))
            current = []
            current_length = 0
        current.append(char)
        current_length += char_length

    if current:
        parts.append("".join(current))
    return parts


def split_html_message(text: str, limit: int = TELEGRAM_SAFE_MESSAGE_LIMIT) -> List[str]:
    """Split an HTML message at line boundaries into Telegram-safe chunks.

    Formatter output uses complete HTML tags on each line. In the unlikely case
    that one line alone exceeds the limit, formatting is removed from that line
    before splitting so Telegram never receives an unclosed HTML tag.
    """
    chunks: List[str] = []
    current_lines: List[str] = []
    current_length = 0

    for line in text.splitlines(keepends=True):
        line_length = telegram_text_length(line)

        if line_length > limit:
            if current_lines:
                chunks.append("".join(current_lines).rstrip("\n"))
                current_lines = []
                current_length = 0

            plain_line = re.sub(r"<[^>]*>", "", line).rstrip("\n")
            escaped_line = html.escape(plain_line)
            chunks.extend(split_plain_text(escaped_line, limit))
            continue

        if current_lines and current_length + line_length > limit:
            chunks.append("".join(current_lines).rstrip("\n"))
            current_lines = []
            current_length = 0

        current_lines.append(line)
        current_length += line_length

    if current_lines:
        chunks.append("".join(current_lines).rstrip("\n"))

    return [chunk for chunk in chunks if chunk] or ["Tidak ada hasil."]


async def send_search_result(update: Update, searching_msg, text: str, reply_markup) -> None:
    """Edit the loading message and send overflow as additional messages."""
    chunks = split_html_message(text)
    last_index = len(chunks) - 1

    await searching_msg.edit_text(
        chunks[0],
        parse_mode="HTML",
        reply_markup=reply_markup if last_index == 0 else None,
    )

    for index, chunk in enumerate(chunks[1:], 1):
        await update.message.reply_html(
            chunk,
            reply_markup=reply_markup if index == last_index else None,
        )


# ==================== BOT HANDLERS ====================
db = OSINTDatabase(DB_PATH)
user_states = {}  # user_id -> last query info

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome = (
        f"👋 Halo {user.first_name}!\n\n"
        "🤖 <b>OSINT Indonesia Bot</b>\n"
        "Database: 2.2GB | 18+ tabel | 3.5M+ records\n\n"
        "<b>Cara pakai:</b> Kirim saja:\n"
        "• 📱 <b>Nomor HP</b> (08xx, 628xx, +628xx)\n"
        "• 🆔 <b>NIK</b> (16 digit)\n"
        "• 👤 <b>Nama</b> (contoh: Budi Santoso)\n"
        "• 🚘 <b>Plat Nomor</b> (contoh: B1234ABC)\n"
        "• 📧 <b>Email</b> (contoh: user@gmail.com)\n\n"
        "Bot akan deteksi otomatis & cari di semua tabel relevan."
    )
    await update.message.reply_html(welcome, reply_markup=get_main_keyboard())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "❓ <b>BANTUAN OSINT BOT</b>\n\n"
        "<b>Tipe Pencarian Otomatis:</b>\n"
        "• <code>08123456789</code> → Cari di phone_registry (2M records)\n"
        "• <code>3175070604891001</code> → Cari NIK di semua tabel\n"
        "• <code>Budi Santoso</code> → Cari nama di citizen, vehicle, member, dll\n"
        "• <code>B1234ABC</code> → Cari plat di vehicle_data (600K records)\n"
        "• <code>user@gmail.com</code> → Cari email di e-commerce & services\n\n"
        "<b>Tabel Database:</b>\n"
        "📱 phone_registry (2M) | 🆔 citizen_data (2K)\n"
        "🆔 sim_data (500K) | 🚘 vehicle_data (600K)\n"
        "📄 government_letters (500K) | 🛒 bukalapak (500K)\n"
        "🛍️ shopee (174K) | 🏪 indo_store (70K)\n"
        "🏦 bsi_bank (508) | 🎓 member_data (148K)\n"
        "🛒 shopping_indo (3K) | 🛒 sg_shopping (103K)\n"
        "🌐 indihome (10K) | ⛽ pertamina\n\n"
        "<b>Inline Keyboard:</b>\n"
        "Gunakan tombol di bawah hasil pencarian untuk navigasi cepat."
    )
    await update.message.reply_html(help_text, reply_markup=get_main_keyboard())

async def db_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = (
        "📊 <b>STATISTIK DATABASE (12.4M+ Records)</b>\n\n"
        "🇮🇩 <b>INDONESIA:</b>\n"
        "📱 phone_registry: 2,000,006\n"
        "🆔 citizen_data: 2,000\n"
        "🆔 sim_data: 500,000\n"
        "🎓 member_data: 148,200\n"
        "🚘 vehicle_data: 599,288\n"
        "📄 government_letters: 507,484\n"
        "🛒 bukalapak_data: 507,872\n"
        "🛍️ shopee_data: 173,917\n"
        "🏪 indo_store_data: 69,999\n"
        "🏦 bsi_bank_data: 508\n"
        "🛒 shopping_indo_data: 3,334\n"
        "🛒 sg_shopping_data: 103,501\n"
        "🌐 indihome_data: 10,000\n"
        "⛽ pertamina_data: 0\n"
        "🗳️ kpu_data: 0\n"
        "🌐 indihome_browse_data: 0\n"
        "💳 visa_card_data: 210,725\n"
        "👮 police_data: 341,798\n\n"
        "💻 <b>MICROSOFT (7.2M+):</b>\n"
        "👤 ms_contacts: 4,490,903\n"
        "🎯 ms_leads: 68,995\n"
        "👥 ms_users: 309,630\n"
        "🚨 ms_incidents: 2,364,982\n"
        "🔐 ms_credentials: 0\n\n"
        f"💾 File: {os.path.getsize(DB_PATH) / (1024**3):.2f} GB"
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(stats, parse_mode="HTML", reply_markup=get_main_keyboard())
    else:
        await update.message.reply_html(stats, reply_markup=get_main_keyboard())

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    if not query:
        return
    
    user_id = update.effective_user.id
    search_type = db.detect_search_type(query)
    
    # Store state
    user_states[user_id] = {"last_query": query, "last_type": search_type}
    
    # Send searching message
    searching_msg = await update.message.reply_html(f"🔍 <b>Mencari...</b> <code>{query}</code> (tipe: {search_type})")
    
    try:
        if search_type == "phone":
            results = await search_phone(query)
        elif search_type == "nik":
            results = await search_nik(query)
        elif search_type == "name":
            results = await search_name(query)
        elif search_type == "plate":
            results = await search_plate(query)
        elif search_type == "email":
            results = await search_email(query)
        else:
            results = "❌ Tipe pencarian tidak dikenali."
        
        await send_search_result(
            update,
            searching_msg,
            results,
            get_result_keyboard(search_type, query),
        )
    except Exception as e:
        logger.error(f"Search error: {e}")
        await searching_msg.edit_text(f"❌ Error: {str(e)}", reply_markup=get_main_keyboard())

async def search_phone(phone: str) -> str:
    results = db.search_by_phone(phone)
    
    # Also search Microsoft tables
    ms_results = db.search_microsoft_by_phone(phone)
    
    if not results and not ms_results:
        return f"Tidak ditemukan data untuk nomor: <code>{phone}</code>"
    
    header = f"HASIL PENCARIAN NOMOR: <code>{phone}</code>\n"
    lines = [header]
    
    # Phone registry results
    if results:
        lines.append(f"PHONE REGISTRY ({len(results)})")
        for i, r in enumerate(results[:10], 1):
            lines.append(f"{i}. {format_phone(r)}")
            if r.get("citizen"):
                lines.append(f"   {format_citizen(r['citizen'])}")
            lines.append("")
        if len(results) > 10:
            lines.append(f"... dan {len(results) - 10} record lainnya")
        lines.append("")
    
    # Microsoft + Police results
    if ms_results:
        total_ms = sum(len(v) for v in ms_results.values())
        lines.append(f"MICROSOFT & POLICE DATA ({total_ms})")
        for table, items in ms_results.items():
            lines.append(f"  {table.upper()}: {len(items)} record")
            for item in items[:3]:
                if table == "ms_contacts":
                    lines.append(f"  {format_ms_contact(item)}")
                elif table == "ms_leads":
                    lines.append(f"  {format_ms_lead(item)}")
                elif table == "ms_users":
                    lines.append(f"  {format_ms_user(item)}")
                elif table == "police":
                    lines.append(f"  {format_police(item)}")
                elif table == "visa_card":
                    lines.append(f"  {format_visa_card(item)}")
            lines.append("")
    
    return "\n".join(lines)

async def search_nik(nik: str) -> str:
    result = db.search_by_nik(nik)
    
    lines = [f"🔎 <b>HASIL PENCARIAN NIK:</b> <code>{nik}</code>\n"]
    
    if result.get("citizen_data"):
        lines.append(format_citizen(result["citizen_data"]))
        lines.append("")
    
    if result.get("phones"):
        lines.append(f"📱 <b>NOMOR TELEPON ({len(result['phones'])})</b>")
        for p in result["phones"][:5]:
            lines.append(f"  {format_phone(p)}")
        lines.append("")
    
    if result.get("vehicles"):
        lines.append(f"🚘 <b>KENDARAAN ({len(result['vehicles'])})</b>")
        for v in result["vehicles"][:5]:
            lines.append(f"  {format_vehicle(v)}")
        lines.append("")
    
    if result.get("sim_data"):
        lines.append(f"🆔 <b>DATA SIM ({len(result['sim_data'])})</b>")
        for s in result["sim_data"][:3]:
            lines.append(f"  {format_sim(s)}")
        lines.append("")
    
    if result.get("government_letters"):
        lines.append(f"📄 <b>SURAT PEMERINTAH ({len(result['government_letters'])})</b>")
        for g in result["government_letters"][:3]:
            lines.append(f"  {format_gov_letter(g)}")
        lines.append("")
    
    if result.get("member_data"):
        lines.append(f"🎓 <b>DATA MEMBER ({len(result['member_data'])})</b>")
        for m in result["member_data"][:3]:
            lines.append(f"  {format_member(m)}")
        lines.append("")
    
    if result.get("ecommerce"):
        lines.append(f"🛒 <b>DATA E-COMMERCE & LAYANAN</b>")
        for key, items in result["ecommerce"].items():
            lines.append(f"  🛍️ {key.upper()}: {len(items)} record")
            for item in items[:2]:
                lines.append(f"     {format_ecommerce(key, item)}")
        lines.append("")
    
    if len(lines) == 1:
        lines.append("❌ Tidak ditemukan data untuk NIK ini.")
    
    return "\n".join(lines)

async def search_name(name: str) -> str:
    results = db.search_by_name(name)
    
    # Also search Microsoft tables
    ms_results = db.search_microsoft_by_name(name)
    if ms_results:
        results.update(ms_results)
    
    if not results:
        return f"❌ Tidak ditemukan data untuk nama: <code>{name}</code>"
    
    lines = [f"🔎 <b>HASIL PENCARIAN NAMA:</b> <code>{name}</code>\n"]
    
    total = sum(len(v) for v in results.values())
    lines.append(f"📊 Total: {total} record dari {len(results)} tabel\n")
    
    for table, items in results.items():
        lines.append(f"📂 <b>{table.upper()} ({len(items)})</b>")
        for item in items[:5]:
            if table == "citizen_data":
                lines.append(f"  {format_citizen(item)}")
            elif table == "vehicles":
                lines.append(f"  {format_vehicle(item)}")
            elif table == "member_data":
                lines.append(f"  {format_member(item)}")
            elif table == "ms_contacts":
                lines.append(f"  {format_ms_contact(item)}")
            elif table == "ms_leads":
                lines.append(f"  {format_ms_lead(item)}")
            elif table == "ms_users":
                lines.append(f"  {format_ms_user(item)}")
            elif table == "ms_incidents":
                lines.append(f"  {format_ms_incident(item)}")
            elif table == "police":
                lines.append(f"  {format_police(item)}")
            elif table == "visa_card":
                lines.append(f"  {format_visa_card(item)}")
            else:
                lines.append(f"  {format_ecommerce(table, item)}")
        lines.append("")
    
    return "\n".join(lines)

async def search_plate(plate: str) -> str:
    results = db.search_by_plate(plate)
    
    if not results:
        return f"❌ Tidak ditemukan kendaraan dengan plat: <code>{plate}</code>"
    
    lines = [f"🔎 <b>HASIL PENCARIAN PLAT:</b> <code>{plate}</code>", f"✅ Ditemukan: {len(results)} record\n"]
    
    for i, r in enumerate(results[:10], 1):
        lines.append(f"{i}. {format_vehicle(r)}")
        lines.append("")
    
    if len(results) > 10:
        lines.append(f"... dan {len(results) - 10} record lainnya")
    
    return "\n".join(lines)

async def search_email(email: str) -> str:
    results = db.search_by_email(email)
    
    if not results:
        return f"❌ Tidak ditemukan data untuk email: <code>{email}</code>"
    
    lines = [f"🔎 <b>HASIL PENCARIAN EMAIL:</b> <code>{email}</code>\n"]
    
    total = sum(len(v) for v in results.values())
    lines.append(f"📊 Total: {total} record dari {len(results)} tabel\n")
    
    for table, items in results.items():
        lines.append(f"📂 <b>{table.upper()} ({len(items)})</b>")
        for item in items[:5]:
            lines.append(f"  {format_ecommerce(table, item)}")
        lines.append("")
    
    return "\n".join(lines)


# ==================== CALLBACK HANDLERS ====================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Answer immediately to remove loading state
    
    user_id = query.from_user.id
    data = query.data
    
    if data == "main_menu":
        await query.edit_message_text(
            "🏠 <b>MENU UTAMA</b>\n\nKirim query untuk pencarian:\n"
            "📱 Nomor HP | 🆔 NIK | 👤 Nama | 🚘 Plat | 📧 Email",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )
    
    elif data == "help":
        await help_cmd(update, context)
    
    elif data == "db_stats":
        await db_stats(update, context)
    
    elif data == "clear_history":
        user_states.pop(user_id, None)
        await query.edit_message_text("🗑️ Riwayat pencarian dibersihkan.", reply_markup=get_main_keyboard())
    
    elif data == "search_again":
        await query.edit_message_text(
            "🔍 <b>CARI LAGI</b>\n\nKirim query baru:\n"
            "📱 Nomor HP | 🆔 NIK | 👤 Nama | 🚘 Plat | 📧 Email",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )
    
    # Quick actions from results
    elif data.startswith("nik_search_"):
        phone = data.replace("nik_search_", "")
        # Search for NIKs related to this phone
        results = db.search_by_phone(phone)
        nik_set = set()
        for r in results:
            if r.get("nik"):
                nik_set.add(r['nik'])
        
        if nik_set:
            text = f"🆔 <b>NIK Terkait Nomor {phone}:</b>\n\n"
            for nik in list(nik_set)[:10]:
                text += f"• <code>{nik}</code>\n"
                # Get name
                citizen = db.get_citizen_by_nik(nik)
                if citizen:
                    text += f"  → {citizen.get('nama', '-')}\n"
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=get_result_keyboard("phone", phone))
        else:
            await query.edit_message_text("❌ Tidak ada NIK terkait.", reply_markup=get_result_keyboard("phone", phone))
    
    elif data.startswith("phone_by_nik_"):
        nik = data.replace("phone_by_nik_", "")
        phones = db.get_phones_by_nik(nik)
        if phones:
            text = f"📱 <b>Nomor Telepon untuk NIK {nik}:</b>\n\n"
            for p in phones:
                text += f"• {format_phone(p)}\n"
        else:
            text = f"❌ Tidak ada nomor telepon untuk NIK {nik}"
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=get_result_keyboard("nik", nik))
    
    elif data.startswith("vehicle_by_nik_"):
        nik = data.replace("vehicle_by_nik_", "")
        vehicles = db.get_vehicles_by_nik(nik)
        if vehicles:
            text = f"🚘 <b>Kendaraan untuk NIK {nik}:</b>\n\n"
            for v in vehicles:
                text += f"{format_vehicle(v)}\n\n"
        else:
            text = f"❌ Tidak ada kendaraan untuk NIK {nik}"
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=get_result_keyboard("nik", nik))
    
    elif data.startswith("owner_by_plate_"):
        plate = data.replace("owner_by_plate_", "")
        results = db.search_by_plate(plate)
        if results:
            text = f"👤 <b>Pemilik Plat {plate}:</b>\n\n"
            for r in results:
                text += f"• Nama: <code>{r.get('name','-')}</code>\n"
                text += f"  NIK: <code>{r.get('nik','-')}</code>\n"
                text += f"  Alamat: {r.get('address','-')}\n\n"
        else:
            text = f"❌ Tidak ditemukan pemilik untuk plat {plate}"
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=get_result_keyboard("plate", plate))
    
    elif data.startswith("name_detail_"):
        name = data.replace("name_detail_", "")
        # Just re-search with more results
        results = db.search_by_name(name)
        text = f"🔎 <b>Detail Nama: {name}</b>\n\n"
        for table, items in results.items():
            text += f"📂 {table.upper()}: {len(items)} record\n"
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=get_result_keyboard("name", name))
    
    elif data.startswith("email_deep_"):
        email = data.replace("email_deep_", "")
        results = db.search_by_email(email)
        text = f"📧 <b>Deep Search Email: {email}</b>\n\n"
        for table, items in results.items():
            text += f"📂 {table.upper()}: {len(items)} record\n"
            for item in items[:3]:
                text += f"  {format_ecommerce(table, item)}\n"
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=get_result_keyboard("email", email))


# ==================== MAIN ====================
async def post_init(application: Application):
    await application.bot.set_my_commands([
        ("start", "🚀 Memulai bot"),
        ("help", "❓ Bantuan & panduan"),
        ("stats", "📊 Statistik database"),
    ])

def main():
    validate_token()
    print("🚀 Starting OSINT Bot...")
    print(f"🗄️ Database: {DB_PATH}")
    print(f"💾 Size: {os.path.getsize(DB_PATH) / (1024**3):.2f} GB")
    
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("stats", db_stats))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(callback_handler))
    
    # Run
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()