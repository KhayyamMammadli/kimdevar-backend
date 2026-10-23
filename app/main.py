"""KimdəVar pilot API. Demo identities must be enabled explicitly for testing."""

import hashlib
import io
import json
import os
import re
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from PIL import Image, UnidentifiedImageError
from . import db
from .schemas import (
    DemoLogin,
    Profile,
    RequestInput,
    RequestStatus,
    OfferInput,
    StoreInput,
    MessageInput,
    ConversationInput,
    ReportInput,
    AnalyzeInput,
)

DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "data/uploads"))
bearer = HTTPBearer(auto_error=False)


def uid():
    return uuid4().hex


def now():
    return datetime.now(timezone.utc).isoformat()


def fail(code, text):
    raise HTTPException(code, text)


def one(conn, sql, args=()):
    result = conn.execute(sql, args).fetchone()
    if not result:
        fail(404, "Məlumat tapılmadı")
    return dict(result)


def rows(conn, sql, args=()):
    return [dict(x) for x in conn.execute(sql, args).fetchall()]


def notify(conn, user, title, body, target="", kind="offer"):
    conn.execute(
        "INSERT INTO notifications VALUES(?,?,?,?,?,?,0,?)",
        (uid(), user, title, body, target, kind, now()),
    )


def store_dict(s):
    s["categories"] = json.loads(s["categories"])
    s["verified"] = bool(s["verified"])
    return s


def seed():
    with db.connect() as c:
        for id_, name, role in [
            ("demo-buyer", "Xəyyam", "buyer"),
            ("demo-seller", "MobileFix sahibi", "seller"),
            ("demo-admin", "Moderator", "admin"),
            ("seed-owner", "Telefon Dünyası sahibi", "seller"),
        ]:
            c.execute(
                "INSERT OR IGNORE INTO users(id,name,role) VALUES(?,?,?)",
                (id_, name, role),
            )
        for id_, owner, name in [
            ("mobilefix", "demo-seller", "MobileFix"),
            ("telefon-dunyasi", "seed-owner", "Telefon Dünyası"),
        ]:
            c.execute(
                "INSERT OR IGNORE INTO stores(id,owner_id,name,district,address,categories,verified) VALUES(?,?,?,?,?,?,1)",
                (
                    id_,
                    owner,
                    name,
                    "Xətai",
                    "Əhmədli metrosu yaxınlığı",
                    json.dumps(["Ekran", "Batareya", "Arxa qapaq", "Digər"]),
                ),
            )
        # Seed only once; never resurrect a deleted/closed request on restart.
        c.execute(
            "CREATE TABLE IF NOT EXISTS seed_versions(version INTEGER PRIMARY KEY)"
        )
        if c.execute("SELECT 1 FROM seed_versions WHERE version=1").fetchone():
            return
        c.execute("INSERT INTO seed_versions VALUES(1)")
        c.execute(
            "INSERT INTO requests VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "demo-request",
                "demo-buyer",
                "Samsung A52 ekranı",
                "Samsung",
                "Galaxy A52",
                "Ekran",
                120,
                "Xətai",
                "Bu gün",
                "Fərq etmir",
                "Quraşdırma ilə qiymət təklif edin.",
                None,
                "active",
                now(),
            ),
        )
        for id_, store, price in [
            ("demo-offer", "mobilefix", 95),
            ("demo-offer-2", "telefon-dunyasi", 110),
        ]:
            c.execute(
                "INSERT INTO offers VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    id_,
                    "demo-request",
                    store,
                    price,
                    "Uyğun alternativ",
                    "Yeni",
                    "Stokda var",
                    10,
                    1,
                    30,
                    "Modeli gəlməzdən əvvəl dəqiqləşdirin.",
                    (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
                    now(),
                    "active",
                ),
            )


@asynccontextmanager
async def lifespan(app):
    db.init()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    if DEMO_MODE:
        seed()
    yield


