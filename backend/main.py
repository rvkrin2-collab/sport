from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from backend.strength_api import router as strength_router

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "sport.db"
TREDICT_TOKEN_PATH = DATA_DIR / "tredict.token"
TREDICT_BASE = "https://www.tredict.com/api/oauth/v2"
START_DATE = date(2026, 8, 30)
END_DATE = date(2026, 11, 22)

app = FastAPI(title="Sport Dashboard", version="0.4.1")
app.include_router(strength_router)


@app.middleware("http")
async def support_tailscale_path_prefix(request: Request, call_next):
    path = request.scope.get("path", "")
    if path == "/sport":
        return RedirectResponse(url="/sport/", status_code=307)
    if path.startswith("/sport/"):
        request.scope["path"] = path[len("/sport"):]
        request.scope["root_path"] = "/sport"
    response = await call_next(request)
    if request.scope.get("path", "").startswith("/api/"):
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
    title: str | None = None
    duration_min: float | None = None
    distance_km: float | None = None
    avg_hr: int | None = None
    pace_sec_km: float | None = None
    calories: int | None = None
    source: str = "manual"
    notes: str | None = None


class MigrationPayload(BaseModel):
    week: dict[str, bool] = Field(default_factory=dict)
    strengthDone: list[int] = Field(default_factory=list)
    exerciseLog: list[dict[str, Any]] = Field(default_factory=list)
    metrics: list[dict[str, Any]] = Field(default_factory=list)


class TredictTokenPayload(BaseModel):
    token: str = Field(min_length=10)


