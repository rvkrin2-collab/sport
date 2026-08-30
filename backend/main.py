from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "sport.db"
START_DATE = date(2026, 8, 30)
END_DATE = date(2026, 11, 22)

app = FastAPI(title="Sport Dashboard", version="0.2.1")


@app.middleware("http")
async def support_tailscale_path_prefix(request: Request, call_next):
    """Work both when Tailscale preserves /sport and when it strips the mount path."""
    path = request.scope.get("path", "")
    if path == "/sport":
        return RedirectResponse(url="/sport/", status_code=307)
    if path.startswith("/sport/"):
        request.scope["path"] = path[len("/sport"):]
        request.scope["root_path"] = "/sport"
    response = await call_next(request)
    if request.scope["path"].startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


class WeekPayload(BaseModel):
    data: dict[str, bool] = Field(default_factory=dict)


class MetricPayload(BaseModel):
    date: str
    weight: float | None = None
    waist: float | None = None
    sleep: float | None = None
    pulse: int | None = None
    energy: int | None = Field(default=None, ge=1, le=5)
    pain: int | None = Field(default=None, ge=0, le=10)


class ExercisePayload(BaseModel):
    name: str
    result: str
    date: str | None = None


class StrengthTogglePayload(BaseModel):
    number: int = Field(ge=1, le=24)


class WorkoutPayload(BaseModel):
    external_id: str | None = None
    date: str
    sport: str
    subtype: str | None = None
    duration_min: float | None = None
    distance_km: float | None = None
    avg_hr: int | None = None
    source: str = "manual"
    notes: str | None = None


