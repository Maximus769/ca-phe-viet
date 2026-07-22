#!/usr/bin/env python3
"""
ANNAM — Backend API
Flask + SQLite/PostgreSQL + Stripe Checkout
"""

import os, datetime, secrets, csv, io
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string, Response, abort, redirect
from flask_sqlalchemy import SQLAlchemy
import resend
import stripe

BASE_DIR = Path(__file__).parent
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", f"sqlite:///{BASE_DIR / 'annam.db'}"
).replace("postgres://", "postgresql://")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

ADMIN_KEY        = os.environ.get("ADMIN_KEY", "hv2026admin")
ADMIN_EMAIL      = os.environ.get("ADMIN_EMAIL", "minhhoangle2909@gmail.com")
SITE_URL         = os.environ.get("SITE_URL", "https://frontend-nine-lyart-63.vercel.app")
resend.api_key   = os.environ.get("RESEND_API_KEY", "")
stripe.api_key   = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK   = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

PRODUCTS = {
    "PURE_AROMA": {"name": "Pure Aroma",  "price": 32, "price_cents": 3200, "origin": "Arabica Cầu Đất · Altitude 1500m"},
    "HIGH_KICK":  {"name": "High Kick",   "price": 28, "price_cents": 2800, "origin": "Robusta Đắk Lắk · Hauts Plateaux"},
    "RUM_BLEND":  {"name": "Rum Blend",   "price": 35, "price_cents": 3500, "origin": "Arabica + Robusta · Arôme Rhum Naturel"},
}

# ─── MODELS ──────────────────────────────────────────────────────────────────

class Order(db.Model):
    __tablename__ = "orders"
    id                = db.Column(db.Integer, primary_key=True)
    ref               = db.Column(db.String(30), unique=True)
    email             = db.Column(db.String(150), nullable=False)
    items_json        = db.Column(db.Text, default="[]")
    total             = db.Column(db.Float, default=0)
    status            = db.Column(db.String(30), default="pending")  # pending|paid|shipped|delivered|cancelled
    stripe_session_id = db.Column(db.String(120))
    note              = db.Column(db.Text, default="")
    created_at        = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    paid_at           = db.Column(db.DateTime, nullable=True)

    def items(self):
        import json
        return json.loads(self.items_json or "[]")

    def to_dict(self):
        return {
            "id": self.id, "ref": self.ref, "email": self.email,
            "items": self.items(), "total": self.total,
            "status": self.status, "note": self.note,
            "stripe_session_id": self.stripe_session_id,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M"),
            "paid_at": self.paid_at.strftime("%Y-%m-%d %H:%M") if self.paid_at else None,
        }

class Lead(db.Model):
    __tablename__ = "leads"
    id         = db.Column(db.Integer, primary_key=True)
    email      = db.Column(db.String(150), nullable=False)
    source     = db.Column(db.String(60), default="waitlist")
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "email": self.email, "source": self.source,
                "created_at": self.created_at.strftime("%Y-%m-%d %H:%M")}

# ─── EMAIL ───────────────────────────────────────────────────────────────────

FROM = "ANNAM Café <onboarding@resend.dev>"

def _send(to, subject, html):
    if not resend.api_key:
        return
    try:
        resend.Emails.send({"from": FROM, "to": [to], "subject": subject, "html": html})
    except Exception as e:
        app.logger.warning(f"Email error: {e}")