class HealthImportPayload(BaseModel):
    date: str
    weight: float | None = None
    resting_hr: int | None = None
    sleep_hours: float | None = None
    hrv_rmssd: float | None = None
    source: str = "external"


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(DATA_DIR, 0o700)
    except OSError:
        pass
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
            CREATE TABLE IF NOT EXISTS daily_health (
                date TEXT PRIMARY KEY,
                weight REAL,
                resting_hr INTEGER,
                dynamic_hr INTEGER,
                sleep_hours REAL,
                sleep_baseline_hours REAL,
                hrv_rmssd REAL,
                hrv_baseline REAL,
                body_fat REAL,
                source TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        ensure_column(conn, "workouts", "title", "TEXT")
        ensure_column(conn, "workouts", "pace_sec_km", "REAL")
        ensure_column(conn, "workouts", "calories", "INTEGER")


@app.on_event("startup")
def startup() -> None:
    init_db()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


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


def set_meta(key: str, value: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO meta(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
            (key, value, now_iso()),
        )


def get_meta(key: str) -> str | None:
    with connect() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def get_week(conn: sqlite3.Connection) -> dict[str, bool]:
    ws = current_week_start().isoformat()
    row = conn.execute("SELECT data FROM week_state WHERE week_start=?", (ws,)).fetchone()
    return json.loads(row["data"]) if row else {}


def get_state() -> dict[str, Any]:
    with connect() as conn:
        week = get_week(conn)
        strength = [r["number"] for r in conn.execute("SELECT number FROM strength_sessions ORDER BY number")]
        exercises = [dict(r) for r in conn.execute("SELECT date,name,result FROM exercise_log ORDER BY id")]
        metrics = [dict(r) for r in conn.execute("SELECT date,weight,waist,sleep,pulse,energy,pain FROM metrics ORDER BY date")]
        workouts = [dict(r) for r in conn.execute(
            "SELECT id,external_id,date,sport,subtype,title,duration_min,distance_km,avg_hr,pace_sec_km,calories,source,notes FROM workouts ORDER BY date DESC,id DESC LIMIT 100"
        )]
    return {
        "week": week,
        "strengthDone": strength,
        "exerciseLog": exercises,
        "metrics": metrics,
        "workouts": workouts,
        "project": {"start": START_DATE.isoformat(), "end": END_DATE.isoformat(), "week": current_week_number()},
    }


def combined_recovery_rows() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = [dict(r) for r in conn.execute(
            """
            SELECT d.date,
                   COALESCE(m.sleep,d.sleep_hours) AS sleep,
                   COALESCE(m.pulse,d.dynamic_hr,d.resting_hr) AS pulse,
                   m.energy,m.pain,d.hrv_rmssd,d.hrv_baseline
            FROM daily_health d LEFT JOIN metrics m ON m.date=d.date
            UNION
            SELECT m.date,m.sleep,m.pulse,m.energy,m.pain,NULL,NULL
            FROM metrics m WHERE NOT EXISTS (SELECT 1 FROM daily_health d WHERE d.date=m.date)
            ORDER BY date DESC LIMIT 21
            """
        )]
    return rows


def readiness() -> dict[str, Any]:
    rows = combined_recovery_rows()
    if not rows:
        return {"level":"unknown","title":"Нет данных восстановления","message":"Добавь сон, пульс и самочувствие — появится рекомендация на сегодня.","reasons":[],"date":None}

    latest = rows[0]
    reasons: list[str] = []
    score = 0
    sleep = latest.get("sleep")
    energy = latest.get("energy")
    pain = latest.get("pain")
    pulse = latest.get("pulse")
    hrv = latest.get("hrv_rmssd")
    hrv_base = latest.get("hrv_baseline")

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

    baseline_pulses = [r["pulse"] for r in rows[1:15] if r.get("pulse") is not None]
    if pulse is not None and len(baseline_pulses) >= 4:
        baseline = mean(baseline_pulses)
        delta = pulse - baseline
        if delta >= 8:
            score += 2; reasons.append(f"пульс покоя +{delta:.0f}")
        elif delta >= 5:
            score += 1; reasons.append(f"пульс покоя +{delta:.0f}")
    if hrv is not None and hrv_base:
        ratio = hrv / hrv_base
        if ratio < 0.80:
            score += 2; reasons.append("HRV заметно ниже базы")
        elif ratio < 0.90:
            score += 1; reasons.append("HRV ниже базы")

    age_days = (date.today() - date.fromisoformat(latest["date"])).days
    stale = age_days > 2
    if score >= 3:
        level, title, message = "red", "Сегодня лучше восстановление", "Не наращивай нагрузку. Тяжёлую работу лучше упростить или перенести."
    elif score >= 1:
        level, title, message = "yellow", "Нагрузка — с запасом", "План выполнять можно, но без попытки добавить объём или интенсивность."
    else:
        level, title, message = "green", "Можно тренироваться по плану", "По текущим данным явных признаков недовосстановления нет."
    if stale:
        level = "unknown"
        title = "Данные восстановления устарели"
        message = f"Последние данные за {latest['date']}. Нужна свежая синхронизация."
    return {"level":level,"title":title,"message":message,"reasons":reasons,"date":latest["date"]}


def week_stats(start: date) -> dict[str, Any]:
    end = start + timedelta(days=6)
    with connect() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM workouts WHERE sport='running' AND date BETWEEN ? AND ? ORDER BY date",
            (start.isoformat(), end.isoformat()),
        )]
    km = sum(float(r.get("distance_km") or 0) for r in rows)
    minutes = sum(float(r.get("duration_min") or 0) for r in rows)
    hrs = [int(r["avg_hr"]) for r in rows if r.get("avg_hr")]
    return {"start":start.isoformat(),"end":end.isoformat(),"runs":len(rows),"km":round(km,1),"minutes":round(minutes),"avg_hr":round(mean(hrs)) if hrs else None}


def running_summary() -> dict[str, Any]:
    ws = current_week_start()
    current = week_stats(ws)
    previous = week_stats(ws - timedelta(days=7))
    with connect() as conn:
        recent = [dict(r) for r in conn.execute(
            "SELECT date,title,duration_min,distance_km,avg_hr,pace_sec_km,source FROM workouts WHERE sport='running' ORDER BY date DESC,id DESC LIMIT 8"
        )]
    return {"current":current,"previous":previous,"recent":recent}


