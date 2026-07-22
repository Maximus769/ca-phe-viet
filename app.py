#!/usr/bin/env python3
"""
ANNAM — Backend API
Flask + SQLite/PostgreSQL
Endpoints: orders, leads, admin, email notifications
"""

import os, json, datetime, smtplib, secrets, csv, io
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify, render_template_string, Response, abort
from flask_sqlalchemy import SQLAlchemy

BASE_DIR = Path(__file__).parent
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", f"sqlite:///{BASE_DIR / 'annam.db'}"
).replace("postgres://", "postgresql://")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

ADMIN_KEY   = os.environ.get("ADMIN_KEY", "hv2026admin")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "minhhoangle2909@gmail.com")
SITE_URL    = os.environ.get("SITE_URL", "https://frontend-nine-lyart-63.vercel.app")

PRODUCTS = {
    "PURE_AROMA": {"name": "Pure Aroma",  "price": 32, "origin": "Arabica Cầu Đất · Altitude 1500m"},
    "HIGH_KICK":  {"name": "High Kick",   "price": 28, "origin": "Robusta Đắk Lắk · Hauts Plateaux"},
    "RUM_BLEND":  {"name": "Rum Blend",   "price": 35, "origin": "Arabica + Robusta · Arôme Rhum Naturel"},
}

# ─── MODELS ──────────────────────────────────────────────────────────────────

class PreOrder(db.Model):
    __tablename__ = "pre_orders"
    id         = db.Column(db.Integer, primary_key=True)
    ref        = db.Column(db.String(20), unique=True)
    email      = db.Column(db.String(150), nullable=False)
    sku        = db.Column(db.String(60), nullable=False)
    qty        = db.Column(db.Integer, default=1)
    total      = db.Column(db.Float, default=0)
    status     = db.Column(db.String(30), default="pending")
    note       = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def to_dict(self):
        p = PRODUCTS.get(self.sku, {})
        return {
            "id": self.id, "ref": self.ref, "email": self.email,
            "sku": self.sku, "name": p.get("name", self.sku),
            "qty": self.qty, "total": self.total,
            "status": self.status, "note": self.note,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M"),
        }

class Lead(db.Model):
    __tablename__ = "leads"
    id         = db.Column(db.Integer, primary_key=True)
    email      = db.Column(db.String(150), nullable=False)
    source     = db.Column(db.String(60), default="waitlist")
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "email": self.email,
            "source": self.source,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M"),
        }

# ─── EMAIL ───────────────────────────────────────────────────────────────────

def _smtp():
    user = os.environ.get("GMAIL_USER", "")
    pwd  = os.environ.get("GMAIL_APP_PASSWORD", "")
    return user, pwd

def _send(to: str, subject: str, html: str):
    user, pwd = _smtp()
    if not user or not pwd:
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"ANNAM Café <{user}>"
        msg["To"]      = to
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as s:
            s.login(user, pwd)
            s.sendmail(user, to, msg.as_string())
        return True
    except Exception as e:
        app.logger.warning(f"Email error: {e}")
        return False