app = FastAPI(title="KimdəVar API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        x.strip()
        for x in os.getenv(
            "CORS_ORIGINS", "http://localhost:8081,http://localhost:19006"
        ).split(",")
        if x.strip()
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


def user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if not credentials:
        fail(401, "Daxil olmaq lazımdır")
    digest = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    with db.connect() as c:
        row = c.execute(
            "SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token_hash=? AND s.expires_at>?",
            (digest, int(time.time())),
        ).fetchone()
        if not row:
            fail(401, "Sessiya bitib. Yenidən daxil ol.")
        return dict(row)


def admin(u=Depends(user)):
    if u["role"] != "admin":
        fail(403, "Administrator icazəsi lazımdır")
    return u


def seller_store(c, u):
    if u["role"] != "seller":
        fail(403, "Mağaza hesabı lazımdır")
    return one(c, "SELECT * FROM stores WHERE owner_id=?", (u["id"],))


def request_access(c, id_, u):
    r = one(c, "SELECT * FROM requests WHERE id=?", (id_,))
    if u["role"] == "admin" or r["buyer_id"] == u["id"]:
        return r
    if u["role"] == "seller":
        s = seller_store(c, u)
        if (
            s["verified"]
            and s["district"] == r["district"]
            and r["part"] in json.loads(s["categories"])
        ):
            return r
        if c.execute(
            "SELECT 1 FROM offers WHERE request_id=? AND store_id=?", (id_, s["id"])
        ).fetchone():
            return r
    fail(403, "Bu sorğuya giriş yoxdur")


def conversation_access(c, id_, u):
    conv = one(
        c,
        "SELECT c.*,s.owner_id,s.name store_name,u.name buyer_name FROM conversations c JOIN stores s ON s.id=c.store_id JOIN users u ON u.id=c.buyer_id WHERE c.id=?",
        (id_,),
    )
    if u["id"] not in [conv["buyer_id"], conv["owner_id"]]:
        fail(403, "Bu yazışmaya giriş yoxdur")
    return conv


@app.get("/health")
def health():
    return {
        "status": "ok",
        "database": "sqlite",
        "demo_mode": DEMO_MODE,
        "ai_provider": "rules-demo",
    }


@app.post("/auth/demo")
def demo_login(data: DemoLogin):
    if not DEMO_MODE:
        fail(404, "Demo giriş deaktivdir")
    token = secrets.token_urlsafe(40)
    with db.connect() as c:
        u = one(c, "SELECT * FROM users WHERE id=?", ("demo-" + data.role,))
        c.execute("DELETE FROM sessions WHERE expires_at<=?", (int(time.time()),))
        c.execute(
            "INSERT INTO sessions VALUES(?,?,?)",
            (
                hashlib.sha256(token.encode()).hexdigest(),
                u["id"],
                int(time.time()) + 86400,
            ),
        )
    return {"token": token, "user": u, "expires_in": 86400, "demo": True}


@app.post("/auth/logout")
def logout(
    credentials: HTTPAuthorizationCredentials = Depends(bearer), u=Depends(user)
):
    with db.connect() as c:
        c.execute(
            "DELETE FROM sessions WHERE token_hash=?",
            (hashlib.sha256(credentials.credentials.encode()).hexdigest(),),
        )
    return {"ok": True}


@app.get("/me")
def me(u=Depends(user)):
    return u


@app.patch("/me")
def update_me(data: Profile, u=Depends(user)):
    with db.connect() as c:
        c.execute(
            "UPDATE users SET name=?,phone=?,district=? WHERE id=?",
            (data.name, data.phone, data.district, u["id"]),
        )
        return one(c, "SELECT * FROM users WHERE id=?", (u["id"],))


@app.delete("/me")
def delete_me(u=Depends(user)):
    with db.connect() as c:
        files = rows(c, "SELECT filename FROM uploads WHERE owner_id=?", (u["id"],))
        c.execute("DELETE FROM users WHERE id=?", (u["id"],))
    for f in files:
        (UPLOAD_DIR / f["filename"]).unlink(missing_ok=True)
    return {"ok": True}


@app.post("/ai/analyze")
def analyze(data: AnalyzeInput, u=Depends(user)):
    text = data.text.lower()
    brand = next(
        (
            b
            for b in ["Samsung", "Apple", "Xiaomi", "Huawei", "Honor"]
            if b.lower() in text
        ),
        "",
    )
    if "iphone" in text:
        brand = "Apple"
    part = next(
        (
            p
            for keys, p in [
                (["ekran", "screen", "şüşə"], "Ekran"),
                (["batareya", "battery"], "Batareya"),
                (["qapaq"], "Arxa qapaq"),
            ]
            if any(k in text for k in keys)
        ),
        "Digər",
    )
    model = re.search(
        r"(?:iphone\s*\d{1,2}(?:\s*pro(?:\s*max)?)?|(?:galaxy\s*)?[as]\d{2}(?:\s*ultra)?|redmi\s*(?:note\s*)?\d+)",
        text,
    )
    budget = re.search(r"(\d+(?:\.\d+)?)\s*(?:₼|azn|manat)", text)
    district = next(
        (
            d
            for d in ["Xətai", "Nərimanov", "Yasamal", "Nəsimi", "Binəqədi"]
            if d.lower() in text
        ),
        "Xətai",
    )
    return {
        "brand": brand,
        "model": model.group(0).title() if model else "",
        "part": part,
        "budget": float(budget.group(1)) if budget else 0,
        "district": district,
        "provider": "rules-demo",
        "requires_confirmation": True,
        "questions": [
            "Telefonun model kodunu yoxla.",
            "Hissənin növünü və büdcəni təsdiqlə.",
        ],
        "notice": "Bu versiya qayda əsaslı demo köməkçidir; real AI və şəkil tanıma bağlı deyil.",
    }


@app.post("/uploads")
async def upload(file: UploadFile = File(...), u=Depends(user)):
    content = await file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        fail(413, "Şəkil maksimum 5 MB ola bilər")
    try:
        with Image.open(io.BytesIO(content)) as im:
            if im.width * im.height > 20_000_000:
                fail(400, "Şəkil ölçüsü çox böyükdür")
            im = im.convert("RGB")
            im.thumbnail((1600, 1600))
            filename = uid() + ".jpg"
            im.save(UPLOAD_DIR / filename, "JPEG", quality=85)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        fail(400, "Düzgün şəkil faylı seç")
    id_ = uid()
    with db.connect() as c:
        c.execute("INSERT INTO uploads VALUES(?,?,?)", (id_, u["id"], filename))
    return {"id": id_}


@app.get("/uploads/{id_}")
def get_upload(id_: str, u=Depends(user)):
    with db.connect() as c:
        item = one(c, "SELECT * FROM uploads WHERE id=?", (id_,))
        if item["owner_id"] != u["id"]:
            req = one(c, "SELECT id FROM requests WHERE image_id=?", (id_,))
            request_access(c, req["id"], u)
    return FileResponse(UPLOAD_DIR / item["filename"], media_type="image/jpeg")


@app.post("/requests", status_code=201)
def create_request(data: RequestInput, u=Depends(user)):
    if u["role"] != "buyer":
        fail(403, "Alıcı hesabı lazımdır")
    id_ = uid()
    with db.connect() as c:
        if data.image_id:
            image = one(c, "SELECT * FROM uploads WHERE id=?", (data.image_id,))
            if image["owner_id"] != u["id"]:
                fail(403, "Bu şəkil sənə aid deyil")
        values = data.model_dump()
        c.execute(
            "INSERT INTO requests(id,buyer_id,title,brand,model,part,budget,district,urgency,quality,note,image_id,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                id_,
                u["id"],
                *[
                    values[k]
                    for k in [
                        "title",
                        "brand",
                        "model",
                        "part",
                        "budget",
                        "district",
                        "urgency",
                        "quality",
                        "note",
                        "image_id",
                    ]
                ],
                "active",
                now(),
            ),
        )
        for s in rows(
            c, "SELECT * FROM stores WHERE verified=1 AND district=?", (data.district,)
        ):
            if data.part in json.loads(s["categories"]):
                notify(c, s["owner_id"], "Yeni uyğun sorğu", data.title, id_, "request")
        return one(c, "SELECT * FROM requests WHERE id=?", (id_,))