def email_paid(order: Order):
    rows = "".join(
        f"<tr><td style='padding:10px 14px;color:#9a8070'>{i['name']}</td>"
        f"<td style='padding:10px 14px;color:#9a8070;text-align:center'>× {i['qty']}</td>"
        f"<td style='padding:10px 14px;color:#F5E6C8;text-align:right'>€{i['price']*i['qty']}</td></tr>"
        for i in order.items()
    )
    html = f"""<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f5f0eb;font-family:Georgia,serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f0eb;padding:40px 0">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#060402;max-width:600px">
  <tr><td style="background:#0e0805;padding:28px 40px;text-align:center;border-bottom:1px solid #2C1503">
    <p style="margin:0 0 4px;font-size:9px;letter-spacing:.5em;color:#a07850;text-transform:uppercase">Maison de Café Vietnamien</p>
    <h1 style="margin:0;font-size:40px;font-weight:400;letter-spacing:.15em;color:#F5E6C8">ANNAM</h1>
  </td></tr>
  <tr><td style="padding:36px 40px">
    <h2 style="color:#F5E6C8;font-size:18px;font-weight:400;margin:0 0 6px">Paiement confirmé ✓</h2>
    <p style="color:#9a8070;font-size:14px;margin:0 0 28px;line-height:1.7">
      Votre commande <strong style="color:#c8a87a">{order.ref}</strong> a été payée avec succès.<br>
      Livraison sous <strong style="color:#F5E6C8">5–8 jours ouvrés</strong> en France.
    </p>
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#1a0e08;border:1px solid #2C1503;margin-bottom:24px">
      <tr><td colspan="3" style="padding:12px 14px;border-bottom:1px solid #2C1503">
        <p style="margin:0;font-size:9px;letter-spacing:.3em;color:#8B5A2B;text-transform:uppercase">Détail de la commande</p>
      </td></tr>
      {rows}
      <tr style="border-top:1px solid #2C1503">
        <td colspan="2" style="padding:12px 14px;color:#c8a87a;font-size:14px">Total payé</td>
        <td style="padding:12px 14px;color:#F5E6C8;font-size:20px;text-align:right">€{order.total:.0f}</td>
      </tr>
    </table>
    <p style="color:#6a5040;font-size:12px;line-height:1.8;margin:0">
      Référence : {order.ref}<br>
      Sachet 250g · TVA 5.5% incluse · Livraison France métropolitaine
    </p>
  </td></tr>
  <tr><td style="background:#0a0602;padding:18px 40px;text-align:center;border-top:1px solid #1a0e08">
    <p style="margin:0;font-size:10px;color:#3a2010;letter-spacing:.1em">ANNAM · contact@annam.fr</p>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""
    _send(order.email, f"✅ Commande {order.ref} payée — ANNAM Café", html)

def email_admin_order(order: Order):
    items_txt = ", ".join(f"{i['name']} ×{i['qty']}" for i in order.items())
    html = f"""<html><body style="font-family:sans-serif;max-width:600px;margin:auto;padding:20px">
<h2 style="color:#8B5A2B">💳 Paiement reçu — {order.ref}</h2>
<table border="1" cellpadding="10" style="border-collapse:collapse;width:100%">
  <tr style="background:#F5E6C8"><th>Champ</th><th>Valeur</th></tr>
  <tr><td><b>Réf</b></td><td><b>{order.ref}</b></td></tr>
  <tr><td>Email</td><td>{order.email}</td></tr>
  <tr><td>Articles</td><td>{items_txt}</td></tr>
  <tr><td>Total</td><td><b>€{order.total:.0f}</b></td></tr>
  <tr><td>Statut</td><td style="color:green"><b>PAYÉ ✓</b></td></tr>
  <tr><td>Date</td><td>{order.created_at.strftime("%d/%m/%Y %H:%M")}</td></tr>
</table>
<p style="margin-top:16px">
  <a href="https://ca-phe-viet.onrender.com/admin?key={ADMIN_KEY}"
     style="background:#8B5A2B;color:white;padding:10px 20px;text-decoration:none;display:inline-block">
    → Admin Dashboard
  </a>
  <a href="https://dashboard.stripe.com/payments"
     style="background:#635BFF;color:white;padding:10px 20px;text-decoration:none;display:inline-block;margin-left:8px">
    → Stripe Dashboard
  </a>