def email_order_customer(order: PreOrder):
    p = PRODUCTS.get(order.sku, {})
    html = f"""
<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f5f0eb;font-family:Georgia,serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f0eb;padding:40px 0">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#060402;max-width:600px">

  <!-- HEADER -->
  <tr><td style="background:#0e0805;padding:32px 40px;text-align:center;border-bottom:1px solid #2C1503">
    <p style="margin:0 0 4px;font-size:9px;letter-spacing:.5em;color:#a07850;text-transform:uppercase">Maison de Café Vietnamien</p>
    <h1 style="margin:0;font-size:42px;font-weight:400;letter-spacing:.15em;color:#F5E6C8">ANNAM</h1>
  </td></tr>

  <!-- BODY -->
  <tr><td style="padding:40px 40px 32px">
    <h2 style="color:#F5E6C8;font-size:20px;font-weight:400;margin:0 0 8px">Merci pour votre commande !</h2>
    <p style="color:#9a8070;font-size:14px;margin:0 0 28px;line-height:1.7">
      Votre pré-commande <strong style="color:#c8a87a">{order.ref}</strong> a bien été reçue.<br>
      Nous vous contacterons sous <strong style="color:#F5E6C8">24 heures</strong> pour finaliser le paiement et la livraison.
    </p>

    <!-- ORDER BOX -->
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#1a0e08;border:1px solid #2C1503;margin-bottom:28px">
      <tr><td style="padding:16px 20px;border-bottom:1px solid #2C1503">
        <p style="margin:0;font-size:9px;letter-spacing:.3em;color:#8B5A2B;text-transform:uppercase">Détail de la commande</p>
      </td></tr>
      <tr><td style="padding:16px 20px;border-bottom:1px solid #2C1503">
        <table width="100%"><tr>
          <td style="color:#F5E6C8;font-size:16px">{p.get("name", order.sku)}</td>
          <td style="color:#9a8070;font-size:13px" align="center">× {order.qty}</td>
          <td style="color:#F5E6C8;font-size:16px" align="right">€{order.total:.0f}</td>
        </tr></table>
        <p style="margin:6px 0 0;font-size:11px;color:#6a5040">{p.get("origin","")}</p>
      </td></tr>
      <tr><td style="padding:16px 20px">
        <table width="100%"><tr>
          <td style="color:#c8a87a;font-size:14px">Total</td>
          <td style="color:#F5E6C8;font-size:20px" align="right">€{order.total:.0f}</td>
        </tr></table>
      </td></tr>
    </table>

    <p style="color:#9a8070;font-size:12px;line-height:1.8;margin:0">
      Sachet 250g · TVA 5.5% incluse · Livraison France métropolitaine 5–8 jours ouvrés
    </p>
  </td></tr>

  <!-- FOOTER -->
  <tr><td style="background:#0a0602;padding:20px 40px;text-align:center;border-top:1px solid #1a0e08">
    <p style="margin:0;font-size:10px;color:#4a3020;letter-spacing:.15em">
      ANNAM · contact@annam.fr · <a href="{SITE_URL}" style="color:#6a4020;text-decoration:none">annam.fr</a>
    </p>
  </td></tr>

</table>
</td></tr></table>
</body></html>
"""
    _send(order.email, f"✅ Commande {order.ref} reçue — ANNAM Café", html)

def email_order_admin(order: PreOrder):
    p = PRODUCTS.get(order.sku, {})
    html = f"""
<html><body style="font-family:sans-serif;max-width:600px;margin:auto;padding:20px">
<h2 style="color:#8B5A2B">🛍️ Nouvelle commande ANNAM — {order.ref}</h2>
<table border="1" cellpadding="10" style="border-collapse:collapse;width:100%">
  <tr style="background:#F5E6C8"><th>Champ</th><th>Valeur</th></tr>
  <tr><td><b>Réf</b></td><td><b>{order.ref}</b></td></tr>
  <tr><td>Email client</td><td>{order.email}</td></tr>
  <tr><td>Produit</td><td>{p.get("name","?")} ({order.sku})</td></tr>
  <tr><td>Quantité</td><td>{order.qty}</td></tr>
  <tr><td>Total</td><td><b>€{order.total:.0f}</b></td></tr>
  <tr><td>Date</td><td>{order.created_at.strftime("%d/%m/%Y %H:%M")}</td></tr>
  <tr><td>Statut</td><td>{order.status}</td></tr>
</table>
<p style="margin-top:20px">
  <a href="https://ca-phe-viet.onrender.com/admin?key={ADMIN_KEY}" style="background:#8B5A2B;color:white;padding:10px 20px;text-decoration:none">
    → Voir Admin Dashboard
  </a>
</p>
<p style="color:#666;font-size:12px">ANNAM Backend · {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}</p>
</body></html>
"""
    _send(ADMIN_EMAIL, f"🛍️ Nouvelle commande {order.ref} — {order.email}", html)

