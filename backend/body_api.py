from __future__ import annotations

import io
import os
import sqlite3
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "sport.db"
PHOTO_DIR = DATA_DIR / "body_photos"
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_SIDE = 1800
ALLOWED_VIEWS = {"front", "side", "back"}

router = APIRouter(prefix="/api/body", tags=["body"])


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_tables() -> None:
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(PHOTO_DIR, 0o700)
    except OSError:
        pass
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS body_photos (
                id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                view TEXT NOT NULL,
                filename TEXT NOT NULL UNIQUE,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_body_photos_date ON body_photos(date);
            CREATE INDEX IF NOT EXISTS idx_body_photos_view ON body_photos(view, date);
            """
        )


ensure_tables()


def row_to_photo(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "date": row["date"],
        "view": row["view"],
        "width": row["width"],
        "height": row["height"],
        "note": row["note"],
        "created_at": row["created_at"],
        "url": f"api/body/photos/{row['id']}/file",
    }


@router.get("/summary")
def body_summary() -> dict[str, Any]:
    ensure_tables()
    with connect() as conn:
        metrics = [dict(r) for r in conn.execute(
            "SELECT date,weight,waist FROM metrics WHERE weight IS NOT NULL OR waist IS NOT NULL ORDER BY date"
        )]
        photo_count = conn.execute("SELECT COUNT(*) AS n FROM body_photos").fetchone()["n"]
    first = metrics[0] if metrics else None
    latest = metrics[-1] if metrics else None

    def delta(key: str) -> float | None:
        if not first or not latest or first.get(key) is None or latest.get(key) is None:
            return None
        return round(float(latest[key]) - float(first[key]), 1)

    return {
        "first": first,
        "latest": latest,
        "weight_delta": delta("weight"),
        "waist_delta": delta("waist"),
        "photo_count": photo_count,
    }


@router.get("/photos")
def list_photos() -> list[dict[str, Any]]:
    ensure_tables()
    with connect() as conn:
        rows = conn.execute(
            "SELECT id,date,view,filename,width,height,note,created_at FROM body_photos ORDER BY date DESC, created_at DESC"
        ).fetchall()
    return [row_to_photo(r) for r in rows]


@router.post("/photos")
async def upload_photo(
    photo: UploadFile = File(...),
    photo_date: str = Form(...),
    view: str = Form(...),
    note: str = Form(default=""),
) -> dict[str, Any]:
    ensure_tables()
    try:
        date.fromisoformat(photo_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Неверная дата") from exc
    if view not in ALLOWED_VIEWS:
        raise HTTPException(status_code=400, detail="Неверный ракурс")
    if photo.content_type and not photo.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Нужен файл изображения")

    raw = await photo.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Фото слишком большое, максимум 12 МБ")
    if not raw:
        raise HTTPException(status_code=400, detail="Пустой файл")

    try:
        with Image.open(io.BytesIO(raw)) as original:
            img = ImageOps.exif_transpose(original)
            img.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
            if img.mode not in ("RGB", "L"):
                background = Image.new("RGB", img.size, "white")
                if "A" in img.getbands():
                    background.paste(img, mask=img.getchannel("A"))
                else:
                    background.paste(img)
                img = background
            elif img.mode == "L":
                img = img.convert("RGB")
            else:
                img = img.copy()
            width, height = img.size
            photo_id = uuid.uuid4().hex
            filename = f"{photo_date}_{view}_{photo_id}.jpg"
            path = PHOTO_DIR / filename
            img.save(path, format="JPEG", quality=88, optimize=True)
            os.chmod(path, 0o600)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Не удалось прочитать изображение") from exc

    clean_note = note.strip()[:500] or None
    with connect() as conn:
        conn.execute(
            "INSERT INTO body_photos(id,date,view,filename,width,height,note,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (photo_id, photo_date, view, filename, width, height, clean_note, now_iso()),
        )
        row = conn.execute(
            "SELECT id,date,view,filename,width,height,note,created_at FROM body_photos WHERE id=?", (photo_id,)
        ).fetchone()
    return row_to_photo(row)


@router.get("/photos/{photo_id}/file")
def photo_file(photo_id: str) -> FileResponse:
    ensure_tables()
    with connect() as conn:
        row = conn.execute("SELECT filename FROM body_photos WHERE id=?", (photo_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Фото не найдено")
    path = PHOTO_DIR / row["filename"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Файл фото не найден")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@router.delete("/photos/{photo_id}")
def delete_photo(photo_id: str) -> dict[str, bool]:
    ensure_tables()
    with connect() as conn:
        row = conn.execute("SELECT filename FROM body_photos WHERE id=?", (photo_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Фото не найдено")
        conn.execute("DELETE FROM body_photos WHERE id=?", (photo_id,))
    path = PHOTO_DIR / row["filename"]
    if path.exists():
        path.unlink()
    return {"deleted": True}
