import io
import os
import tempfile
from pathlib import Path

os.environ["DEMO_MODE"] = "true"
os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp()) / "test.db")
os.environ["UPLOAD_DIR"] = str(Path(tempfile.mkdtemp()))
from fastapi.testclient import TestClient
from PIL import Image
from app.main import app


def login(c, role):
    r = c.post("/auth/demo", json={"role": role})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def test_marketplace_flow_and_permissions():
    with TestClient(app) as c:
        buyer = login(c, "buyer")
        seller = login(c, "seller")
        admin = login(c, "admin")
        assert c.get("/requests").status_code == 401
        assert c.get("/admin/overview", headers=buyer).status_code == 403
        draft = c.post(
            "/ai/analyze",
            headers=buyer,
            json={"text": "Samsung A52 ekran 120 manat Xətai"},
        ).json()
        assert draft["brand"] == "Samsung" and draft["budget"] == 120
        payload = {
            "title": "Samsung A52 ekran",
            "brand": "Samsung",
            "model": "A52",
            "part": "Ekran",
            "budget": 120,
            "district": "Xətai",
        }
        req = c.post("/requests", headers=buyer, json=payload)
        assert req.status_code == 201, req.text
        rid = req.json()["id"]
        assert c.post("/requests", headers=seller, json=payload).status_code == 403
        assert c.get("/requests/" + rid, headers=seller).status_code == 200
        offer = c.post(f"/requests/{rid}/offers", headers=seller, json={"price": 95})
        assert offer.status_code == 201, offer.text
        assert c.get(f"/requests/{rid}/offers", headers=seller).status_code == 403
        assert len(c.get(f"/requests/{rid}/offers", headers=buyer).json()) == 1
        assert (
            c.post(
                f"/requests/{rid}/offers", headers=seller, json={"price": 90}
            ).status_code
            == 201
        )
        assert len(c.get(f"/requests/{rid}/offers", headers=buyer).json()) == 1
        conv = c.post(
            "/conversations",
            headers=buyer,
            json={"request_id": rid, "store_id": "mobilefix"},
        ).json()
        mid = conv["id"]
        assert (
            c.post(
                f"/conversations/{mid}/messages", headers=buyer, json={"text": "Salam"}
            ).status_code
            == 201
        )
        assert (
            c.post(
                f"/conversations/{mid}/messages",
                headers=seller,
                json={"text": "Buyurun"},
            ).status_code
            == 201
        )
        assert len(c.get(f"/conversations/{mid}/messages", headers=buyer).json()) == 2
        assert c.get(f"/conversations/{mid}/messages", headers=admin).status_code == 403
        assert c.post("/favorites/mobilefix", headers=buyer).status_code == 200
        assert len(c.get("/favorites", headers=buyer).json()) == 1
        assert c.get("/notifications", headers=buyer).json()
        assert c.post("/notifications/read", headers=buyer).status_code == 200
        assert (
            c.patch(
                "/requests/" + rid, headers=seller, json={"status": "completed"}
            ).status_code
            == 403
        )
        assert (
            c.patch(
                "/requests/" + rid, headers=buyer, json={"status": "completed"}
            ).status_code
            == 200
        )
        assert (
            c.post(
                f"/requests/{rid}/offers", headers=seller, json={"price": 99}
            ).status_code
            == 409
        )
        assert (
            c.post(
                "/reports",
                headers=buyer,
                json={"reason": "Stok", "detail": "Stok düzgün deyil"},
            ).status_code
            == 201
        )
        assert c.get("/admin/overview", headers=admin).json()["reports"]
        assert c.post("/auth/logout", headers=buyer).status_code == 200
        assert c.get("/me", headers=buyer).status_code == 401


def test_uploads_and_store_verification():
    with TestClient(app) as c:
        buyer = login(c, "buyer")
        seller = login(c, "seller")
        admin = login(c, "admin")
        assert (
            c.post(
                "/uploads",
                headers=buyer,
                files={"file": ("bad.jpg", b"not an image", "image/jpeg")},
            ).status_code
            == 400
        )
        im = Image.new("RGB", (10, 10))
        buf = io.BytesIO()
        im.save(buf, "PNG")
        upload = c.post(
            "/uploads",
            headers=buyer,
            files={"file": ("x.png", buf.getvalue(), "image/png")},
        )
        assert upload.status_code == 200
        iid = upload.json()["id"]
        assert c.get("/uploads/" + iid, headers=buyer).status_code == 200
        assert c.get("/uploads/" + iid, headers=seller).status_code == 404
        store = c.get("/stores/mine", headers=seller).json()
        store["address"] = "Yeni ünvan"
        result = c.patch("/stores/mine", headers=seller, json=store)
        assert result.status_code == 200, result.text
        assert not result.json()["verified"]
        assert c.get("/requests", headers=seller).json() == []
        assert (
            c.post("/admin/stores/mobilefix/verify", headers=buyer).status_code == 403
        )
        assert (
            c.post("/admin/stores/mobilefix/verify", headers=admin).status_code == 200
        )


def test_unrelated_buyer_cannot_access_request():
    from app import db
    import hashlib, time

    with TestClient(app) as c:
        with db.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users(id,name,role) VALUES('other','Other','buyer')"
            )
            conn.execute(
                "INSERT OR REPLACE INTO sessions VALUES(?,?,?)",
                (
                    hashlib.sha256(b"other-token").hexdigest(),
                    "other",
                    int(time.time()) + 3600,
                ),
            )
        h = {"Authorization": "Bearer other-token"}
        assert c.get("/requests/demo-request", headers=h).status_code == 403
        assert c.get("/requests/demo-request/offers", headers=h).status_code == 403