def coach_brief() -> dict[str, Any]:
    run = running_summary()
    cur, prev = run["current"], run["previous"]
    notes: list[str] = []
    if cur["runs"]:
        notes.append(f"На этой неделе: {cur['runs']} пробежки, {cur['km']:.1f} км.")
    else:
        notes.append("На этой неделе пробежек пока нет в базе.")
    if prev["km"] > 0 and cur["km"] > 0:
        delta = (cur["km"] - prev["km"]) / prev["km"] * 100
        if delta > 20:
            notes.append(f"Беговой объём уже на {delta:.0f}% выше прошлой недели — силовые держать короткими.")
        elif delta < -20:
            notes.append(f"Беговой объём пока на {abs(delta):.0f}% ниже прошлой недели.")
        else:
            notes.append("Беговой объём близок к прошлой неделе.")
    r = readiness()
    notes.append(r["title"] + ".")
    with connect() as conn:
        strength = conn.execute("SELECT COUNT(*) AS n FROM strength_sessions").fetchone()["n"]
        latest_metric = conn.execute("SELECT date,weight,waist FROM metrics ORDER BY date DESC LIMIT 1").fetchone()
    notes.append(f"Силовые: {strength}/24.")
    if latest_metric and (latest_metric["weight"] is not None or latest_metric["waist"] is not None):
        bits=[]
        if latest_metric["weight"] is not None: bits.append(f"вес {latest_metric['weight']:.1f} кг")
        if latest_metric["waist"] is not None: bits.append(f"талия {latest_metric['waist']:.1f} см")
        notes.append("Последний замер: " + ", ".join(bits) + ".")
    return {"notes":notes,"generated_at":now_iso()}


def token_value() -> str | None:
    if not TREDICT_TOKEN_PATH.exists():
        return None
    return TREDICT_TOKEN_PATH.read_text(encoding="utf-8").strip() or None


async def tredict_get(path: str, token: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=35.0, follow_redirects=True) as client:
        r = await client.get(
            f"{TREDICT_BASE}/{path}", params=params,
            headers={"Authorization":f"Bearer {token}","Accept":"application/json;charset=UTF-8"},
        )
    if r.status_code in (401,403):
        raise HTTPException(status_code=400, detail="Tredict token is invalid or lacks read scopes")
    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Tredict returned {r.status_code}")
    return r.json()


def local_day(timestamp: str, offset_seconds: int | float | None = None) -> str:
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if offset_seconds:
            dt = dt.astimezone(timezone.utc) + timedelta(seconds=float(offset_seconds))
        return dt.date().isoformat()
    except Exception:
        return timestamp[:10]


def upsert_metric_fields(day: str, *, weight: float | None = None, sleep: float | None = None, pulse: int | None = None) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO metrics(date,weight,waist,sleep,pulse,energy,pain,updated_at)
            VALUES(?,?,NULL,?,?,NULL,NULL,?)
            ON CONFLICT(date) DO UPDATE SET
              weight=COALESCE(metrics.weight,excluded.weight),
              sleep=COALESCE(metrics.sleep,excluded.sleep),
              pulse=COALESCE(metrics.pulse,excluded.pulse),
              updated_at=excluded.updated_at
            """,
            (day, weight, sleep, pulse, now_iso()),
        )


def upsert_health(day: str, values: dict[str, Any]) -> None:
    keys = ["weight","resting_hr","dynamic_hr","sleep_hours","sleep_baseline_hours","hrv_rmssd","hrv_baseline","body_fat","source"]
    vals = [values.get(k) for k in keys]
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO daily_health(date,weight,resting_hr,dynamic_hr,sleep_hours,sleep_baseline_hours,hrv_rmssd,hrv_baseline,body_fat,source,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(date) DO UPDATE SET
              weight=COALESCE(excluded.weight,daily_health.weight),
              resting_hr=COALESCE(excluded.resting_hr,daily_health.resting_hr),
              dynamic_hr=COALESCE(excluded.dynamic_hr,daily_health.dynamic_hr),
              sleep_hours=COALESCE(excluded.sleep_hours,daily_health.sleep_hours),
              sleep_baseline_hours=COALESCE(excluded.sleep_baseline_hours,daily_health.sleep_baseline_hours),
              hrv_rmssd=COALESCE(excluded.hrv_rmssd,daily_health.hrv_rmssd),
              hrv_baseline=COALESCE(excluded.hrv_baseline,daily_health.hrv_baseline),
              body_fat=COALESCE(excluded.body_fat,daily_health.body_fat),
              source=COALESCE(excluded.source,daily_health.source),
              updated_at=excluded.updated_at
            """,
            (day,*vals,now_iso()),
        )


