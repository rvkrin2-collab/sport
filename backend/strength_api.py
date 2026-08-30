from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.strength_plan import build_prescription, phase_for

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "sport.db"
router = APIRouter(prefix="/api/strength", tags=["strength"])


class ExerciseResult(BaseModel):
    exercise_key: str
    load: float | None = Field(default=None, ge=0)
    reps: list[int] = Field(default_factory=list, max_length=6)
    rir: float | None = Field(default=None, ge=0, le=5)
    pain: int | None = Field(default=None, ge=0, le=10)
    note: str | None = Field(default=None, max_length=500)


class StrengthSessionResult(BaseModel):
    number: int = Field(ge=1, le=24)
    date: str | None = None
    overall_rpe: float | None = Field(default=None, ge=1, le=10)
    notes: str | None = Field(default=None, max_length=1000)
    exercises: list[ExerciseResult] = Field(default_factory=list)


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_tables() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS strength_workout_logs (
                number INTEGER PRIMARY KEY,
                date TEXT NOT NULL,
                workout_type TEXT NOT NULL,
                phase TEXT NOT NULL,
                fatigue_mode TEXT,
                overall_rpe REAL,
                notes TEXT,
                completed_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS strength_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_number INTEGER NOT NULL,
                exercise_key TEXT NOT NULL,
                load REAL,
                reps_json TEXT NOT NULL,
                rir REAL,
                pain INTEGER,
                note TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(session_number, exercise_key)
            );
            CREATE INDEX IF NOT EXISTS idx_strength_perf_exercise
                ON strength_performance(exercise_key, session_number);
            """
        )


ensure_tables()


def next_number(conn: sqlite3.Connection) -> int | None:
    done = {r["number"] for r in conn.execute("SELECT number FROM strength_sessions WHERE number BETWEEN 1 AND 24")}
    for n in range(1, 25):
        if n not in done:
            return n
    return None


def previous_by_exercise(conn: sqlite3.Connection, number: int) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT p.exercise_key,p.load,p.reps_json,p.rir,p.pain,p.note,p.session_number,l.date
        FROM strength_performance p
        LEFT JOIN strength_workout_logs l ON l.number=p.session_number
        WHERE p.session_number < ?
        ORDER BY p.session_number DESC
        """,
        (number,),
    ).fetchall()
    result: dict[str, dict[str, Any]] = {}
    for r in rows:
        key = r["exercise_key"]
        if key in result:
            continue
        result[key] = {
            "session_number": r["session_number"],
            "date": r["date"],
            "load": r["load"],
            "reps": json.loads(r["reps_json"] or "[]"),
            "rir": r["rir"],
            "pain": r["pain"],
            "note": r["note"],
        }
    return result


def recovery_mode(conn: sqlite3.Connection) -> tuple[str, str | None]:
    # Manual metrics override imported health when available for the same day.
    row = conn.execute(
        """
        SELECT d.date,
               COALESCE(m.sleep,d.sleep_hours) AS sleep,
               COALESCE(m.pulse,d.dynamic_hr,d.resting_hr) AS pulse,
               m.energy,m.pain
        FROM daily_health d LEFT JOIN metrics m ON m.date=d.date
        UNION
        SELECT m.date,m.sleep,m.pulse,m.energy,m.pain
        FROM metrics m WHERE NOT EXISTS (SELECT 1 FROM daily_health d WHERE d.date=m.date)
        ORDER BY date DESC LIMIT 1
        """
    ).fetchone()

    score = 0
    reasons: list[str] = []
    if row:
        sleep = row["sleep"]
        energy = row["energy"]
        pain = row["pain"]
        pulse = row["pulse"]
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
                score += 3; reasons.append(f"боль {pain}/10")
            elif pain >= 3:
                score += 1; reasons.append(f"боль {pain}/10")
        pulses = [r["pulse"] for r in conn.execute(
            "SELECT pulse FROM metrics WHERE pulse IS NOT NULL ORDER BY date DESC LIMIT 15"
        ).fetchall()[1:]]
        if pulse is not None and len(pulses) >= 4:
            delta = pulse - mean(pulses)
            if delta >= 8:
                score += 2; reasons.append(f"пульс +{delta:.0f}")
            elif delta >= 5:
                score += 1; reasons.append(f"пульс +{delta:.0f}")

    if score >= 3:
        return "red", ", ".join(reasons) if reasons else "восстановление"
    if score >= 1:
        return "yellow", ", ".join(reasons) if reasons else "умеренное недовосстановление"

    # If a demanding run happened in the last 30 hours, keep the strength session
    # but remove leg progression and one leg set.
    cutoff = (datetime.now() - timedelta(hours=30)).date().isoformat()
    recent = conn.execute(
        """
        SELECT date,duration_min,distance_km,avg_hr,title
        FROM workouts WHERE sport='running' AND date>=?
        ORDER BY date DESC,id DESC LIMIT 1
        """,
        (cutoff,),
    ).fetchone()
    if recent:
        hard = (recent["duration_min"] or 0) >= 65 or (recent["distance_km"] or 0) >= 11 or (recent["avg_hr"] or 0) >= 165
        if hard:
            return "post_hard_run", f"недавний бег {recent['distance_km'] or 0:.1f} км / {recent['duration_min'] or 0:.0f} мин"
    return "green", None