class MigrationPayload(BaseModel):
    week: dict[str, bool] = Field(default_factory=dict)
    strengthDone: list[int] = Field(default_factory=list)
    exerciseLog: list[dict[str, Any]] = Field(default_factory=list)
    metrics: list[dict[str, Any]] = Field(default_factory=list)


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS week_state (
                week_start TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS metrics (
                date TEXT PRIMARY KEY,
                weight REAL,
                waist REAL,
                sleep REAL,
                pulse INTEGER,
                energy INTEGER,
                pain INTEGER,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS strength_sessions (
                number INTEGER PRIMARY KEY,
                completed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS exercise_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                name TEXT NOT NULL,
                result TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS workouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id TEXT UNIQUE,
                date TEXT NOT NULL,
                sport TEXT NOT NULL,
                subtype TEXT,
                duration_min REAL,
                distance_km REAL,
                avg_hr INTEGER,
                source TEXT NOT NULL,
                notes TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_workouts_date ON workouts(date);
            """
        )


@app.on_event("startup")
def startup() -> None:
    init_db()


def current_week_start(on_date: date | None = None) -> date:
    d = on_date or date.today()
    if d < START_DATE:
        return START_DATE
    offset = (d - START_DATE).days
    return START_DATE + timedelta(days=(offset // 7) * 7)


def current_week_number(on_date: date | None = None) -> int:
    d = on_date or date.today()
    if d <= START_DATE:
        return 1
    return max(1, min(12, ((d - START_DATE).days // 7) + 1))


def get_week(conn: sqlite3.Connection) -> dict[str, bool]:
    ws = current_week_start().isoformat()
    row = conn.execute("SELECT data FROM week_state WHERE week_start=?", (ws,)).fetchone()
    return json.loads(row["data"]) if row else {}


def get_state() -> dict[str, Any]:
    with connect() as conn:
        week = get_week(conn)
        strength = [r["number"] for r in conn.execute("SELECT number FROM strength_sessions ORDER BY number")]
        exercises = [dict(r) for r in conn.execute("SELECT date,name,result FROM exercise_log ORDER BY id")]
        metrics = [dict(r) for r in conn.execute(
            "SELECT date,weight,waist,sleep,pulse,energy,pain FROM metrics ORDER BY date"
        )]
        workouts = [dict(r) for r in conn.execute(
            "SELECT id,external_id,date,sport,subtype,duration_min,distance_km,avg_hr,source,notes FROM workouts ORDER BY date DESC,id DESC LIMIT 100"
        )]
    return {
        "week": week,
        "strengthDone": strength,
        "exerciseLog": exercises,
        "metrics": metrics,
        "workouts": workouts,
        "project": {
            "start": START_DATE.isoformat(),
            "end": END_DATE.isoformat(),
            "week": current_week_number(),
        },
    }


def readiness() -> dict[str, Any]:
    with connect() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT date,sleep,pulse,energy,pain FROM metrics ORDER BY date DESC LIMIT 15"
        )]
    if not rows:
        return {
            "level": "unknown",
            "title": "Нет данных восстановления",
            "message": "Добавь сон, пульс и самочувствие — появится рекомендация на сегодня.",
            "reasons": [],
        }

    latest = rows[0]
    reasons: list[str] = []
    score = 0
    sleep = latest.get("sleep")
    energy = latest.get("energy")
    pain = latest.get("pain")
    pulse = latest.get("pulse")

    if sleep is not None:
        if sleep < 6:
            score += 2; reasons.append(f"сон {sleep:.1f} ч")
        elif sleep < 7:
            score += 1; reasons.append(f"сон {sleep:.1f} ч")
    if energy is not None:
        if energy <= 2:
            score += 2; reasons.append(f"энергия {energy}/5")
        elif energy == 3:
            score += 1; reasons.append("энергия 3/5")
    if pain is not None:
        if pain >= 5:
            score += 2; reasons.append(f"боль {pain}/10")
        elif pain >= 3:
            score += 1; reasons.append(f"боль {pain}/10")

    baseline_pulses = [r["pulse"] for r in rows[1:] if r.get("pulse") is not None]
    if pulse is not None and len(baseline_pulses) >= 4:
        baseline = mean(baseline_pulses)
        delta = pulse - baseline
        if delta >= 8:
            score += 2; reasons.append(f"пульс покоя +{delta:.0f}")
        elif delta >= 5:
            score += 1; reasons.append(f"пульс покоя +{delta:.0f}")

    if score >= 2:
        return {
            "level": "red",
            "title": "Сегодня лучше восстановление",
            "message": "Не наращивай нагрузку. Если по плану тяжёлая работа — лучше упростить или перенести.",
            "reasons": reasons,
        }
    if score == 1:
        return {
            "level": "yellow",
            "title": "Нагрузка — с запасом",
            "message": "План выполнять можно, но без попытки добавить объём или интенсивность.",
            "reasons": reasons,
        }
    return {
        "level": "green",
        "title": "Можно тренироваться по плану",
        "message": "По текущим данным явных признаков недовосстановления нет.",
        "reasons": reasons,
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "version": "0.2.1", "db": str(DB_PATH)}


@app.get("/api/state")
def state() -> dict[str, Any]:
    return get_state()


@app.get("/api/today")
def today() -> dict[str, Any]:
    return {"date": date.today().isoformat(), "week": current_week_number(), "readiness": readiness()}


@app.post("/api/week")
def save_week(payload: WeekPayload) -> dict[str, bool]:
    ws = current_week_start().isoformat()
    with connect() as conn:
        conn.execute(
            "INSERT INTO week_state(week_start,data,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(week_start) DO UPDATE SET data=excluded.data,updated_at=excluded.updated_at",
            (ws, json.dumps(payload.data, ensure_ascii=False), datetime.now().isoformat(timespec="seconds")),
        )
    return payload.data


@app.post("/api/strength/toggle")
def toggle_strength(payload: StrengthTogglePayload) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT number FROM strength_sessions WHERE number=?", (payload.number,)).fetchone()
        if row:
            conn.execute("DELETE FROM strength_sessions WHERE number=?", (payload.number,))
            done = False
        else:
            conn.execute(
                "INSERT INTO strength_sessions(number,completed_at) VALUES(?,?)",
                (payload.number, datetime.now().isoformat(timespec="seconds")),
            )
            done = True
    return {"number": payload.number, "done": done}


@app.post("/api/exercises")
def add_exercise(payload: ExercisePayload) -> dict[str, Any]:
    d = payload.date or date.today().isoformat()
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO exercise_log(date,name,result,created_at) VALUES(?,?,?,?)",
            (d, payload.name.strip(), payload.result.strip(), datetime.now().isoformat(timespec="seconds")),
        )
    return {"id": cur.lastrowid, "date": d, "name": payload.name, "result": payload.result}


@app.post("/api/metrics")
def upsert_metric(payload: MetricPayload) -> dict[str, Any]:
    try:
        date.fromisoformat(payload.date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid date") from exc
    values = payload.model_dump()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO metrics(date,weight,waist,sleep,pulse,energy,pain,updated_at)
            VALUES(:date,:weight,:waist,:sleep,:pulse,:energy,:pain,:updated_at)
            ON CONFLICT(date) DO UPDATE SET
              weight=excluded.weight, waist=excluded.waist, sleep=excluded.sleep,
              pulse=excluded.pulse, energy=excluded.energy, pain=excluded.pain,
              updated_at=excluded.updated_at
            """,
            {**values, "updated_at": datetime.now().isoformat(timespec="seconds")},
        )
    return values


@app.get("/api/workouts")
def list_workouts(limit: int = 100) -> list[dict[str, Any]]:
    limit = min(max(limit, 1), 500)
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id,external_id,date,sport,subtype,duration_min,distance_km,avg_hr,source,notes FROM workouts ORDER BY date DESC,id DESC LIMIT ?",
            (limit,),
        )]