async def sync_tredict_data() -> dict[str, Any]:
    token = token_value()
    if not token:
        raise HTTPException(status_code=400, detail="Tredict token is not configured")

    activities = await tredict_get("activityList", token, {"pageSize":1000,"extendedSummary":1})
    body = await tredict_get("bodyvalues", token)
    since = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat().replace("+00:00", "Z")
    nowz = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    sleep = await tredict_get("sleep", token, {"startDate":nowz,"endDate":since})
    hrv = await tredict_get("hrv", token, {"startDate":nowz,"endDate":since})

    activity_rows = activities.get("_embedded", {}).get("activityList", activities.get("activityList", [])) or []
    imported_activities = 0
    with connect() as conn:
        for item in activity_rows:
            ext = str(item.get("id") or "").strip()
            if not ext or not item.get("date"):
                continue
            summary = item.get("summary") or item.get("extendedSummary") or {}
            duration = summary.get("durationTotal") or summary.get("duration")
            distance = summary.get("distance")
            hr = summary.get("heartrate")
            pace = summary.get("pace")
            calories = summary.get("calories")
            vals = {
                "external_id":ext,
                "date":local_day(item["date"]),
                "sport":item.get("sportType") or "misc",
                "subtype":item.get("subSportType"),
                "title":item.get("title"),
                "duration_min":round(float(duration)/60,1) if duration is not None else None,
                "distance_km":round(float(distance)/1000,3) if distance is not None else None,
                "avg_hr":round(float(hr)) if hr is not None else None,
                "pace_sec_km":float(pace) if pace is not None else None,
                "calories":round(float(calories)) if calories is not None else None,
                "source":"tredict",
                "notes":item.get("notes"),
                "updated_at":now_iso(),
            }
            conn.execute(
                """
                INSERT INTO workouts(external_id,date,sport,subtype,title,duration_min,distance_km,avg_hr,pace_sec_km,calories,source,notes,updated_at)
                VALUES(:external_id,:date,:sport,:subtype,:title,:duration_min,:distance_km,:avg_hr,:pace_sec_km,:calories,:source,:notes,:updated_at)
                ON CONFLICT(external_id) DO UPDATE SET
                  date=excluded.date,sport=excluded.sport,subtype=excluded.subtype,title=excluded.title,
                  duration_min=excluded.duration_min,distance_km=excluded.distance_km,avg_hr=excluded.avg_hr,
                  pace_sec_km=excluded.pace_sec_km,calories=excluded.calories,source=excluded.source,
                  notes=excluded.notes,updated_at=excluded.updated_at
                """, vals,
            )
            imported_activities += 1

    body_rows = body.get("bodyvalues", []) or []
    for item in body_rows:
        if not item.get("timestamp"):
            continue
        day = local_day(item["timestamp"], item.get("timezoneOffsetInSeconds"))
        w = item.get("weightInKilograms")
        pulse = item.get("hrRestDynamic") or item.get("restingHeartrate")
        upsert_health(day, {
            "weight":w,
            "resting_hr":item.get("restingHeartrate"),
            "dynamic_hr":item.get("hrRestDynamic"),
            "body_fat":item.get("bodyFatInPercent"),
            "source":"tredict",
        })
        if w is not None or pulse is not None:
            upsert_metric_fields(day, weight=w, pulse=int(pulse) if pulse is not None else None)

    for key, pair in (sleep.get("sleep", {}) or {}).items():
        if not pair:
            continue
        day = f"{key[:4]}-{key[4:6]}-{key[6:8]}"
        total = float(pair[0])/3600 if pair[0] is not None else None
        baseline = float(pair[1])/3600 if len(pair)>1 and pair[1] is not None else None
        upsert_health(day,{"sleep_hours":total,"sleep_baseline_hours":baseline,"source":"tredict"})
        if total is not None:
            upsert_metric_fields(day,sleep=round(total,2))

    for key, pair in (hrv.get("hrv", {}) or {}).items():
        if not pair:
            continue
        day = f"{key[:4]}-{key[4:6]}-{key[6:8]}"
        upsert_health(day,{"hrv_rmssd":pair[0],"hrv_baseline":pair[1] if len(pair)>1 else None,"source":"tredict"})

    set_meta("tredict_last_sync", now_iso())
    set_meta("tredict_last_status", "ok")
    set_meta("tredict_last_count", str(imported_activities))
    return {"ok":True,"activities":imported_activities,"bodyvalues":len(body_rows),"last_sync":get_meta("tredict_last_sync")}


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok":True,"version":"0.4.1","db":str(DB_PATH)}


@app.get("/api/state")
def state() -> dict[str, Any]:
    return get_state()


@app.get("/api/today")
def today() -> dict[str, Any]:
    return {"date":date.today().isoformat(),"week":current_week_number(),"readiness":readiness(),"running":running_summary(),"coach":coach_brief()}


@app.get("/api/summary/running")
def summary_running() -> dict[str, Any]:
    return running_summary()


