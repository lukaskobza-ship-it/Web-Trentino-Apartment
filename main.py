"""
Apartmán Stenico – Backend (FastAPI)
=====================================
Spuštění:
  pip install fastapi uvicorn aiosmtplib jinja2 python-multipart
  uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException, Depends, Request, Form, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr
from datetime import date, datetime
from typing import Optional, List
import sqlite3, hashlib, os, asyncio, json
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ──────────────────────────────────────────────
# CONFIG – upravte dle vašeho nastavení
# ──────────────────────────────────────────────
SMTP_HOST     = "smtp.gmail.com"
SMTP_PORT     = 587
SMTP_USER     = "dkonly456@gmail.com"          # ← váš Gmail
SMTP_PASSWORD = "hbvn rglj bycf omtg"          # ← App Password (ne heslo k účtu!)
NOTIFY_EMAIL  = "lukas.kobza@icloud.com"            # ← kam chodit notifikace
ADMIN_PASSWORD = hashlib.sha256(b"Anastazie0329").hexdigest()  # ← změňte heslo!
SECRET_TOKEN  = "stenico-secret-2025"          # ← tajný token pro admin session

DB_PATH = "stenico.db"

# ──────────────────────────────────────────────
# APP
# ──────────────────────────────────────────────
app = FastAPI(title="Apartmán Stenico API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # V produkci nastavte konkrétní doménu
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")

# ──────────────────────────────────────────────
# DATABASE
# ──────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS rezervace (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            jmeno       TEXT NOT NULL,
            email       TEXT NOT NULL,
            telefon     TEXT,
            osoby       INTEGER DEFAULT 2,
            datum_od    DATE NOT NULL,
            datum_do    DATE NOT NULL,
            zprava      TEXT,
            stav        TEXT DEFAULT 'nova',  -- nova | potvrzena | zrusena
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS blokovane_dny (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            datum    DATE NOT NULL UNIQUE,
            poznamka TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ──────────────────────────────────────────────
# MODELS
# ──────────────────────────────────────────────
class PoptavkaIn(BaseModel):
    jmeno:    str
    email:    EmailStr
    telefon:  Optional[str] = None
    osoby:    int = 2
    datum_od: date
    datum_do: date
    zprava:   Optional[str] = None

class RezervaceOut(BaseModel):
    id:         int
    jmeno:      str
    email:      str
    telefon:    Optional[str]
    osoby:      int
    datum_od:   str
    datum_do:   str
    zprava:     Optional[str]
    stav:       str
    created_at: str

class StavUpdate(BaseModel):
    stav: str  # potvrzena | zrusena | nova

# ──────────────────────────────────────────────
# EMAIL HELPER
# ──────────────────────────────────────────────
async def send_email(to: str, subject: str, html_body: str):
    """Odešle e-mail přes Gmail SMTP."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SMTP_USER
    msg["To"]      = to
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    try:
        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            start_tls=True,
            username=SMTP_USER,
            password=SMTP_PASSWORD,
        )
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")  # Logujeme, ale nepadáme

def email_host_html(r: dict) -> str:
    return f"""
    <div style="font-family:sans-serif;max-width:600px;margin:auto">
      <h2 style="color:#0f1f3d">Nová poptávka – Apartmán Stenico</h2>
      <table style="width:100%;border-collapse:collapse">
        <tr><td style="padding:8px;color:#555">Jméno:</td><td><b>{r['jmeno']}</b></td></tr>
        <tr><td style="padding:8px;color:#555">E-mail:</td><td>{r['email']}</td></tr>
        <tr><td style="padding:8px;color:#555">Telefon:</td><td>{r.get('telefon','—')}</td></tr>
        <tr><td style="padding:8px;color:#555">Osoby:</td><td>{r['osoby']}</td></tr>
        <tr><td style="padding:8px;color:#555">Příjezd:</td><td>{r['datum_od']}</td></tr>
        <tr><td style="padding:8px;color:#555">Odjezd:</td><td>{r['datum_do']}</td></tr>
        <tr><td style="padding:8px;color:#555">Zpráva:</td><td>{r.get('zprava','—')}</td></tr>
      </table>
      <p style="margin-top:1rem">
        <a href="http://localhost:8000/admin" style="background:#c9a84c;color:#fff;padding:10px 20px;text-decoration:none">
          Otevřít admin panel
        </a>
      </p>
    </div>
    """

