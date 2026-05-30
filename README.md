# 📊 Forex News & Trading Signal Bot

Bot Telegram untuk notifikasi berita ekonomi high impact dan sinyal trading otomatis dengan analisa multi-timeframe.

---

## 🚀 Fitur Utama

- **Notifikasi Berita Otomatis** — 60m, 30m, 15m, 5m sebelum rilis, dan saat rilis
- **Filter High Impact** — NFP, CPI, PPI, FOMC, Fed Rate, ECB, GDP, dll
- **Fokus XAUUSD** — Alert khusus gold dengan analisa mendalam
- **Analisa Multi-Timeframe** — D1, H4, H1, M15, M5, M1
- **Scoring System** — 100 poin, sinyal hanya dikirim jika ≥80
- **AI Market Summary** — Ringkasan kondisi pasar (opsional, butuh OpenAI key)
- **Breakout Alert** — Notifikasi saat harga menembus level penting
- **Dashboard Web** — FastAPI + visualisasi signal history dan statistik
- **Auto Restart** — Systemd service atau Docker dengan restart policy

---

## 📁 Struktur Proyek

```
forex_bot/
├── main.py                     # Entry point
├── requirements.txt
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── core/
│   ├── config.py               # Konfigurasi dari .env
│   └── database.py             # Models PostgreSQL
├── data/
│   ├── news_fetcher.py         # Fetch berita dari Trading Economics & Twelve Data
│   └── market_data.py          # Fetch OHLCV dari Twelve Data & Alpha Vantage
├── analysis/
│   ├── technical.py            # EMA, RSI, ATR, ADX, BB, OB, FVG, Market Structure
│   ├── signal_engine.py        # Scoring + signal generation
│   └── ai_analysis.py          # OpenAI market summary
├── bot/
│   ├── handlers.py             # Telegram command handlers
│   ├── scheduler.py            # Background jobs (news alerts, signal scan)
│   └── formatter.py            # Format pesan Telegram
├── dashboard/
│   └── backend/app.py          # FastAPI REST API
└── deployment/
    └── forex-bot.service       # Systemd service
```

---

## ⚙️ Setup

### 1. Clone & Install

```bash
git clone https://github.com/yourrepo/forex-bot.git
cd forex_bot
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Konfigurasi .env

```bash
cp .env.example .env
nano .env
```

Isi minimal yang **wajib** diisi:

| Variable | Keterangan |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Dari @BotFather |
| `TELEGRAM_GROUP_ID` | ID group tujuan (awali dengan -100) |
| `TELEGRAM_CHANNEL_ID` | ID channel tujuan |
| `DATABASE_URL` | PostgreSQL connection string |
| `TWELVE_DATA_API_KEY` | Dari twelvedata.com (free tier tersedia) |

### 3. Setup PostgreSQL

```bash
sudo -u postgres psql
CREATE DATABASE forex_bot;
CREATE USER forex_user WITH PASSWORD 'yourpassword';
GRANT ALL PRIVILEGES ON DATABASE forex_bot TO forex_user;
\q
```

### 4. Jalankan

```bash
python main.py
```

---

## 🐳 Docker Deployment

```bash
cp .env.example .env
# Edit .env dengan API keys

docker-compose up -d
docker-compose logs -f bot
```

---

## 🖥️ VPS Ubuntu — Systemd Service

```bash
# Copy project ke VPS
sudo cp -r . /opt/forex_bot
cd /opt/forex_bot
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Install systemd service
sudo cp deployment/forex-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable forex-bot
sudo systemctl start forex-bot

# Cek status
sudo systemctl status forex-bot
sudo journalctl -u forex-bot -f
```

---

## 📱 Telegram Commands

| Command | Fungsi |
|---|---|
| `/start` | Mulai bot |
| `/status` | Status bot dan uptime |
| `/news` | Berita high impact hari ini |
| `/gold` | Analisa & sinyal XAUUSD |
| `/signal EURUSD` | Sinyal untuk pair tertentu |
| `/calendar` | Kalender ekonomi 7 hari ke depan |
| `/impact` | Berita high impact berikutnya |
| `/help` | Daftar command |

---

## 📊 Scoring System

| Komponen | Poin |
|---|---|
| Trend (4 TF aligned) | 20 |
| Support/Resistance | 20 |
| RSI | 10 |
| Volume | 10 |
| VWAP | 10 |
| Market Structure | 15 |
| Order Block | 15 |
| **Total** | **100** |

| Score | Sinyal |
|---|---|
| 90-100 | STRONG BUY / STRONG SELL |
| 80-89 | BUY / SELL |
| 70-79 | WEAK (tidak dikirim) |
| <70 | NO TRADE |

---

## 🔑 API Keys

| API | Free Tier | Gunakan untuk |
|---|---|---|
| [Twelve Data](https://twelvedata.com) | 800 req/hari | OHLCV + Kalender |
| [Alpha Vantage](https://alphavantage.co) | 25 req/hari | Fallback OHLCV |
| [Trading Economics](https://tradingeconomics.com/api) | Trial tersedia | Kalender berita |
| OpenAI | Pay per use | AI market summary (opsional) |

---

## ⚠️ Disclaimer

Bot ini dibuat untuk tujuan edukasi dan riset. **Bukan financial advice.**
Trading forex dan gold memiliki risiko tinggi. Selalu gunakan manajemen risiko yang ketat.
Tidak ada strategi yang menjamin profit konsisten. Lakukan forward testing sebelum live trading.

---

## 📝 License

MIT License