@app.get("/api/coach")
def coach() -> dict[str, Any]:
    return coach_brief()


@app.post("/api/week")
def save_week(payload: WeekPayload) -> dict[str, bool]:
    ws=current_week_start().isoformat()
    with connect() as conn:
        conn.execute("INSERT INTO week_state(week_start,data,updated_at) VALUES(?,?,?) ON CONFLICT(week_start) DO UPDATE SET data=excluded.data,updated_at=excluded.updated_at",(ws,json.dumps(payload.data,ensure_ascii=False),now_iso()))
    return payload.data


@app.post("/api/strength/toggle")
def toggle_strength(payload: StrengthTogglePayload) -> dict[str, Any]:
    with connect() as conn:
        row=conn.execute("SELECT number FROM strength_sessions WHERE number=?",(payload.number,)).fetchone()
        if row:
            conn.execute("DELETE FROM strength_sessions WHERE number=?",(payload.number,)); done=False
        else:
            conn.execute("INSERT INTO strength_sessions(number,completed_at) VALUES(?,?)",(payload.number,now_iso())); done=True
    return {"number":payload.number,"done":done}


@app.post("/api/exercises")
def add_exercise(payload: ExercisePayload) -> dict[str, Any]:
    d=payload.date or date.today().isoformat()
    with connect() as conn:
        cur=conn.execute("INSERT INTO exercise_log(date,name,result,created_at) VALUES(?,?,?,?)",(d,payload.name.strip(),payload.result.strip(),now_iso()))
    return {"id":cur.lastrowid,"date":d,"name":payload.name,"result":payload.result}


@app.post("/api/metrics")
def upsert_metric(payload: MetricPayload) -> dict[str, Any]:
    try: date.fromisoformat(payload.date)
    except ValueError as exc: raise HTTPException(status_code=400,detail="Invalid date") from exc
    values=payload.model_dump()
    with connect() as conn:
        conn.execute(
            """INSERT INTO metrics(date,weight,waist,sleep,pulse,energy,pain,updated_at)
            VALUES(:date,:weight,:waist,:sleep,:pulse,:energy,:pain,:updated_at)
            ON CONFLICT(date) DO UPDATE SET weight=excluded.weight,waist=excluded.waist,sleep=excluded.sleep,pulse=excluded.pulse,energy=excluded.energy,pain=excluded.pain,updated_at=excluded.updated_at""",
            {**values,"updated_at":now_iso()},
        )
    return values


@app.get("/api/workouts")
def list_workouts(limit:int=100) -> list[dict[str,Any]]:
    limit=min(max(limit,1),500)
    with connect() as conn:
        return [dict(r) for r in conn.execute("SELECT id,external_id,date,sport,subtype,title,duration_min,distance_km,avg_hr,pace_sec_km,calories,source,notes FROM workouts ORDER BY date DESC,id DESC LIMIT ?",(limit,))]


@app.post("/api/workouts")
def upsert_workout(payload: WorkoutPayload) -> dict[str,Any]:
    try: date.fromisoformat(payload.date)
    except ValueError as exc: raise HTTPException(status_code=400,detail="Invalid date") from exc
    v={**payload.model_dump(),"updated_at":now_iso()}
    with connect() as conn:
        if payload.external_id:
            conn.execute("""INSERT INTO workouts(external_id,date,sport,subtype,title,duration_min,distance_km,avg_hr,pace_sec_km,calories,source,notes,updated_at)
            VALUES(:external_id,:date,:sport,:subtype,:title,:duration_min,:distance_km,:avg_hr,:pace_sec_km,:calories,:source,:notes,:updated_at)
            ON CONFLICT(external_id) DO UPDATE SET date=excluded.date,sport=excluded.sport,subtype=excluded.subtype,title=excluded.title,duration_min=excluded.duration_min,distance_km=excluded.distance_km,avg_hr=excluded.avg_hr,pace_sec_km=excluded.pace_sec_km,calories=excluded.calories,source=excluded.source,notes=excluded.notes,updated_at=excluded.updated_at""",v)
        else:
            conn.execute("INSERT INTO workouts(external_id,date,sport,subtype,title,duration_min,distance_km,avg_hr,pace_sec_km,calories,source,notes,updated_at) VALUES(NULL,?,?,?,?,?,?,?,?,?,?,?,?)",(payload.date,payload.sport,payload.subtype,payload.title,payload.duration_min,payload.distance_km,payload.avg_hr,payload.pace_sec_km,payload.calories,payload.source,payload.notes,now_iso()))
    return payload.model_dump()