def email_guest_html(r: dict) -> str:
    return f"""
    <div style="font-family:sans-serif;max-width:600px;margin:auto">
      <h2 style="color:#0f1f3d">Děkujeme za vaši poptávku!</h2>
      <p>Vážený/á <b>{r['jmeno']}</b>,</p>
      <p>vaši poptávku jsme přijali a ozveme se vám do 24 hodin.</p>
      <table style="width:100%;border-collapse:collapse;margin:1rem 0">
        <tr><td style="padding:6px;color:#555">Příjezd:</td><td><b>{r['datum_od']}</b></td></tr>
        <tr><td style="padding:6px;color:#555">Odjezd:</td><td><b>{r['datum_do']}</b></td></tr>
        <tr><td style="padding:6px;color:#555">Počet osob:</td><td>{r['osoby']}</td></tr>
      </table>
      <p>S pozdravem,<br><b>Apartmán Stenico</b></p>
    </div>
    """

# ──────────────────────────────────────────────
# ADMIN AUTH (jednoduchý token v cookie)
# ──────────────────────────────────────────────
def is_admin(request: Request) -> bool:
    return request.cookies.get("admin_token") == SECRET_TOKEN

def require_admin(request: Request):
    if not is_admin(request):
        raise HTTPException(status_code=401, detail="Nepřihlášen")

# ──────────────────────────────────────────────
# ── PUBLIC ENDPOINTS ──
# ──────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/admin")

