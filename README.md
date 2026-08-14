# ��� Telegram OSINT Bot Indonesia

Bot Telegram untuk pencarian OSINT (Open Source Intelligence) menggunakan database lokal 2.2GB dengan **23 tabel** dan **12.4M+ records**.

## ��� Fitur

- **Multi-search otomatis**: Deteksi tipe query (Phone/NIK/Nama/Plat/Email)
- **Inline Keyboard**: Navigasi cepat dengan tombol interaktif
- **Database lengkap**: 23 tabel data Indonesia + Microsoft

### Tipe Pencarian

| Input | Contoh | Tabel yang Dicari |
|-------|--------|-------------------|
| ��� **Nomor HP** | `08123456789`, `628123456789`, `+628123456789` | phone_registry (2M), citizen_data, **ms_contacts, ms_leads, ms_users** |
| ��� **NIK** | `3175070604891001` (16 digit) | Semua tabel (citizen, phone, vehicle, SIM, gov letters, e-commerce, member, Microsoft) |
| ��� **Nama** | `Budi Santoso` | citizen_data, vehicle_data, member_data, gov_letters, shopee, indo_store, bsi_bank, shopping_indo, sg_shopping, pertamina, **ms_contacts, ms_leads, ms_users, ms_incidents** |
| ��� **Plat Nomor** | `B1234ABC`, `KT5207ZF` | vehicle_data (600K) |
| ��� **Email** | `user@gmail.com` | bukalapak, indo_store, bsi_bank, shopping_indo, sg_shopping, indihome, pertamina, **ms_contacts, ms_leads, ms_users, ms_incidents** |

### Tabel Database (12.4M+ Records)

| Tabel | Records | Deskripsi |
|-------|---------|-----------|
| `phone_registry` | 2,000,006 | Nomor HP, NIK, Provider, Tanggal |
| `citizen_data` | 2,000 | Data kependudukan lengkap |
| `sim_data` | 500,000 | Data SIM |
| `vehicle_data` | 599,288 | Kendaraan (plat, BPKB, nama, NIK, alamat, merk, VIN, engine) |
| `government_letters` | 507,484 | Surat pemerintah |
| `bukalapak_data` | 507,872 | Data Bukalapak |
| `shopee_data` | 173,917 | Data Shopee |
| `indo_store_data` | 69,999 | Data toko online Indo |
| `member_data` | 148,200 | Data member/pendidikan |
| `bsi_bank_data` | 508 | Data BSI Bank |
| `shopping_indo_data` | 3,334 | Data shopping Indo |
| `sg_shopping_data` | 103,501 | Data shopping SG |
| `indihome_data` | 10,000 | Data IndiHome |
| `pertamina_data` | 0 | Data Pertamina |
| `kpu_data` | 0 | Data KPU |
| `indihome_browse_data` | 0 | Data browsing IndiHome |
| `ms_contacts` | 4,490,903 | Microsoft Contacts (email, nama, phone, company, title, city, country, dept) |
| `ms_leads` | 68,995 | Microsoft Leads (email, nama, phone, company, title, industry) |
| `ms_users` | 309,630 | Microsoft Users (email, nama, username, phone, department, domain) |
| `ms_incidents` | 2,364,982 | Microsoft Incidents (title, description, email, priority, status, category) |
| `ms_credentials` | 0 | Microsoft Credentials |
| `visa_card_data` | 210,725 | Data Visa Card |
| `police_data` | 341,798 | Data Police |

**TOTAL: 12,413,142 records**

## ��� Instalasi

### 1. Clone & Install Dependencies
```bash
git clone <repo>
cd osint-bot
pip install -r requirements.txt
```

### 2. Setup Environment
```bash
cp .env.example .env
# Edit .env dan isi BOT_TOKEN dari @BotFather
```

### 3. Database
File database `osint_Backup.db` (2.2GB) harus berada di path yang dikonfigurasi di `OSINT_DB_PATH` (default: `/home/user/osint_Backup.db`).

### 4. Jalankan Bot
```bash
python osint_bot.py
```

## ��� Cara Pakai

1. Start bot: `/start`
2. Kirim query langsung:
   - Nomor: `08123456789`
   - NIK: `3175070604891001`
   - Nama: `Budi Santoso`
   - Plat: `B1234ABC`
   - Email: `user@gmail.com`
3. Gunakan **Inline Keyboard** untuk navigasi:
   - Cari NIK terkait dari nomor
   - Cari nomor lain dari NIK
   - Cari kendaraan dari NIK
   - Cari pemilik dari plat
   - Deep search email

## ������ Commands

| Command | Deskripsi |
|---------|-----------|
| `/start` | Memulai bot & menampilkan menu |
| `/help` | Bantuan & panduan lengkap |
| `/stats` | Statistik database |

## ��� Konfigurasi

Environment variables:
- `BOT_TOKEN` - Token bot dari @BotFather (wajib)
- `OSINT_DB_PATH` - Path file database (default: `/home/user/osint_Backup.db`)

## ��� Inline Keyboard Actions

Setiap hasil pencarian memiliki tombol aksi kontekstual:

- **Dari Nomor HP** → Cari NIK Terkait
- **Dari NIK** → Cari Nomor Lain / Cari Kendaraan
- **Dari Nama** → Cari Lebih Detail
- **Dari Plat** → Cari Pemilik (NIK)
- **Dari Email** → Cari di Semua Tabel

## ������ Disclaimer

**Gunakan secara bertanggung jawab dan legal.**
- Data bersifat sensitif, gunakan hanya untuk keperluan yang sah
- Patuhi hukum dan regulasi yang berlaku (UU PDP, dll)
- Bot ini untuk tujuan edukasi & riset keamanan

## ��� License

MIT License - gunakan dengan bijak.