def prescription(number: int) -> dict[str, Any]:
    ensure_tables()
    with connect() as conn:
        prev = previous_by_exercise(conn, number)
        mode, reason = recovery_mode(conn)
    return build_prescription(number, prev, fatigue_mode=mode, fatigue_reason=reason)


@router.get("/current")
def current_strength() -> dict[str, Any]:
    ensure_tables()
    with connect() as conn:
        n = next_number(conn)
        completed = conn.execute("SELECT COUNT(*) AS n FROM strength_sessions WHERE number BETWEEN 1 AND 24").fetchone()["n"]
    if n is None:
        return {"completed": True, "completed_count": completed, "next": None, "message": "24/24 — цикл завершён."}
    return {"completed": False, "completed_count": completed, "next": prescription(n)}


@router.get("/session/{number}")
def strength_session(number: int) -> dict[str, Any]:
    if not 1 <= number <= 24:
        raise HTTPException(status_code=404, detail="Session must be 1..24")
    return prescription(number)


@router.get("/roadmap")
def strength_roadmap() -> list[dict[str, Any]]:
    return [
        {
            "number": n,
            "type": "A" if n % 2 else "B",
            "phase": phase_for(n)["name"],
            "message": phase_for(n)["message"],
        }
        for n in range(1, 25)
    ]


@router.get("/history")
def strength_history() -> list[dict[str, Any]]:
    ensure_tables()
    with connect() as conn:
        sessions = [dict(r) for r in conn.execute(
            "SELECT * FROM strength_workout_logs ORDER BY number DESC"
        )]
        for s in sessions:
            s["exercises"] = []
            for r in conn.execute(
                "SELECT exercise_key,load,reps_json,rir,pain,note FROM strength_performance WHERE session_number=? ORDER BY id",
                (s["number"],),
            ):
                x = dict(r)
                x["reps"] = json.loads(x.pop("reps_json") or "[]")
                s["exercises"].append(x)
    return sessions


@router.post("/session")
def save_strength_session(payload: StrengthSessionResult) -> dict[str, Any]:
    ensure_tables()
    try:
        session_date = date.fromisoformat(payload.date) if payload.date else date.today()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid date") from exc

    plan = prescription(payload.number)
    known = {x["key"] for x in plan["exercises"]}
    unknown = [x.exercise_key for x in payload.exercises if x.exercise_key not in known]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown exercise: {unknown[0]}")

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO strength_workout_logs(number,date,workout_type,phase,fatigue_mode,overall_rpe,notes,completed_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(number) DO UPDATE SET
              date=excluded.date,workout_type=excluded.workout_type,phase=excluded.phase,
              fatigue_mode=excluded.fatigue_mode,overall_rpe=excluded.overall_rpe,notes=excluded.notes,
              completed_at=excluded.completed_at,updated_at=excluded.updated_at
            """,
            (payload.number, session_date.isoformat(), plan["type"], plan["phase"]["name"], plan["fatigue_mode"],
             payload.overall_rpe, payload.notes, now_iso(), now_iso()),
        )
        conn.execute("DELETE FROM strength_performance WHERE session_number=?", (payload.number,))
        for ex in payload.exercises:
            conn.execute(
                """
                INSERT INTO strength_performance(session_number,exercise_key,load,reps_json,rir,pain,note,created_at)
                VALUES(?,?,?,?,?,?,?,?)
                """,
                (payload.number, ex.exercise_key, ex.load, json.dumps(ex.reps), ex.rir, ex.pain, ex.note, now_iso()),
            )
        conn.execute(
            "INSERT OR REPLACE INTO strength_sessions(number,completed_at) VALUES(?,?)",
            (payload.number, now_iso()),
        )

    with connect() as conn:
        n = next_number(conn)
    return {
        "saved": True,
        "number": payload.number,
        "next": prescription(n) if n is not None else None,
        "completed": n is None,
    }