@app.post("/api/import/health")
def import_health(payload: HealthImportPayload) -> dict[str,Any]:
    try: date.fromisoformat(payload.date)
    except ValueError as exc: raise HTTPException(status_code=400,detail="Invalid date") from exc
    upsert_health(payload.date,{"weight":payload.weight,"resting_hr":payload.resting_hr,"sleep_hours":payload.sleep_hours,"hrv_rmssd":payload.hrv_rmssd,"source":payload.source})
    upsert_metric_fields(payload.date,weight=payload.weight,sleep=payload.sleep_hours,pulse=payload.resting_hr)
    return {"ok":True}


@app.get("/api/integrations/tredict")
def tredict_status() -> dict[str,Any]:
    return {"configured":bool(token_value()),"last_sync":get_meta("tredict_last_sync"),"status":get_meta("tredict_last_status"),"last_count":int(get_meta("tredict_last_count") or 0)}


@app.post("/api/integrations/tredict/token")
async def tredict_set_token(payload:TredictTokenPayload) -> dict[str,Any]:
    token=payload.token.strip()
    await tredict_get("activityList",token,{"pageSize":50,"extendedSummary":1})
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    TREDICT_TOKEN_PATH.write_text(token+"\n",encoding="utf-8")
    os.chmod(TREDICT_TOKEN_PATH,0o600)
    set_meta("tredict_last_status","configured")
    sync=await sync_tredict_data()
    return {"configured":True,"sync":sync}


@app.delete("/api/integrations/tredict/token")
def tredict_delete_token() -> dict[str,Any]:
    if TREDICT_TOKEN_PATH.exists(): TREDICT_TOKEN_PATH.unlink()
    set_meta("tredict_last_status","disconnected")
    return {"configured":False}


@app.post("/api/integrations/tredict/sync")
async def tredict_sync() -> dict[str,Any]:
    try:
        return await sync_tredict_data()
    except HTTPException:
        set_meta("tredict_last_status","error")
        raise
    except Exception as exc:
        set_meta("tredict_last_status","error")
        raise HTTPException(status_code=502,detail=str(exc)) from exc


@app.post("/api/migrate")
def migrate(payload: MigrationPayload) -> dict[str,Any]:
    with connect() as conn:
        existing=conn.execute("SELECT COUNT(*) AS n FROM metrics").fetchone()["n"]+conn.execute("SELECT COUNT(*) AS n FROM exercise_log").fetchone()["n"]+conn.execute("SELECT COUNT(*) AS n FROM strength_sessions").fetchone()["n"]
        if existing>0: return {"migrated":False,"reason":"server already has data"}
    save_week(WeekPayload(data=payload.week))
    for n in payload.strengthDone:
        if 1<=int(n)<=24:
            with connect() as conn: conn.execute("INSERT OR IGNORE INTO strength_sessions(number,completed_at) VALUES(?,?)",(int(n),now_iso()))
    for x in payload.exerciseLog:
        if x.get("name") and x.get("result"): add_exercise(ExercisePayload(name=str(x["name"]),result=str(x["result"]),date=x.get("date")))
    for x in payload.metrics:
        if x.get("date"):
            data={k:(None if x.get(k) in ("",None) else x.get(k)) for k in ["weight","waist","sleep","pulse","energy","pain"]}
            upsert_metric(MetricPayload(date=str(x["date"]),**data))
    return {"migrated":True}


@app.get("/api/export")
def export() -> JSONResponse:
    payload=get_state()
    payload["dailyHealth"]=[]
    with connect() as conn:
        payload["dailyHealth"]=[dict(r) for r in conn.execute("SELECT * FROM daily_health ORDER BY date")]
    return JSONResponse(payload,headers={"Content-Disposition":"attachment; filename=sport-data.json"})


@app.get("/")
def root() -> FileResponse:
    return FileResponse(ROOT/"index.html")


@app.get("/index.html")
def index() -> FileResponse:
    return FileResponse(ROOT/"index.html")


@app.get("/styles.css")
def css() -> FileResponse:
    return FileResponse(ROOT/"styles.css",media_type="text/css")


@app.get("/app.js")
def js() -> FileResponse:
    return FileResponse(ROOT/"app.js",media_type="application/javascript")
