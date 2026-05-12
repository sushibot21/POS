# 🍽️ Restaurant POS System

A complete, production-ready restaurant POS with billing, inventory, suppliers,
hotel management, customer due tracking, and a live mobile dashboard.

---

## 🚀 Quick Start

### Windows
1. Install **Python 3.10+** → https://python.org (check "Add to PATH")
2. Double-click **`START_POS_WINDOWS.bat`**
3. Browser opens automatically at http://localhost:5000/login

### Mac
1. Install **Python 3.10+** → https://python.org (or `brew install python`)
2. Double-click **`START_POS_MAC.command`**
   - If blocked: Right-click → Open → Open anyway
3. Browser opens at http://localhost:5000/login

---

## 📱 Remote Access (Access from phone / anywhere)

### Same Wi-Fi (recommended for table service)
1. Connect phone to same Wi-Fi as the POS PC
2. Find PC's IP: Run `ipconfig` (Windows) or `ifconfig` (Mac) → look for IPv4
3. Open on phone: `http://192.168.x.x:5000` (replace with your PC's IP)
4. Add to Home Screen for app-like experience

### Remote access from anywhere (internet)
Use **ngrok** for secure HTTPS tunneling:
```bash
# Install ngrok: https://ngrok.com/download
ngrok http 5000
# Copy the https://xxxx.ngrok.io URL — works from anywhere
```
Or use **Tailscale** (https://tailscale.com) for a permanent private network.

---

## 🗂️ Pages & Features

| Page | URL | Description |
|------|-----|-------------|
| Login | `/login` | Biller authentication |
| POS Terminal | `/` | Tables, menu, billing |
| Dashboard | `/dashboard` | Live sales, mobile-friendly |
| Reports | `/reports` | Sales by period, CSV export |
| Menu Manager | `/menu` | Items, customizations, portions |
| Inventory | `/inventory` | Stock, suppliers, purchases |
| Customers | `/customers` | History, due tracking |
| Hotel | `/hotel` | Room management |
| Settings | `/settings` | Config, QR upload, GSTIN |
| Admin | `/admin` | Manage biller accounts |

---

## ✨ Feature Highlights

- **Table management** — Add/delete tables, sections (Main, Outdoor, Bar, Terrace)
- **Payment methods** — Cash, UPI (GPay/Paytm/PhonePe/BHIM), Credit/Debit Card, Swiggy, Zomato, Due
- **Due tracking** — Mark orders as due, link to customer, collect later with payment split
- **Inventory** — Raw materials with supplier linking, gm/kg/litre units, purchase records
- **Supplier management** — Track what we owe suppliers, purchase history, date filters
- **Menu customizations** — Spice level, size, extras — shown as picker when ordering
- **Portion costing** — Link inventory ingredients to menu items, auto-deduct on order
- **Hotel dashboard** — Room grid by floor, check-in/check-out, occupancy stats
- **GSTIN + Logo** — Printed on every bill
- **UPI QR code** — Upload once, prints on every bill
- **Print-optimised** — Pure black ink for thermal/laser printers
- **Biller login** — One login per session, admin manages accounts
- **Admin portal** — Create/edit/delete billers, private admin credentials

---

## 💾 Data Storage

All data is stored locally in **`data/pos.db`** (SQLite database).

**Back up this file regularly** — it contains all your orders, customers, inventory, and settings.

```
pos_system/
  data/
    pos.db          ← ALL your data (back this up!)
  static/
    uploads/        ← Uploaded logo, profile pic, QR code
```

---

## 🛵 Swiggy & Zomato Integration

Direct integration requires their Partner API (needs business account):
- **Swiggy**: https://partner.swiggy.com
- **Zomato**: https://www.zomato.com/business

Once approved, enter your API keys in **Settings** page. Orders will appear as Takeaway orders with source tagged as Swiggy/Zomato.

---

## 🔧 Troubleshooting

**"Python not found"** — Reinstall Python and check "Add to PATH"

**Port 5000 already in use** — Edit `app.py` last line, change `port=5000` to `port=5001`

**Can't access from phone** — Check both devices are on same Wi-Fi. Check Windows Firewall allows port 5000.

**Slow on old PC** — POS runs fine on 4GB RAM, dual-core. Disable debug mode (already off by default).