def email_lead_admin(lead: Lead):
    html = f"""
<html><body style="font-family:sans-serif;max-width:500px;margin:auto;padding:20px">
<h3 style="color:#8B5A2B">📧 Nouveau lead ANNAM</h3>
<p><b>Email :</b> {lead.email}</p>
<p><b>Source :</b> {lead.source}</p>
<p><b>Date :</b> {lead.created_at.strftime("%d/%m/%Y %H:%M")}</p>
<p><b>Total leads :</b> {Lead.query.count()}</p>
</body></html>
"""
    _send(ADMIN_EMAIL, f"📧 Lead ANNAM : {lead.email}", html)

# ─── CORS ────────────────────────────────────────────────────────────────────

def _cors(resp):
    resp.headers["Access-Control-Allow-Origin"]  = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,PATCH,OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type,X-Admin-Key"
    return resp

@app.after_request
def after(resp):
    return _cors(resp)

@app.route("/", defaults={"path": ""}, methods=["OPTIONS"])
@app.route("/<path:path>", methods=["OPTIONS"])
def options(path):
    return _cors(jsonify({}))

# ─── PUBLIC API ───────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({
        "status": "ok", "brand": "ANNAM",
        "orders": PreOrder.query.count(),
        "leads":  Lead.query.count(),
        "ts": datetime.datetime.utcnow().isoformat(),
    })

@app.route("/api/products")
def api_products():
    return jsonify([
        {"sku": k, "name": v["name"], "price": v["price"], "origin": v["origin"]}
        for k, v in PRODUCTS.items()
    ])

@app.route("/leads", methods=["POST"])
def api_leads():
    data  = request.get_json(force=True, silent=True) or {}
    email = data.get("email", "").strip().lower()
    if not email or "@" not in email:
        return jsonify({"error": "email invalide"}), 400
    lead = Lead(email=email, source=data.get("source", "waitlist"))
    db.session.add(lead)
    db.session.commit()
    # Notify admin (async-ish: ignore failure)
    try: email_lead_admin(lead)
    except: pass
    return jsonify({"ok": True, "id": lead.id, "count": Lead.query.count()})

@app.route("/leads/count")
def api_leads_count():
    return jsonify({"count": Lead.query.count()})

@app.route("/orders", methods=["POST"])
def api_orders():
    data  = request.get_json(force=True, silent=True) or {}
    email = data.get("email", "").strip().lower()
    sku   = data.get("sku", "").strip().upper()
    qty   = max(1, int(data.get("qty", 1)))

    if not email or "@" not in email:
        return jsonify({"error": "email invalide"}), 400
    if sku not in PRODUCTS:
        return jsonify({"error": f"sku inconnu: {sku}"}), 400

    price = PRODUCTS[sku]["price"]
    total = price * qty
    ref   = f"ANNAM-{datetime.datetime.utcnow().strftime('%m%d')}-{PreOrder.query.count()+1:03d}"

    order = PreOrder(email=email, sku=sku, qty=qty, total=total, ref=ref, status="pending")
    db.session.add(order)
    db.session.commit()

    # Emails
    try: email_order_customer(order)
    except: pass
    try: email_order_admin(order)
    except: pass

    return jsonify({"ok": True, "ref": ref, "total": total})

# ─── ADMIN API ───────────────────────────────────────────────────────────────

def _require_admin():
    key = request.headers.get("X-Admin-Key") or request.args.get("key", "")
    if key != ADMIN_KEY:
        abort(403)

@app.route("/admin/orders")
def admin_orders_api():
    _require_admin()
    status = request.args.get("status")
    q = PreOrder.query.order_by(PreOrder.created_at.desc())
    if status:
        q = q.filter_by(status=status)
    return jsonify([o.to_dict() for o in q.limit(200).all()])