@app.get("/requests")
def list_requests(u=Depends(user)):
    with db.connect() as c:
        if u["role"] == "buyer":
            return rows(
                c,
                "SELECT r.*,(SELECT count(*) FROM offers o WHERE o.request_id=r.id AND o.status='active' AND o.expires_at>?) offer_count FROM requests r WHERE buyer_id=? ORDER BY created_at DESC",
                (now(), u["id"]),
            )
        if u["role"] == "admin":
            return rows(c, "SELECT * FROM requests ORDER BY created_at DESC LIMIT 200")
        s = seller_store(c, u)
        if not s["verified"]:
            return []
        return [
            r
            for r in rows(
                c,
                "SELECT * FROM requests WHERE status='active' AND district=? ORDER BY created_at DESC",
                (s["district"],),
            )
            if r["part"] in json.loads(s["categories"])
        ]


@app.get("/requests/{id_}")
def get_request(id_: str, u=Depends(user)):
    with db.connect() as c:
        return request_access(c, id_, u)


@app.patch("/requests/{id_}")
def set_status(id_: str, data: RequestStatus, u=Depends(user)):
    with db.connect() as c:
        r = one(c, "SELECT * FROM requests WHERE id=?", (id_,))
        if r["buyer_id"] != u["id"]:
            fail(403, "Yalnız sorğu sahibi dəyişə bilər")
        c.execute("UPDATE requests SET status=? WHERE id=?", (data.status, id_))
        return one(c, "SELECT * FROM requests WHERE id=?", (id_,))


