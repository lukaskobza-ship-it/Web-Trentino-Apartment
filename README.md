# Apartmán Stenico – Backend

## Požadavky
- Python 3.10+
- Gmail účet s povoleným "App Password"

## Instalace

```bash
# 1. Nainstalujte závislosti
pip install -r requirements.txt

# 2. Nastavte konfiguraci v main.py
#    Otevřete main.py a upravte sekci CONFIG:
SMTP_USER      = "vas-email@gmail.com"
SMTP_PASSWORD  = "xxxx xxxx xxxx xxxx"   # Gmail App Password
NOTIFY_EMAIL   = "vlastnik@email.cz"
ADMIN_PASSWORD = hashlib.sha256(b"vase-heslo").hexdigest()

# 3. Spusťte server
uvicorn main:app --reload --port 8000
```

## Jak získat Gmail App Password
1. Jděte na myaccount.google.com → Bezpečnost
2. Zapněte "Dvoufázové ověření"
3. Hledejte "Hesla aplikací" → vygenerujte heslo
4. Toto heslo vložte do SMTP_PASSWORD

## Endpointy

| Metoda | URL | Popis |
|--------|-----|-------|
| POST | `/api/poptavka` | Odeslání poptávky z formuláře |
| GET | `/api/dostupnost` | Obsazené dny pro kalendář |
| GET | `/admin` | Admin panel (vyžaduje přihlášení) |
| POST | `/admin/login` | Přihlášení do adminu |
| GET | `/admin/logout` | Odhlášení |
| POST | `/admin/rezervace/{id}/stav` | Změna stavu rezervace |

## Propojení s frontendem

V souboru `stenico-apartman.html` nahraďte funkci `submitForm`:

```javascript
async function submitForm(e) {
  e.preventDefault();
  const btn = document.querySelector('.form-submit');
  btn.textContent = 'Odesílám...';
  btn.disabled = true;

  const payload = {
    jmeno:    document.getElementById('jmeno').value,
    email:    document.getElementById('email').value,
    telefon:  document.getElementById('telefon').value,
    osoby:    parseInt(document.getElementById('osoby').value),
    datum_od: document.getElementById('od').value,
    datum_do: document.getElementById('do').value,
    zprava:   document.getElementById('zprava').value,
  };

  try {
    const res = await fetch('http://localhost:8000/api/poptavka', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (res.ok) {
      document.getElementById('successMsg').style.display = 'block';
      document.getElementById('contactForm').reset();
    } else {
      alert('Chyba: ' + data.detail);
    }
  } catch (err) {
    alert('Server není dostupný. Zkuste to znovu.');
  } finally {
    btn.textContent = 'Odeslat poptávku';
    btn.disabled = false;
  }
}
```

A přidejte načítání kalendáře dostupnosti:

```javascript
async function loadDostupnost() {
  const res = await fetch('http://localhost:8000/api/dostupnost');
  const data = await res.json();
  // data.obsazeno = ["2025-01-03", "2025-01-04", ...]
  // Použijte pro obarvení kalendáře
}
loadDostupnost();
```

## Struktura databáze

```
stenico.db
├── rezervace       – poptávky z formuláře
└── blokovane_dny   – ručně blokované dny
```

## Produkční nasazení

Pro nasazení na server doporučuji:
- **Hosting**: DigitalOcean, Hetzner, nebo Railway.app
- **Process manager**: `systemd` nebo `supervisor`
- **Reverse proxy**: Nginx před uvicornem
- **HTTPS**: Let's Encrypt (certbot)

```bash
# Spuštění v produkci
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
```