@app.route("/admin/orders/<int:oid>", methods=["PATCH"])
def admin_order_update(oid):
    _require_admin()
    order = PreOrder.query.get_or_404(oid)
    data  = request.get_json(force=True, silent=True) or {}
    if "status" in data and data["status"] in ("pending","confirmed","shipped","delivered","cancelled"):
        order.status = data["status"]
    if "note" in data:
        order.note = data["note"]
    db.session.commit()
    return jsonify(order.to_dict())

@app.route("/admin/leads")
def admin_leads_api():
    _require_admin()
    leads = Lead.query.order_by(Lead.created_at.desc()).limit(500).all()
    return jsonify([l.to_dict() for l in leads])

@app.route("/admin/leads/export")
def admin_leads_export():
    _require_admin()
    leads = Lead.query.order_by(Lead.created_at.desc()).all()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["id", "email", "source", "created_at"])
    for l in leads:
        w.writerow([l.id, l.email, l.source, l.created_at.strftime("%Y-%m-%d %H:%M")])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment;filename=annam_leads.csv"})

@app.route("/admin/stats")
def admin_stats():
    _require_admin()
    total_orders  = PreOrder.query.count()
    total_revenue = db.session.query(db.func.sum(PreOrder.total)).filter_by(status="confirmed").scalar() or 0
    pending       = PreOrder.query.filter_by(status="pending").count()
    confirmed     = PreOrder.query.filter_by(status="confirmed").count()
    total_leads   = Lead.query.count()
    return jsonify({
        "orders": {"total": total_orders, "pending": pending, "confirmed": confirmed},
        "revenue_confirmed": total_revenue,
        "leads": total_leads,
        "conversion_rate": f"{confirmed/total_leads*100:.1f}%" if total_leads else "0%",
    })

# ─── ADMIN DASHBOARD HTML ────────────────────────────────────────────────────