</p>
</body></html>"""
    _send(ADMIN_EMAIL, f"💳 Paiement {order.ref} — €{order.total:.0f} — {order.email}", html)

def email_lead_admin(lead: Lead):
    _send(ADMIN_EMAIL, f"📧 Nouveau lead ANNAM : {lead.email}",
          f"<p><b>Email :</b> {lead.email}<br><b>Source :</b> {lead.source}<br><b>Total leads :</b> {Lead.query.count()}</p>")

# ─── CORS ────────────────────────────────────────────────────────────────────

@app.after_request
def cors(resp):
    resp.headers["Access-Control-Allow-Origin"]  = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,PATCH,OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type,X-Admin-Key,Stripe-Signature"
    return resp

@app.route("/", defaults={"p": ""}, methods=["OPTIONS"])
@app.route("/<path:p>", methods=["OPTIONS"])
def options(p): return jsonify({})

# ─── PUBLIC ──────────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({
        "status": "ok", "brand": "ANNAM",
        "stripe": bool(stripe.api_key),
        "orders": Order.query.count(),
        "leads": Lead.query.count(),
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
    try: email_lead_admin(lead)
    except: pass
    return jsonify({"ok": True, "id": lead.id, "count": Lead.query.count()})

@app.route("/leads/count")
def leads_count():
    return jsonify({"count": Lead.query.count()})

# ─── STRIPE CHECKOUT ─────────────────────────────────────────────────────────

@app.route("/create-checkout-session", methods=["POST"])
def create_checkout():
    if not stripe.api_key:
        return jsonify({"error": "Stripe non configuré"}), 503

    data  = request.get_json(force=True, silent=True) or {}
    items = data.get("items", [])   # [{sku, qty}, ...]
    email = data.get("email", "")

    if not items:
        return jsonify({"error": "Panier vide"}), 400

    # Build line items for Stripe
    line_items = []
    total = 0
    order_items = []
    for item in items:
        sku  = item.get("sku", "").upper()
        qty  = max(1, int(item.get("qty", 1)))
        prod = PRODUCTS.get(sku)
        if not prod:
            return jsonify({"error": f"Produit inconnu: {sku}"}), 400
        line_items.append({
            "price_data": {
                "currency": "eur",
                "unit_amount": prod["price_cents"],
                "product_data": {
                    "name": f"ANNAM — {prod['name']}",
                    "description": prod["origin"] + " · Sachet 250g",
                    "images": [f"{SITE_URL}/images/{sku.lower()}.jpg"],
                },
            },
            "quantity": qty,
        })
        total += prod["price"] * qty
        order_items.append({"sku": sku, "name": prod["name"], "price": prod["price"], "qty": qty})

    # Create order in DB (pending)
    import json
    ref = f"ANNAM-{datetime.datetime.utcnow().strftime('%m%d')}-{Order.query.count()+1:04d}"
    order = Order(ref=ref, email=email, items_json=json.dumps(order_items), total=total, status="pending")
    db.session.add(order)
    db.session.commit()

    # Create Stripe session
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=line_items,
            mode="payment",
            customer_email=email or None,
            success_url=f"{SITE_URL}/success?ref={ref}&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{SITE_URL}/?cancelled=1",
            metadata={"order_ref": ref, "order_id": str(order.id)},
            shipping_address_collection={"allowed_countries": ["FR", "BE", "CH", "LU"]},
            shipping_options=[
                {
                    "shipping_rate_data": {
                        "type": "fixed_amount",
                        "fixed_amount": {"amount": 0, "currency": "eur"},
                        "display_name": "Livraison standard France",
                        "delivery_estimate": {
                            "minimum": {"unit": "business_day", "value": 5},
                            "maximum": {"unit": "business_day", "value": 8},
                        },
                    }
                }
            ],
            locale="fr",
        )
        # Save session ID
        order.stripe_session_id = session.id
        db.session.commit()
        return jsonify({"url": session.url, "ref": ref})
    except stripe.error.StripeError as e:
        app.logger.error(f"Stripe error: {e}")
        return jsonify({"error": str(e)}), 500

# ─── STRIPE WEBHOOK ──────────────────────────────────────────────────────────

@app.route("/webhook/stripe", methods=["POST"])
def stripe_webhook():
    payload = request.get_data()
    sig     = request.headers.get("Stripe-Signature", "")

    try:
        if STRIPE_WEBHOOK:
            event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK)
        else:
            import json
            event = json.loads(payload)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    if event["type"] == "checkout.session.completed":
        session  = event["data"]["object"]
        ref      = session.get("metadata", {}).get("order_ref")
        order    = Order.query.filter_by(ref=ref).first() if ref else None
        if order and order.status == "pending":
            order.status  = "paid"
            order.paid_at = datetime.datetime.utcnow()
            db.session.commit()
            try: email_paid(order)
            except: pass
            try: email_admin_order(order)
            except: pass

    return jsonify({"ok": True})

# ─── ADMIN API ───────────────────────────────────────────────────────────────

def _auth():
    key = request.headers.get("X-Admin-Key") or request.args.get("key", "")
    if key != ADMIN_KEY:
        abort(403)

@app.route("/admin/orders")
def admin_orders():
    _auth()
    status = request.args.get("status")
    q = Order.query.order_by(Order.created_at.desc())
    if status: q = q.filter_by(status=status)
    return jsonify([o.to_dict() for o in q.limit(300).all()])

@app.route("/admin/orders/<int:oid>", methods=["PATCH"])
def admin_order_patch(oid):
    _auth()
    order = Order.query.get_or_404(oid)
    data  = request.get_json(force=True, silent=True) or {}
    if "status" in data:
        order.status = data["status"]
    if "note" in data:
        order.note = data["note"]
    db.session.commit()
    return jsonify(order.to_dict())

@app.route("/admin/leads")
def admin_leads():
    _auth()
    return jsonify([l.to_dict() for l in Lead.query.order_by(Lead.created_at.desc()).limit(500).all()])

@app.route("/admin/leads/export")
def admin_leads_export():
    _auth()
    out = io.StringIO()
    w   = csv.writer(out)
    w.writerow(["id","email","source","created_at"])
    for l in Lead.query.order_by(Lead.created_at.desc()).all():
        w.writerow([l.id, l.email, l.source, l.created_at.strftime("%Y-%m-%d %H:%M")])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment;filename=annam_leads.csv"})

@app.route("/admin/stats")
def admin_stats():
    _auth()
    paid_revenue = db.session.query(db.func.sum(Order.total)).filter_by(status="paid").scalar() or 0
    return jsonify({
        "orders": {
            "total":     Order.query.count(),
            "pending":   Order.query.filter_by(status="pending").count(),
            "paid":      Order.query.filter_by(status="paid").count(),
            "shipped":   Order.query.filter_by(status="shipped").count(),
        },
        "revenue_paid": paid_revenue,
        "leads": Lead.query.count(),
        "stripe_live": bool(stripe.api_key and "live" in stripe.api_key),
    })

# ─── ADMIN DASHBOARD ─────────────────────────────────────────────────────────

ADMIN_HTML = """<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ANNAM Admin</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#060402;color:#F5E6C8;font-family:Georgia,serif;min-height:100vh}
header{background:#0e0805;border-bottom:1px solid #2C1503;padding:0 32px;height:56px;display:flex;align-items:center;justify-content:space-between}
header h1{font-size:18px;letter-spacing:.15em;font-weight:400}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;padding:24px 32px;border-bottom:1px solid #100806}
.stat{background:#1a0e08;border:1px solid #2C1503;padding:18px 20px}
.stat-val{font-size:30px;font-weight:300;margin-bottom:2px}
.stat-label{font-size:9px;color:#a07850;letter-spacing:.2em;text-transform:uppercase}
.stat-val.green{color:#7ab85a}.stat-val.amber{color:#c8a87a}.stat-val.blue{color:#60a8c8}
.tabs{display:flex;padding:0 32px;border-bottom:1px solid #100806}
.tab{padding:14px 18px;font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:#6a5040;cursor:pointer;background:none;border:none;border-bottom:2px solid transparent;font-family:Georgia,serif;transition:color .2s}
.tab.on{color:#c8a87a;border-bottom-color:#8B5A2B}
.content{padding:20px 32px}
table{width:100%;border-collapse:collapse;font-size:12px}
th{font-size:8px;letter-spacing:.3em;color:#6a4020;text-transform:uppercase;text-align:left;padding:8px 12px;border-bottom:1px solid #200e04;font-weight:normal}
td{padding:10px 12px;border-bottom:1px solid #0e0602;color:#9a8070;vertical-align:middle}
td:first-child{color:#F5E6C8}tr:hover td{background:#0e0602}
.badge{display:inline-block;padding:2px 8px;font-size:9px;letter-spacing:.08em;border:1px solid}
.badge.pending{color:#c8a87a;border-color:#8a6020}
.badge.paid{color:#7ab85a;border-color:#3a7020}
.badge.shipped{color:#60a8c8;border-color:#205080}
.badge.delivered{color:#a07850;border-color:#604020}
.badge.cancelled{color:#c06060;border-color:#802020}
select{background:#0e0805;border:1px solid #2C1503;color:#F5E6C8;padding:5px 8px;font-family:Georgia,serif;font-size:11px;cursor:pointer}
.btn{display:inline-block;padding:7px 16px;font-size:9px;letter-spacing:.2em;text-transform:uppercase;cursor:pointer;text-decoration:none;font-family:Georgia,serif;border:1px solid}
.btn-amber{background:#2C1503;border-color:#8B5A2B;color:#c8a87a}
.btn-green{background:#0a2010;border-color:#3a7020;color:#7ab85a}
.empty{color:#3a2010;font-size:13px;padding:40px;text-align:center}
.toolbar{display:flex;align-items:center;gap:12px;margin-bottom:16px;flex-wrap:wrap}
</style>
</head>
<body>
<header>
  <h1>ANNAM · Admin</h1>
  <div style="display:flex;gap:10px;align-items:center">
    <span id="stripe-badge" style="font-size:9px;letter-spacing:.2em;color:#6a5040"></span>
    <button class="btn btn-amber" onclick="loadAll()">↻</button>
  </div>
</header>

<div class="stats">
  <div class="stat"><div class="stat-val green" id="s-paid">—</div><div class="stat-label">Commandes payées</div></div>
  <div class="stat"><div class="stat-val amber" id="s-pending">—</div><div class="stat-label">En attente</div></div>
  <div class="stat"><div class="stat-val blue" id="s-shipped">—</div><div class="stat-label">Expédiées</div></div>
  <div class="stat"><div class="stat-val" id="s-revenue">—</div><div class="stat-label">Revenue</div></div>
  <div class="stat"><div class="stat-val" id="s-leads">—</div><div class="stat-label">Leads waitlist</div></div>
</div>

<div class="tabs">
  <button class="tab on" onclick="tab('orders',this)">Commandes</button>
  <button class="tab" onclick="tab('leads',this)">Leads</button>
</div>

<div class="content">
  <div id="pane-orders">
    <div class="toolbar">
      <select id="fstatus" onchange="loadOrders()">
        <option value="">Tous</option>
        <option value="pending">En attente</option>
        <option value="paid">Payées</option>
        <option value="shipped">Expédiées</option>
        <option value="delivered">Livrées</option>
        <option value="cancelled">Annulées</option>
      </select>
    </div>
    <div id="orders-body"><p class="empty">Chargement…</p></div>
  </div>
  <div id="pane-leads" style="display:none">
    <div class="toolbar">
      <a class="btn btn-amber" id="export-link" href="#">↓ Export CSV</a>
    </div>
    <div id="leads-body"><p class="empty">Chargement…</p></div>
  </div>
</div>

<script>
const KEY  = new URLSearchParams(location.search).get("key")||"";
const H    = {"X-Admin-Key":KEY};
const STAT = ["pending","paid","shipped","delivered","cancelled"];

function tab(name,el){
  document.querySelectorAll(".tab").forEach(t=>t.classList.remove("on"));
  el.classList.add("on");
  document.querySelectorAll("[id^=pane-]").forEach(p=>p.style.display="none");
  document.getElementById("pane-"+name).style.display="";
  if(name==="leads") loadLeads();
}

async function get(path){
  const r=await fetch(path,{headers:H});
  if(!r.ok) throw new Error(r.status);
  return r.json();
}

async function loadStats(){
  const s=await get("/admin/stats");
  document.getElementById("s-paid").textContent    = s.orders.paid;
  document.getElementById("s-pending").textContent = s.orders.pending;
  document.getElementById("s-shipped").textContent = s.orders.shipped;
  document.getElementById("s-revenue").textContent = "€"+s.revenue_paid;
  document.getElementById("s-leads").textContent   = s.leads;
  document.getElementById("stripe-badge").textContent = s.stripe_live ? "STRIPE LIVE ●" : "STRIPE TEST ●";
  document.getElementById("stripe-badge").style.color = s.stripe_live ? "#7ab85a" : "#c8a87a";
}

async function loadOrders(){
  const status=document.getElementById("fstatus").value;
  const el=document.getElementById("orders-body");
  el.innerHTML="<p class='empty'>Chargement…</p>";
  const orders=await get("/admin/orders"+(status?"?status="+status:""));
  if(!orders.length){el.innerHTML="<p class='empty'>Aucune commande.</p>";return;}
  el.innerHTML=`<table>
    <tr><th>Réf</th><th>Email</th><th>Articles</th><th>Total</th><th>Statut</th><th>Date</th><th>Action</th></tr>
    ${orders.map(o=>`<tr>
      <td>${o.ref}</td>
      <td>${o.email}</td>
      <td>${o.items.map(i=>i.name+"×"+i.qty).join(", ")}</td>
      <td>€${o.total}</td>
      <td><span class="badge ${o.status}">${o.status}</span></td>
      <td>${o.created_at}</td>
      <td>
        <select onchange="patch(${o.id},this.value)">
          ${STAT.map(s=>`<option${s===o.status?" selected":""}>${s}</option>`).join("")}
        </select>
      </td>
    </tr>`).join("")}
  </table>`;
}

async function patch(id,status){
  await fetch("/admin/orders/"+id,{method:"PATCH",headers:{...H,"Content-Type":"application/json"},body:JSON.stringify({status})});
  setTimeout(loadStats,400);
}

async function loadLeads(){
  document.getElementById("export-link").href="/admin/leads/export?key="+KEY;
  const el=document.getElementById("leads-body");
  el.innerHTML="<p class='empty'>Chargement…</p>";
  const leads=await get("/admin/leads");
  if(!leads.length){el.innerHTML="<p class='empty'>Aucun lead.</p>";return;}
  el.innerHTML=`<table>
    <tr><th>#</th><th>Email</th><th>Source</th><th>Date</th></tr>
    ${leads.map(l=>`<tr><td>${l.id}</td><td>${l.email}</td><td>${l.source}</td><td>${l.created_at}</td></tr>`).join("")}
  </table>`;
}

async function loadAll(){await loadStats();await loadOrders();}
loadAll();
setInterval(loadAll,30000);
</script>
</body></html>"""

@app.route("/admin")
def admin():
    key = request.args.get("key","")
    if key != ADMIN_KEY:
        return """<html><body style="background:#060402;color:#F5E6C8;font-family:Georgia,serif;display:flex;align-items:center;justify-content:center;height:100vh;flex-direction:column;gap:20px">
        <h1 style="font-size:28px;font-weight:400;letter-spacing:.15em">ANNAM</h1>
        <form method="get" style="display:flex">
          <input name="key" type="password" placeholder="Clé admin"
            style="background:#0e0805;border:1px solid #2C1503;color:#F5E6C8;padding:12px 16px;font-size:14px;border-right:none;font-family:Georgia,serif">
          <button type="submit"
            style="background:#8B5A2B;border:none;color:#F5E6C8;padding:12px 20px;cursor:pointer;font-family:Georgia,serif">Accéder</button>
        </form></body></html>""", 403
    return render_template_string(ADMIN_HTML.replace("{{KEY}}", key))

# ─── INIT ────────────────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