@app.get("/requests/{id_}/offers")
def list_offers(id_: str, u=Depends(user)):
    with db.connect() as c:
        r = request_access(c, id_, u)
        if r["buyer_id"] != u["id"] and u["role"] != "admin":
            fail(403, "Təklifləri yalnız alıcı görə bilər")
        return rows(
            c,
            "SELECT o.*,s.name store_name,s.district,s.verified FROM offers o JOIN stores s ON s.id=o.store_id WHERE request_id=? AND o.status='active' AND o.expires_at>? ORDER BY o.price",
            (id_, now()),
        )


@app.post("/requests/{id_}/offers", status_code=201)
def upsert_offer(id_: str, data: OfferInput, u=Depends(user)):
    with db.connect() as c:
        s = seller_store(c, u)
        r = request_access(c, id_, u)
        if not s["verified"]:
            fail(403, "Mağaza təsdiqlənməlidir")
        if r["status"] != "active":
            fail(409, "Sorğu artıq aktiv deyil")
        if r["district"] != s["district"] or r["part"] not in json.loads(
            s["categories"]
        ):
            fail(403, "Uyğun olmayan sorğu")
        existing = c.execute(
            "SELECT id FROM offers WHERE request_id=? AND store_id=?", (id_, s["id"])
        ).fetchone()
        offer_id = existing["id"] if existing else uid()
        vals = (
            data.price,
            data.quality,
            data.condition,
            data.stock,
            data.installation,
            int(data.delivery),
            data.warranty,
            data.note,
            (
                datetime.now(timezone.utc) + timedelta(hours=data.validity_hours)
            ).isoformat(),
            now(),
            "active",
        )
        if existing:
            c.execute(
                "UPDATE offers SET price=?,quality=?,condition=?,stock=?,installation=?,delivery=?,warranty=?,note=?,expires_at=?,created_at=?,status=? WHERE id=?",
                (*vals, offer_id),
            )
        else:
            c.execute(
                "INSERT INTO offers VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (offer_id, id_, s["id"], *vals),
            )
        notify(
            c,
            r["buyer_id"],
            "Yeni təklif",
            s["name"] + " mağazasından " + str(data.price) + " ₼",
            id_,
        )
        return one(c, "SELECT * FROM offers WHERE id=?", (offer_id,))