@app.post("/api/workouts")
def upsert_workout(payload: WorkoutPayload) -> dict[str, Any]:
    try:
        date.fromisoformat(payload.date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid date") from exc
    values = payload.model_dump()
    with connect() as conn:
        if payload.external_id:
            conn.execute(
                """
                INSERT INTO workouts(external_id,date,sport,subtype,duration_min,distance_km,avg_hr,source,notes,updated_at)
                VALUES(:external_id,:date,:sport,:subtype,:duration_min,:distance_km,:avg_hr,:source,:notes,:updated_at)
                ON CONFLICT(external_id) DO UPDATE SET
                  date=excluded.date,sport=excluded.sport,subtype=excluded.subtype,
                  duration_min=excluded.duration_min,distance_km=excluded.distance_km,
                  avg_hr=excluded.avg_hr,source=excluded.source,notes=excluded.notes,updated_at=excluded.updated_at
                """,
                {**values, "updated_at": datetime.now().isoformat(timespec="seconds")},
            )
        else:
            conn.execute(
                "INSERT INTO workouts(external_id,date,sport,subtype,duration_min,distance_km,avg_hr,source,notes,updated_at) VALUES(NULL,?,?,?,?,?,?,?,?,?)",
                (
                    payload.date, payload.sport, payload.subtype, payload.duration_min,
                    payload.distance_km, payload.avg_hr, payload.source, payload.notes,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
    return values


@app.post("/api/migrate")
def migrate(payload: MigrationPayload) -> dict[str, Any]:
    with connect() as conn:
        existing = conn.execute("SELECT COUNT(*) AS n FROM metrics").fetchone()["n"]
        existing += conn.execute("SELECT COUNT(*) AS n FROM exercise_log").fetchone()["n"]
        existing += conn.execute("SELECT COUNT(*) AS n FROM strength_sessions").fetchone()["n"]
        if existing > 0:
            return {"migrated": False, "reason": "server already has data"}

    save_week(WeekPayload(data=payload.week))
    for n in payload.strengthDone:
        if 1 <= int(n) <= 24:
            with connect() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO strength_sessions(number,completed_at) VALUES(?,?)",
                    (int(n), datetime.now().isoformat(timespec="seconds")),
                )
    for x in payload.exerciseLog:
        if x.get("name") and x.get("result"):
            add_exercise(ExercisePayload(name=str(x["name"]), result=str(x["result"]), date=x.get("date")))
    for x in payload.metrics:
        if x.get("date"):
            data = {k: (None if x.get(k) in ("", None) else x.get(k)) for k in ["weight","waist","sleep","pulse","energy","pain"]}
            upsert_metric(MetricPayload(date=str(x["date"]), **data))
    return {"migrated": True}


@app.get("/api/export")
def export() -> JSONResponse:
    return JSONResponse(get_state(), headers={"Cache-Control": "no-store"})


@app.get("/")
def index() -> FileResponse:
    return FileResponse(ROOT / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/styles.css")
def styles() -> FileResponse:
    return FileResponse(ROOT / "styles.css", media_type="text/css")


@app.get("/app.js")
def script() -> FileResponse:
    return FileResponse(ROOT / "app.js", media_type="application/javascript", headers={"Cache-Control": "no-cache"})
