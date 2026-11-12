import os
import sqlite3
import uuid
import hmac
from functools import wraps

from flask import Flask, request, jsonify, send_from_directory, Response

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "shop.db")
STATIC_DIR = os.path.join(BASE, "static")
PRIVATE_DIR = os.path.join(BASE, "private")
UPLOAD_DIR = os.path.join(STATIC_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "1234")
ALLOWED_EXT = {"jpg", "jpeg", "png", "webp", "gif"}

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # max 5MB


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def setup_db():
    conn = get_db()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            stock INTEGER DEFAULT 0,
            image TEXT
        )"""
    )
    conn.commit()
    conn.close()


setup_db()


# ---------- password lock ----------
def admin_only(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.authorization
        if auth and hmac.compare_digest(auth.password or "", ADMIN_PASSWORD):
            return f(*args, **kwargs)
        return Response(
            "Password dao", 401, {"WWW-Authenticate": 'Basic realm="Admin"'}
        )

    return wrapper


# ---------- pic save/delete ----------
def save_image(file):
    if not file or not file.filename:
        return None
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXT:
        return None
    name = uuid.uuid4().hex + "." + ext
    file.save(os.path.join(UPLOAD_DIR, name))
    return "/static/uploads/" + name


def delete_image(path):
    if not path:
        return
    full = os.path.join(UPLOAD_DIR, os.path.basename(path))
    if os.path.exists(full):
        os.remove(full)


# ---------- pages ----------
@app.route("/")
def home():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/admin")
@admin_only
def admin():
    return send_from_directory(PRIVATE_DIR, "admin.html")


# ---------- API ----------
@app.route("/api/products", methods=["GET"])
def list_products():
    conn = get_db()
    rows = conn.execute("SELECT * FROM products ORDER BY id").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/products", methods=["POST"])
@admin_only
def add_product():
    name = request.form.get("name", "").strip()
    try:
        price = float(request.form.get("price", ""))
        stock = int(request.form.get("stock") or 0)
    except ValueError:
        return jsonify({"error": "Dam ba stock thik na"}), 400
    if not name:
        return jsonify({"error": "Naam dao"}), 400

    image = save_image(request.files.get("image"))
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO products (name, price, stock, image) VALUES (?, ?, ?, ?)",
        (name, price, stock, image),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return jsonify({"id": new_id})


@app.route("/api/products/<int:pid>", methods=["PUT"])
@admin_only
def update_product(pid):
    name = request.form.get("name", "").strip()
    try:
        price = float(request.form.get("price", ""))
        stock = int(request.form.get("stock") or 0)
    except ValueError:
        return jsonify({"error": "Dam ba stock thik na"}), 400
    if not name:
        return jsonify({"error": "Naam dao"}), 400

    conn = get_db()
    old = conn.execute("SELECT image FROM products WHERE id=?", (pid,)).fetchone()
    if old is None:
        conn.close()
        return jsonify({"error": "Product pawa jay ni"}), 404

    new_image = save_image(request.files.get("image"))
    if new_image:
        delete_image(old["image"])
        image = new_image
    else:
        image = old["image"]

    conn.execute(
        "UPDATE products SET name=?, price=?, stock=?, image=? WHERE id=?",
        (name, price, stock, image, pid),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/products/<int:pid>", methods=["DELETE"])
@admin_only
def delete_product(pid):
    conn = get_db()
    old = conn.execute("SELECT image FROM products WHERE id=?", (pid,)).fetchone()
    if old:
        delete_image(old["image"])
    conn.execute("DELETE FROM products WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True)