ADMIN_HTML = """<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ANNAM — Admin</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#060402;color:#F5E6C8;font-family:Georgia,serif;min-height:100vh}
header{background:#0e0805;border-bottom:1px solid #2C1503;padding:16px 32px;display:flex;align-items:center;justify-content:space-between}
header h1{font-size:20px;letter-spacing:.15em;font-weight:400}
header span{font-size:10px;color:#a07850;letter-spacing:.3em}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px;padding:32px;border-bottom:1px solid #1a0e08}
.stat{background:#1a0e08;border:1px solid #2C1503;padding:20px 24px}
.stat-val{font-size:32px;font-weight:300;color:#F5E6C8;margin-bottom:4px}
.stat-label{font-size:10px;color:#a07850;letter-spacing:.2em;text-transform:uppercase}
.tabs{display:flex;border-bottom:1px solid #1a0e08;padding:0 32px}
.tab{padding:14px 20px;font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:#9a8070;cursor:pointer;border-bottom:2px solid transparent;background:none;border-top:none;border-left:none;border-right:none;font-family:Georgia,serif}
.tab.active{color:#c8a87a;border-bottom-color:#8B5A2B}
.content{padding:24px 32px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{font-size:9px;letter-spacing:.3em;color:#8B5A2B;text-transform:uppercase;text-align:left;padding:10px 14px;border-bottom:1px solid #2C1503;font-weight:normal}
td{padding:12px 14px;border-bottom:1px solid #0e0804;color:#9a8070}
td:first-child{color:#F5E6C8}
tr:hover td{background:#0e0804}
.badge{display:inline-block;padding:3px 10px;font-size:10px;letter-spacing:.1em;border:1px solid}
.badge.pending{color:#c8a87a;border-color:#8a6020}
.badge.confirmed{color:#7ab85a;border-color:#3a7020}
.badge.shipped{color:#60a0c8;border-color:#205080}
.badge.cancelled{color:#c06060;border-color:#802020}
.badge.delivered{color:#a07850;border-color:#604020}
select{background:#0e0805;border:1px solid #2C1503;color:#F5E6C8;padding:6px 10px;font-family:Georgia,serif;cursor:pointer}
.export-btn{background:#2C1503;border:1px solid #8B5A2B;color:#c8a87a;padding:8px 20px;font-size:10px;letter-spacing:.2em;text-transform:uppercase;cursor:pointer;text-decoration:none;font-family:Georgia,serif}
.loading{color:#6a5040;font-size:13px;padding:40px;text-align:center}
.refresh-btn{background:none;border:1px solid #2C1503;color:#9a8070;padding:8px 16px;font-size:10px;letter-spacing:.15em;cursor:pointer;font-family:Georgia,serif}
</style>
</head>
<body>
<header>
  <div>
    <h1>ANNAM</h1>
    <span>Admin Dashboard</span>
  </div>
  <button class="refresh-btn" onclick="loadAll()">↻ Rafraîchir</button>
</header>

<div class="stats" id="stats">
  <div class="stat"><div class="stat-val" id="s-orders">…</div><div class="stat-label">Commandes</div></div>
  <div class="stat"><div class="stat-val" id="s-pending">…</div><div class="stat-label">En attente</div></div>
  <div class="stat"><div class="stat-val" id="s-confirmed">…</div><div class="stat-label">Confirmées</div></div>
  <div class="stat"><div class="stat-val" id="s-revenue">…</div><div class="stat-label">Revenue confirmé</div></div>
  <div class="stat"><div class="stat-val" id="s-leads">…</div><div class="stat-label">Leads waitlist</div></div>
  <div class="stat"><div class="stat-val" id="s-conv">…</div><div class="stat-label">Taux conversion</div></div>
</div>

<div class="tabs">
  <button class="tab active" onclick="showTab('orders',this)">Commandes</button>
  <button class="tab" onclick="showTab('leads',this)">Leads Waitlist</button>
</div>

<div class="content">
  <!-- ORDERS -->
  <div id="tab-orders">
    <div style="display:flex;align-items:center;gap:16px;margin-bottom:20px">
      <select id="filter-status" onchange="loadOrders()">
        <option value="">Tous les statuts</option>
        <option value="pending">En attente</option>
        <option value="confirmed">Confirmées</option>
        <option value="shipped">Expédiées</option>
        <option value="delivered">Livrées</option>
        <option value="cancelled">Annulées</option>
      </select>
    </div>
    <div id="orders-table"><p class="loading">Chargement…</p></div>
  </div>

  <!-- LEADS -->
  <div id="tab-leads" style="display:none">
    <div style="margin-bottom:16px">
      <a href="?key={{KEY}}&export=leads" class="export-btn">↓ Exporter CSV</a>
    </div>
    <div id="leads-table"><p class="loading">Chargement…</p></div>
  </div>
</div>

<script>
const KEY = new URLSearchParams(location.search).get("key") || "";
const BASE = "";

function showTab(name, el) {
  document.querySelectorAll(".tab").forEach(t=>t.classList.remove("active"));
  el.classList.add("active");
  document.querySelectorAll("[id^=tab-]").forEach(t=>t.style.display="none");
  document.getElementById("tab-"+name).style.display="block";
  if(name==="leads") loadLeads();
}

async function api(path) {
  const r = await fetch(BASE+path, {headers:{"X-Admin-Key":KEY}});
  if(!r.ok) throw new Error(r.status);
  return r.json();
}

async function loadStats() {
  try {
    const s = await api("/admin/stats");
    document.getElementById("s-orders").textContent    = s.orders.total;
    document.getElementById("s-pending").textContent   = s.orders.pending;
    document.getElementById("s-confirmed").textContent = s.orders.confirmed;
    document.getElementById("s-revenue").textContent   = "€"+s.revenue_confirmed;
    document.getElementById("s-leads").textContent     = s.leads;
    document.getElementById("s-conv").textContent      = s.conversion_rate;
  } catch(e) { console.error(e); }
}

const STATUSES = ["pending","confirmed","shipped","delivered","cancelled"];

async function loadOrders() {
  const status = document.getElementById("filter-status").value;
  const el = document.getElementById("orders-table");
  el.innerHTML = '<p class="loading">Chargement…</p>';
  try {
    const orders = await api("/admin/orders"+(status?"?status="+status:""));
    if(!orders.length){ el.innerHTML='<p class="loading">Aucune commande.</p>'; return; }
    el.innerHTML = `<table>
      <tr><th>Réf</th><th>Email</th><th>Produit</th><th>Qté</th><th>Total</th><th>Statut</th><th>Date</th><th>Action</th></tr>
      ${orders.map(o=>`<tr>
        <td>${o.ref}</td>
        <td>${o.email}</td>
        <td>${o.name}</td>
        <td>${o.qty}</td>
        <td>€${o.total}</td>
        <td><span class="badge ${o.status}">${o.status}</span></td>
        <td>${o.created_at}</td>
        <td>
          <select onchange="updateOrder(${o.id},this.value)" style="font-size:11px;padding:4px 8px">
            ${STATUSES.map(s=>`<option value="${s}"${s===o.status?" selected":""}>${s}</option>`).join("")}
          </select>
        </td>
      </tr>`).join("")}
    </table>`;
  } catch(e) { el.innerHTML=`<p class="loading" style="color:#c06060">Erreur: ${e.message}</p>`; }
}

async function updateOrder(id, status) {
  try {
    await fetch(BASE+"/admin/orders/"+id, {
      method:"PATCH",
      headers:{"Content-Type":"application/json","X-Admin-Key":KEY},
      body:JSON.stringify({status})
    });
    setTimeout(loadStats, 300);
  } catch(e) { alert("Erreur: "+e.message); }
}

async function loadLeads() {
  const el = document.getElementById("leads-table");
  el.innerHTML = '<p class="loading">Chargement…</p>';
  try {
    const leads = await api("/admin/leads");
    document.getElementById("tab-leads").querySelector("a").href =
      `/admin/leads/export?key=${KEY}`;
    if(!leads.length){ el.innerHTML='<p class="loading">Aucun lead.</p>'; return; }
    el.innerHTML = `<table>
      <tr><th>#</th><th>Email</th><th>Source</th><th>Date</th></tr>
      ${leads.map(l=>`<tr>
        <td>${l.id}</td>
        <td>${l.email}</td>
        <td>${l.source}</td>
        <td>${l.created_at}</td>
      </tr>`).join("")}
    </table>`;
  } catch(e) { el.innerHTML=`<p class="loading" style="color:#c06060">Erreur: ${e.message}</p>`; }
}

async function loadAll() { await loadStats(); await loadOrders(); }
loadAll();
setInterval(loadAll, 30000);
</script>
</body></html>
"""

@app.route("/admin")
def admin_dashboard():
    key = request.args.get("key", "")
    if key != ADMIN_KEY:
        return """<html><body style="background:#060402;color:#F5E6C8;font-family:Georgia,serif;display:flex;align-items:center;justify-content:center;height:100vh;flex-direction:column">
        <h2 style="font-size:24px;font-weight:400;margin-bottom:20px;letter-spacing:.1em">ANNAM · Admin</h2>
        <form method="get" style="display:flex;gap:0">
          <input name="key" type="password" placeholder="Clé admin" style="background:#0e0805;border:1px solid #2C1503;color:#F5E6C8;padding:12px 16px;font-size:14px;border-right:none">
          <button type="submit" style="background:#8B5A2B;border:1px solid #8B5A2B;color:#F5E6C8;padding:12px 20px;cursor:pointer;font-family:Georgia,serif">Accéder</button>
        </form>
        </body></html>""", 403
    html = ADMIN_HTML.replace("{{KEY}}", key)
    return render_template_string(html)

# ─── INIT ────────────────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