# 1. Odeslat poptávku z kontaktního formuláře
@app.post("/api/poptavka", status_code=201)
async def odeslat_poptavku(data: PoptavkaIn, db: sqlite3.Connection = Depends(get_db)):
    # Validace dat
    if data.datum_od >= data.datum_do:
        raise HTTPException(400, "Datum odjezdu musí být po datu příjezdu.")
    if data.datum_od < date.today():
        raise HTTPException(400, "Datum příjezdu nemůže být v minulosti.")

    # Kontrola dostupnosti (jednoduché překrytí)
    existing = db.execute("""
        SELECT id FROM rezervace
        WHERE stav != 'zrusena'
          AND datum_od < ? AND datum_do > ?
    """, (str(data.datum_do), str(data.datum_od))).fetchone()
    if existing:
        raise HTTPException(409, "Termín je již obsazen. Zvolte jiné datum.")

    # Uložit do DB
    cur = db.execute("""
        INSERT INTO rezervace (jmeno, email, telefon, osoby, datum_od, datum_do, zprava)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (data.jmeno, data.email, data.telefon, data.osoby,
          str(data.datum_od), str(data.datum_do), data.zprava))
    db.commit()

    r = dict(data) | {"id": cur.lastrowid}

    # Odeslat e-maily (async, neblokuje odpověď)
    asyncio.create_task(send_email(NOTIFY_EMAIL, "Nová poptávka – Stenico", email_host_html(r)))
    asyncio.create_task(send_email(data.email, "Vaše poptávka – Apartmán Stenico", email_guest_html(r)))

    return {"ok": True, "id": cur.lastrowid, "message": "Poptávka přijata, brzy se ozveme!"}


# 2. Dostupnost – vrátí obsazené dny pro kalendář
@app.get("/api/dostupnost")
async def dostupnost(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("""
        SELECT datum_od, datum_do FROM rezervace WHERE stav != 'zrusena'
    """).fetchall()
    bloky = db.execute("SELECT datum FROM blokovane_dny").fetchall()

    obsazeno = set()
    for r in rows:
        d = date.fromisoformat(r["datum_od"])
        end = date.fromisoformat(r["datum_do"])
        while d < end:
            obsazeno.add(str(d))
            from datetime import timedelta
            d += timedelta(days=1)
    for b in bloky:
        obsazeno.add(b["datum"])

    return {"obsazeno": sorted(obsazeno)}


# ──────────────────────────────────────────────
# ── ADMIN ENDPOINTS ──
# ──────────────────────────────────────────────

# Admin přihlášení
@app.post("/admin/login")
async def admin_login(heslo: str = Form(...)):
    if hashlib.sha256(heslo.encode()).hexdigest() == ADMIN_PASSWORD:
        resp = RedirectResponse("/admin", status_code=303)
        resp.set_cookie("admin_token", SECRET_TOKEN, httponly=True)
        return resp
    raise HTTPException(401, "Špatné heslo")

@app.get("/admin/logout")
async def admin_logout():
    resp = RedirectResponse("/admin/prihlaseni")
    resp.delete_cookie("admin_token")
    return resp

# Admin přihlašovací stránka
@app.get("/admin/prihlaseni", response_class=HTMLResponse)
async def admin_login_page():
    return HTMLResponse(LOGIN_HTML)

# Admin panel – seznam rezervací
@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request, db: sqlite3.Connection = Depends(get_db)):
    if not is_admin(request):
        return RedirectResponse("/admin/prihlaseni")
    rezervace = db.execute("""
        SELECT * FROM rezervace ORDER BY created_at DESC
    """).fetchall()
    rows_html = ""
    for r in rezervace:
        stav_color = {"nova": "#e8b400", "potvrzena": "#2e7d32", "zrusena": "#c62828"}.get(r["stav"], "#555")
        rows_html += f"""
        <tr>
          <td>{r['id']}</td>
          <td><b>{r['jmeno']}</b><br><small>{r['email']}</small></td>
          <td>{r['telefon'] or '—'}</td>
          <td>{r['osoby']}</td>
          <td>{r['datum_od']}</td>
          <td>{r['datum_do']}</td>
          <td style="color:{stav_color};font-weight:600">{r['stav'].upper()}</td>
          <td>
            <form method="post" action="/admin/rezervace/{r['id']}/stav" style="display:inline">
              <select name="stav" onchange="this.form.submit()" style="padding:4px;font-size:0.8rem">
                <option value="nova" {'selected' if r['stav']=='nova' else ''}>Nová</option>
                <option value="potvrzena" {'selected' if r['stav']=='potvrzena' else ''}>Potvrzena</option>
                <option value="zrusena" {'selected' if r['stav']=='zrusena' else ''}>Zrušena</option>
              </select>
            </form>
          </td>
        </tr>"""
    total = len(rezervace)
    nove = sum(1 for r in rezervace if r["stav"] == "nova")
    potvrzene = sum(1 for r in rezervace if r["stav"] == "potvrzena")
    return HTMLResponse(ADMIN_HTML
        .replace("{{ROWS}}", rows_html)
        .replace("{{TOTAL}}", str(total))
        .replace("{{NOVE}}", str(nove))
        .replace("{{POTVRZENE}}", str(potvrzene))
    )

# Změna stavu rezervace
@app.post("/admin/rezervace/{rez_id}/stav")
async def zmenit_stav(
    rez_id: int,
    request: Request,
    stav: str = Form(...),
    db: sqlite3.Connection = Depends(get_db)
):
    require_admin(request)
    if stav not in ("nova", "potvrzena", "zrusena"):
        raise HTTPException(400, "Neplatný stav")
    db.execute("UPDATE rezervace SET stav=? WHERE id=?", (stav, rez_id))
    db.commit()
    return RedirectResponse("/admin", status_code=303)

# Blokovat den
@app.post("/api/blokovat")
async def blokovat_den(
    request: Request,
    datum: str = Form(...),
    poznamka: str = Form(""),
    db: sqlite3.Connection = Depends(get_db)
):
    require_admin(request)
    db.execute("INSERT OR IGNORE INTO blokovane_dny (datum, poznamka) VALUES (?,?)", (datum, poznamka))
    db.commit()
    return {"ok": True}

# ──────────────────────────────────────────────
# INLINE HTML TEMPLATES (bez externích souborů)
# ──────────────────────────────────────────────
LOGIN_HTML = """<!DOCTYPE html>
<html lang="cs">
<head><meta charset="UTF-8"><title>Admin – Stenico</title>
<style>
  body{font-family:sans-serif;background:#0f1f3d;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}
  .box{background:#fff;padding:2.5rem;width:360px;box-shadow:0 20px 60px rgba(0,0,0,0.4)}
  h2{color:#0f1f3d;margin-bottom:1.5rem;font-size:1.4rem}
  input{width:100%;padding:.8rem;border:1px solid #ddd;margin-bottom:1rem;font-size:1rem;box-sizing:border-box}
  button{width:100%;background:#c9a84c;color:#fff;border:none;padding:.9rem;font-size:1rem;cursor:pointer;font-weight:600}
  button:hover{background:#b8943d}
</style></head>
<body><div class="box">
  <h2>🏔 Apartmán Stenico<br><small style="font-weight:300;font-size:.9rem">Admin panel</small></h2>
  <form method="post" action="/admin/login">
    <input type="password" name="heslo" placeholder="Heslo" autofocus required>
    <button type="submit">Přihlásit se</button>
  </form>
</div></body></html>"""

ADMIN_HTML = """<!DOCTYPE html>
<html lang="cs">
<head><meta charset="UTF-8"><title>Admin – Stenico</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:sans-serif;background:#f4f7fb;color:#222}
  header{background:#0f1f3d;color:#fff;padding:1rem 2rem;display:flex;justify-content:space-between;align-items:center}
  header h1{font-size:1.2rem;color:#c9a84c}
  header a{color:#aac;text-decoration:none;font-size:.85rem}
  .stats{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;padding:1.5rem 2rem}
  .stat{background:#fff;padding:1.2rem 1.5rem;border-top:3px solid #c9a84c;box-shadow:0 2px 8px rgba(0,0,0,.07)}
  .stat .num{font-size:2rem;font-weight:700;color:#0f1f3d}
  .stat .lbl{font-size:.8rem;color:#888;text-transform:uppercase;letter-spacing:.1em}
  .section{padding:0 2rem 2rem}
  .section h2{font-size:1rem;color:#0f1f3d;margin-bottom:1rem;text-transform:uppercase;letter-spacing:.1em}
  table{width:100%;border-collapse:collapse;background:#fff;box-shadow:0 2px 8px rgba(0,0,0,.07)}
  th{background:#0f1f3d;color:#c9a84c;padding:.8rem 1rem;text-align:left;font-size:.75rem;letter-spacing:.1em;text-transform:uppercase}
  td{padding:.8rem 1rem;border-bottom:1px solid #eee;font-size:.88rem;vertical-align:middle}
  tr:hover td{background:#fafbff}
  select{border:1px solid #ddd;border-radius:3px;background:#fff}
</style></head>
<body>
<header>
  <h1>🏔 Apartmán Stenico – Admin</h1>
  <a href="/admin/logout">Odhlásit se</a>
</header>
<div class="stats">
  <div class="stat"><div class="num">{{TOTAL}}</div><div class="lbl">Celkem poptávek</div></div>
  <div class="stat"><div class="num" style="color:#e8b400">{{NOVE}}</div><div class="lbl">Nové</div></div>
  <div class="stat"><div class="num" style="color:#2e7d32">{{POTVRZENE}}</div><div class="lbl">Potvrzené</div></div>
</div>
<div class="section">
  <h2>Rezervace</h2>
  <table>
    <thead><tr>
      <th>#</th><th>Host</th><th>Telefon</th><th>Osob</th>
      <th>Příjezd</th><th>Odjezd</th><th>Stav</th><th>Akce</th>
    </tr></thead>
    <tbody>{{ROWS}}</tbody>
  </table>
</div>
</body></html>"""