@app.get("/offers/mine")
def my_offers(u=Depends(user)):
    with db.connect() as c:
        s = seller_store(c, u)
        return rows(
            c,
            "SELECT o.*,r.title FROM offers o JOIN requests r ON r.id=o.request_id WHERE store_id=? ORDER BY o.created_at DESC",
            (s["id"],),
        )


@app.delete("/offers/{id_}")
def withdraw(id_: str, u=Depends(user)):
    with db.connect() as c:
        s = seller_store(c, u)
        o = one(c, "SELECT * FROM offers WHERE id=?", (id_,))
        if o["store_id"] != s["id"]:
            fail(403, "Təklif sənə aid deyil")
        c.execute("UPDATE offers SET status='withdrawn' WHERE id=?", (id_,))
    return {"ok": True}


@app.get("/stores")
def stores(u=Depends(user)):
    with db.connect() as c:
        return [store_dict(s) for s in rows(c, "SELECT * FROM stores WHERE verified=1")]


@app.get("/stores/mine")
def my_store(u=Depends(user)):
    with db.connect() as c:
        return store_dict(seller_store(c, u))


@app.patch("/stores/mine")
def update_store(data: StoreInput, u=Depends(user)):
    with db.connect() as c:
        s = seller_store(c, u)
        # Identity/address changes invalidate verification until admin review.
        verified = (
            s["verified"]
            if (s["name"], s["address"], s["district"])
            == (data.name, data.address, data.district)
            else 0
        )
        c.execute(
            "UPDATE stores SET name=?,district=?,address=?,phone=?,categories=?,hours=?,verified=? WHERE id=?",
            (
                data.name,
                data.district,
                data.address,
                data.phone,
                json.dumps(data.categories),
                data.hours,
                verified,
                s["id"],
            ),
        )
        return store_dict(one(c, "SELECT * FROM stores WHERE id=?", (s["id"],)))


@app.get("/stores/{id_}")
def store(id_: str, u=Depends(user)):
    with db.connect() as c:
        s = one(c, "SELECT * FROM stores WHERE id=?", (id_,))
        if not s["verified"] and u["id"] != s["owner_id"] and u["role"] != "admin":
            fail(404, "Mağaza tapılmadı")
        return store_dict(s)


@app.get("/favorites")
def favorites(u=Depends(user)):
    with db.connect() as c:
        return [
            store_dict(s)
            for s in rows(
                c,
                "SELECT s.* FROM stores s JOIN favorites f ON f.store_id=s.id WHERE f.user_id=?",
                (u["id"],),
            )
        ]


@app.post("/favorites/{store_id}")
def favorite(store_id: str, u=Depends(user)):
    with db.connect() as c:
        one(c, "SELECT * FROM stores WHERE id=? AND verified=1", (store_id,))
        c.execute("INSERT OR IGNORE INTO favorites VALUES(?,?)", (u["id"], store_id))
    return {"ok": True}


@app.delete("/favorites/{store_id}")
def unfavorite(store_id: str, u=Depends(user)):
    with db.connect() as c:
        c.execute(
            "DELETE FROM favorites WHERE user_id=? AND store_id=?", (u["id"], store_id)
        )
    return {"ok": True}


