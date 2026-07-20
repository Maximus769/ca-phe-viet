#!/usr/bin/env python3
"""
Cà Phê Việt — Web Shop
Flask app: product catalog, cart, orders, customer DB, chatbot, email confirm
"""

import os, json, datetime, smtplib, hashlib, secrets
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import (Flask, render_template, request, redirect, url_for,
                   session, jsonify, flash, abort)
from flask_sqlalchemy import SQLAlchemy

BASE_DIR = Path(__file__).parent
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"]   = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", f"sqlite:///{BASE_DIR / 'shop.db'}"
).replace("postgres://", "postgresql://")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ─── MODELS ──────────────────────────────────────────────────────────────────

class Product(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(120), nullable=False)
    name_fr     = db.Column(db.String(120))
    description = db.Column(db.Text)
    price       = db.Column(db.Float, nullable=False)
    stock       = db.Column(db.Integer, default=100)
    image       = db.Column(db.String(200))
    category    = db.Column(db.String(60))
    active      = db.Column(db.Boolean, default=True)

class Customer(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    email      = db.Column(db.String(150), unique=True, nullable=False)
    name       = db.Column(db.String(120))
    phone      = db.Column(db.String(30))
    address    = db.Column(db.Text)
    city       = db.Column(db.String(80))
    country    = db.Column(db.String(60), default="France")
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    orders     = db.relationship("Order", backref="customer", lazy=True)

class Order(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    ref         = db.Column(db.String(20), unique=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    total       = db.Column(db.Float)
    status      = db.Column(db.String(30), default="pending")
    note        = db.Column(db.Text)
    created_at  = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    items       = db.relationship("OrderItem", backref="order", lazy=True)

class OrderItem(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    order_id   = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    qty        = db.Column(db.Integer, default=1)
    price      = db.Column(db.Float)
    product    = db.relationship("Product")

class Review(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    author     = db.Column(db.String(80))
    email      = db.Column(db.String(150))
    rating     = db.Column(db.Integer, default=5)
    comment    = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    product    = db.relationship("Product")

# ─── EMAIL ───────────────────────────────────────────────────────────────────

def _email_cfg():
    cfg = {}
    p = Path.home() / ".hv_email_config"
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    return cfg

def send_order_confirmation(order: Order):
    cfg  = _email_cfg()
    user = cfg.get("GMAIL_USER", "")
    pwd  = cfg.get("GMAIL_APP_PASSWORD", "")
    if not user or not pwd:
        return
    c   = order.customer
    rows = "".join(
        f"<tr><td>{i.product.name}</td><td>{i.qty}</td><td>€{i.price:.2f}</td></tr>"
        for i in order.items
    )
    html = f"""<html><body style='font-family:sans-serif;max-width:600px;margin:auto'>
<div style='background:#4A2C17;padding:20px;text-align:center'>
  <h1 style='color:#D4A847;margin:0'>Cà Phê Việt</h1>
  <p style='color:#F5ECD7;margin:4px 0'>Robusta Đắk Lắk • Torréfié à la main</p>
</div>
<div style='padding:24px'>
  <h2 style='color:#4A2C17'>Merci pour votre commande, {c.name}!</h2>
  <p>Votre commande <strong>{order.ref}</strong> a été reçue et est en cours de traitement.</p>
  <table border='1' cellpadding='8' style='border-collapse:collapse;width:100%'>
    <tr style='background:#F5ECD7'><th>Produit</th><th>Qté</th><th>Prix</th></tr>
    {rows}
    <tr style='background:#F5ECD7'><td colspan='2'><strong>Total</strong></td><td><strong>€{order.total:.2f}</strong></td></tr>
  </table>
  <p style='color:#666;margin-top:20px'>Livraison sous 5-7 jours ouvrables.<br>
  Adresse: {c.address}, {c.city}, {c.country}</p>
</div>
<div style='background:#F5ECD7;padding:12px;text-align:center'>
  <p style='color:#4A2C17;font-size:12px;margin:0'>Cà Phê Việt — Du Vietnam à votre tasse ☕</p>
</div>
</body></html>"""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"✅ Commande {order.ref} confirmée — Cà Phê Việt"
        msg["From"]    = user
        msg["To"]      = c.email
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(user, pwd)
            s.sendmail(user, c.email, msg.as_string())
    except Exception:
        pass

def send_review_notification(review: Review):
    cfg  = _email_cfg()
    user = cfg.get("GMAIL_USER", "")
    pwd  = cfg.get("GMAIL_APP_PASSWORD", "")
    to   = os.environ.get("ADMIN_EMAIL", "minhhoangle2909@gmail.com")
    if not user or not pwd:
        return
    html = f"""<html><body style='font-family:sans-serif'>
<h3>⭐ Nouvel avis — {review.product.name}</h3>
<p><b>{review.author}</b> ({review.email}) — {'⭐'*review.rating}</p>
<blockquote style='background:#F5ECD7;padding:12px;border-left:4px solid #D4A847'>
  {review.comment}
</blockquote>
<p><a href='/admin/reviews'>Voir tous les avis →</a></p>
</body></html>"""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[Cà Phê Việt] Nouvel avis ⭐{review.rating} — {review.product.name}"
        msg["From"]    = user
        msg["To"]      = to
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(user, pwd)
            s.sendmail(user, to, msg.as_string())
    except Exception:
        pass

# ─── CART HELPERS ─────────────────────────────────────────────────────────────

def get_cart():
    return session.get("cart", {})

def cart_total():
    cart = get_cart()
    total = 0.0
    for pid, item in cart.items():
        p = db.session.get(Product, int(pid))
        if p:
            total += p.price * item["qty"]
    return total

def cart_count():
    return sum(v["qty"] for v in get_cart().values())

app.jinja_env.globals.update(cart_count=cart_count, cart_total=cart_total)

# ─── ROUTES — PUBLIC ─────────────────────────────────────────────────────────

@app.route("/")
def index():
    products = Product.query.filter_by(active=True).limit(6).all()
    return render_template("index.html", products=products)

@app.route("/products")
def products():
    cat  = request.args.get("cat", "")
    q    = request.args.get("q",   "")
    qs   = Product.query.filter_by(active=True)
    if cat:
        qs = qs.filter_by(category=cat)
    if q:
        qs = qs.filter(Product.name.ilike(f"%{q}%"))
    prods = qs.all()
    cats  = db.session.query(Product.category).distinct().all()
    return render_template("products.html", products=prods, cats=[c[0] for c in cats],
                           selected_cat=cat, q=q)

@app.route("/product/<int:pid>")
def product_detail(pid):
    p       = Product.query.get_or_404(pid)
    reviews = Review.query.filter_by(product_id=pid).order_by(Review.created_at.desc()).all()
    avg     = round(sum(r.rating for r in reviews) / len(reviews), 1) if reviews else 0
    return render_template("product.html", product=p, reviews=reviews, avg=avg)

@app.route("/about")
def about():
    return render_template("about.html")

# ─── CART ────────────────────────────────────────────────────────────────────

@app.route("/cart")
def cart():
    items = []
    for pid, data in get_cart().items():
        p = db.session.get(Product, int(pid))
        if p:
            items.append({"product": p, "qty": data["qty"],
                          "subtotal": p.price * data["qty"]})
    return render_template("cart.html", items=items, total=cart_total())

@app.route("/cart/add/<int:pid>", methods=["POST"])
def cart_add(pid):
    qty  = int(request.form.get("qty", 1))
    cart = get_cart()
    key  = str(pid)
    cart[key] = {"qty": cart.get(key, {}).get("qty", 0) + qty}
    session["cart"] = cart
    session.modified = True
    flash("Ajouté au panier ✓", "success")
    return redirect(url_for("cart"))

@app.route("/cart/remove/<int:pid>")
def cart_remove(pid):
    cart = get_cart()
    cart.pop(str(pid), None)
    session["cart"] = cart
    return redirect(url_for("cart"))

@app.route("/cart/update", methods=["POST"])
def cart_update():
    cart = get_cart()
    for pid, qty in request.form.items():
        if pid.isdigit():
            if int(qty) <= 0:
                cart.pop(pid, None)
            else:
                cart[pid] = {"qty": int(qty)}
    session["cart"] = cart
    return redirect(url_for("cart"))

# ─── CHECKOUT ────────────────────────────────────────────────────────────────

@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    if not get_cart():
        return redirect(url_for("cart"))
    if request.method == "POST":
        f    = request.form
        cust = Customer.query.filter_by(email=f["email"]).first()
        if not cust:
            cust = Customer(email=f["email"], name=f["name"],
                            phone=f.get("phone",""), address=f["address"],
                            city=f["city"], country=f.get("country","France"))
            db.session.add(cust)
            db.session.flush()
        else:
            cust.name    = f["name"]
            cust.address = f["address"]
            cust.city    = f["city"]

        ref   = "CPV" + datetime.datetime.now().strftime("%y%m%d%H%M%S")
        order = Order(ref=ref, customer_id=cust.id,
                      total=cart_total(), note=f.get("note",""))
        db.session.add(order)
        db.session.flush()

        for pid, data in get_cart().items():
            p = db.session.get(Product, int(pid))
            if p:
                db.session.add(OrderItem(order_id=order.id, product_id=p.id,
                                         qty=data["qty"], price=p.price))
                p.stock = max(0, p.stock - data["qty"])

        db.session.commit()
        session["cart"] = {}
        send_order_confirmation(order)
        return redirect(url_for("order_success", ref=ref))

    return render_template("checkout.html", total=cart_total())

@app.route("/order/<ref>")
def order_success(ref):
    order = Order.query.filter_by(ref=ref).first_or_404()
    return render_template("order_success.html", order=order)

# ─── REVIEWS ─────────────────────────────────────────────────────────────────

@app.route("/review/<int:pid>", methods=["POST"])
def add_review(pid):
    p = Product.query.get_or_404(pid)
    r = Review(product_id=pid,
               author=request.form.get("author","Anonyme"),
               email=request.form.get("email",""),
               rating=int(request.form.get("rating", 5)),
               comment=request.form.get("comment",""))
    db.session.add(r)
    db.session.commit()
    send_review_notification(r)
    flash("Merci pour votre avis!", "success")
    return redirect(url_for("product_detail", pid=pid))

# ─── CHATBOT API ─────────────────────────────────────────────────────────────

@app.route("/api/chat", methods=["POST"])
def chat():
    msg = request.json.get("message", "").strip()
    if not msg:
        return jsonify({"reply": "Bonjour! Comment puis-je vous aider?"})

    products_info = "\n".join(
        f"- {p.name}: €{p.price:.2f} — {p.description or ''}"
        for p in Product.query.filter_by(active=True).all()
    )
    system = f"""Tu es l'assistant de Cà Phê Việt, une boutique de café vietnamien premium vendu en France.
Nos produits: {products_info}
Réponds en français (ou en vietnamien si le client écrit en vietnamien), sois chaleureux, concis.
Pour commander: dirige vers /products. Pour questions livraison: 5-7 jours, gratuit >€40."""

    try:
        import urllib.request as ur, json as j
        base = os.environ.get("OPENCLAW_URL", "http://localhost:3000")
        oai_key = os.environ.get("OPENAI_API_KEY", "")

        if oai_key:
            payload = j.dumps({"model":"gpt-4o-mini","messages":[
                {"role":"system","content":system},
                {"role":"user","content":msg}
            ],"max_tokens":300}).encode()
            req = ur.Request("https://api.openai.com/v1/chat/completions",
                             data=payload,
                             headers={"Authorization":f"Bearer {oai_key}",
                                      "Content-Type":"application/json"})
            resp = j.loads(ur.urlopen(req, timeout=15).read())
            reply = resp["choices"][0]["message"]["content"]
        else:
            # Fallback: Ollama local
            payload = j.dumps({"model":"qwen2.5:7b","prompt":f"{system}\n\nUser: {msg}\nAssistant:","stream":False}).encode()
            req = ur.Request("http://localhost:11434/api/generate",data=payload,
                             headers={"Content-Type":"application/json"})
            resp = j.loads(ur.urlopen(req,timeout=20).read())
            reply = resp.get("response","Désolé, service temporairement indisponible.")
    except Exception as e:
        reply = "Désolé, notre assistant est temporairement indisponible. Contactez-nous à caopheviet@gmail.com"

    return jsonify({"reply": reply})

# ─── ADMIN ───────────────────────────────────────────────────────────────────

ADMIN_KEY = os.environ.get("ADMIN_KEY", "hv2026admin")

def admin_required():
    if session.get("admin") != ADMIN_KEY:
        abort(401)

@app.route("/admin", methods=["GET","POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("key") == ADMIN_KEY:
            session["admin"] = ADMIN_KEY
            return redirect(url_for("admin_dashboard"))
        flash("Clé incorrecte", "error")
    return render_template("admin_login.html")

@app.route("/admin/dashboard")
def admin_dashboard():
    admin_required()
    orders    = Order.query.order_by(Order.created_at.desc()).limit(20).all()
    customers = Customer.query.count()
    revenue   = db.session.query(db.func.sum(Order.total)).filter_by(status="confirmed").scalar() or 0
    return render_template("admin_dashboard.html", orders=orders,
                           customers=customers, revenue=revenue)

@app.route("/admin/order/<int:oid>/status", methods=["POST"])
def admin_order_status(oid):
    admin_required()
    order = Order.query.get_or_404(oid)
    order.status = request.form["status"]
    db.session.commit()
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/reviews")
def admin_reviews():
    admin_required()
    reviews = Review.query.order_by(Review.created_at.desc()).all()
    return render_template("admin_reviews.html", reviews=reviews)

# ─── SEED DATA ───────────────────────────────────────────────────────────────

def seed_products():
    if Product.query.count() > 0:
        return
    prods = [
        Product(name="Robusta Đắk Lắk — Rang Xay 500g",
                name_fr="Robusta Dak Lak Torréfié 500g",
                description="Café robusta de montagne, torréfié artisanalement. Saveur intense, corsée, légèrement chocolatée. Idéal pour le phin et l'espresso.",
                price=18.0, stock=50, image="/static/images/M1-A.jpg", category="rang-xay"),
        Product(name="Kit Phin Truyền Thống",
                name_fr="Kit Filtre Phin Traditionnel",
                description="Filtre phin aluminium authentique + 200g café robusta + 1 boîte lait concentré Vinamilk. Expérience café vietnamien complète.",
                price=24.0, stock=30, image="/static/images/p2.jpg", category="kit"),
        Product(name="Cà Phê Hòa Tan 3in1 — Hộp 20 gói",
                name_fr="Café Instantané 3en1 — Boîte 20 sachets",
                description="Café instantané vietnamien avec sucre et lait concentré. Prêt en 30 secondes, goût authentique. Parfait pour le bureau.",
                price=12.0, stock=80, image="/static/images/p3.jpg", category="hoa-tan"),
        Product(name="Robusta Nguyên Hạt 1kg",
                name_fr="Robusta en Grains 1kg",
                description="Grains de robusta entiers, torréfaction artisanale médium. Pour les amateurs qui souhaitent moudre eux-mêmes.",
                price=32.0, stock=25, image="/static/images/M1-A.jpg", category="rang-xay"),
        Product(name="Cà Phê Sữa Đá — Hộp 12 lon",
                name_fr="Café Glacé au Lait — Pack 12 canettes",
                description="Cà phê sữa đá style vietnamien, prêt à consommer. Recette authentique avec robusta Đắk Lắk.",
                price=28.0, stock=40, image="/static/images/p3.jpg", category="ready-to-drink"),
    ]
    db.session.add_all(prods)
    db.session.commit()

# ─── MAIN ────────────────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()
    seed_products()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