@app.post("/conversations")
def start_chat(data: ConversationInput, u=Depends(user)):
    with db.connect() as c:
        r = request_access(c, data.request_id, u)
        if r["buyer_id"] != u["id"]:
            fail(403, "Yazışmanı alıcı başlada bilər")
        one(
            c,
            "SELECT id FROM offers WHERE request_id=? AND store_id=? AND status='active' AND expires_at>?",
            (data.request_id, data.store_id, now()),
        )
        c.execute(
            "INSERT OR IGNORE INTO conversations VALUES(?,?,?,?)",
            (uid(), data.request_id, u["id"], data.store_id),
        )
        return one(
            c,
            "SELECT * FROM conversations WHERE request_id=? AND store_id=?",
            (data.request_id, data.store_id),
        )


@app.get("/conversations")
def conversations(u=Depends(user)):
    with db.connect() as c:
        return rows(
            c,
            "SELECT c.*,s.name store_name,u.name buyer_name,r.title request_title,(SELECT text FROM messages WHERE conversation_id=c.id ORDER BY created_at DESC LIMIT 1) last_message FROM conversations c JOIN stores s ON s.id=c.store_id JOIN users u ON u.id=c.buyer_id JOIN requests r ON r.id=c.request_id WHERE c.buyer_id=? OR s.owner_id=?",
            (u["id"], u["id"]),
        )


@app.get("/conversations/{id_}/messages")
def messages(id_: str, u=Depends(user)):
    with db.connect() as c:
        conversation_access(c, id_, u)
        return rows(
            c,
            "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at LIMIT 1000",
            (id_,),
        )


@app.post("/conversations/{id_}/messages", status_code=201)
def message(id_: str, data: MessageInput, u=Depends(user)):
    with db.connect() as c:
        conv = conversation_access(c, id_, u)
        mid = uid()
        c.execute(
            "INSERT INTO messages VALUES(?,?,?,?,?)",
            (mid, id_, u["id"], data.text.strip(), now()),
        )
        target = conv["owner_id"] if u["id"] == conv["buyer_id"] else conv["buyer_id"]
        notify(c, target, "Yeni mesaj", data.text[:100], id_, "message")
        return one(c, "SELECT * FROM messages WHERE id=?", (mid,))


@app.get("/notifications")
def notifications(u=Depends(user)):
    with db.connect() as c:
        return rows(
            c,
            "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 100",
            (u["id"],),
        )


@app.post("/notifications/read")
def read_notifications(u=Depends(user)):
    with db.connect() as c:
        c.execute("UPDATE notifications SET read=1 WHERE user_id=?", (u["id"],))
    return {"ok": True}


@app.post("/reports", status_code=201)
def report(data: ReportInput, u=Depends(user)):
    with db.connect() as c:
        c.execute(
            "INSERT INTO reports VALUES(?,?,?,?,?,?)",
            (uid(), u["id"], data.reason, data.detail, "pending", now()),
        )
    return {"ok": True}


@app.get("/analytics")
def analytics(u=Depends(user)):
    with db.connect() as c:
        s = seller_store(c, u)
        return {
            "offers": c.execute(
                "SELECT count(*) FROM offers WHERE store_id=?", (s["id"],)
            ).fetchone()[0],
            "conversations": c.execute(
                "SELECT count(*) FROM conversations WHERE store_id=?", (s["id"],)
            ).fetchone()[0],
            "active_offers": c.execute(
                "SELECT count(*) FROM offers WHERE store_id=? AND status='active' AND expires_at>?",
                (s["id"], now()),
            ).fetchone()[0],
        }


@app.get("/admin/overview")
def overview(u=Depends(admin)):
    with db.connect() as c:
        return {
            "stores": [
                store_dict(s) for s in rows(c, "SELECT * FROM stores WHERE verified=0")
            ],
            "reports": rows(c, "SELECT * FROM reports WHERE status='pending'"),
        }


@app.post("/admin/stores/{id_}/verify")
def verify(id_: str, u=Depends(admin)):
    with db.connect() as c:
        one(c, "SELECT * FROM stores WHERE id=?", (id_,))
        c.execute("UPDATE stores SET verified=1 WHERE id=?", (id_,))
    return {"ok": True}
