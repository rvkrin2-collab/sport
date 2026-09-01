from pathlib import Path
import re

p = Path('backend/strength_api.py')
text = p.read_text(encoding='utf-8')

new_history = '''@router.get("/history")
def strength_history() -> list[dict[str, Any]]:
    ensure_tables()
    with connect() as conn:
        marks = [dict(r) for r in conn.execute(
            "SELECT number,completed_at FROM strength_sessions WHERE number BETWEEN 1 AND 24 ORDER BY number DESC"
        )]
        logs = {r["number"]: dict(r) for r in conn.execute(
            "SELECT * FROM strength_workout_logs WHERE number BETWEEN 1 AND 24"
        )}
        sessions: list[dict[str, Any]] = []
        for mark in marks:
            n = int(mark["number"])
            s = logs.get(n)
            if s is None:
                completed_at = mark.get("completed_at") or now_iso()
                s = {
                    "number": n,
                    "date": str(completed_at)[:10],
                    "workout_type": "A" if n % 2 else "B",
                    "phase": phase_for(n)["name"],
                    "fatigue_mode": None,
                    "overall_rpe": None,
                    "notes": None,
                    "completed_at": completed_at,
                    "updated_at": completed_at,
                    "legacy_only": True,
                }
            else:
                s["legacy_only"] = False
            s["exercises"] = []
            for r in conn.execute(
                "SELECT exercise_key,load,reps_json,loads_json,rir,pain,note FROM strength_performance WHERE session_number=? ORDER BY id",
                (n,),
            ):
                x = dict(r)
                reps = json.loads(x.pop("reps_json") or "[]")
                x["reps"] = reps
                x["loads"] = _decode_loads(x.pop("loads_json"), x.get("load"), reps)
                meta = EXERCISES.get(x["exercise_key"])
                x["name"] = meta.name if meta else x["exercise_key"]
                x["measure"] = meta.measure if meta else "reps"
                s["exercises"].append(x)
            sessions.append(s)
    return sessions
'''
text, n1 = re.subn(
    r'@router\.get\("/history"\)\ndef strength_history\(\) -> list\[dict\[str, Any\]\]:.*?\n    return sessions\n',
    new_history, text, count=1, flags=re.S,
)
if n1 != 1:
    raise SystemExit('Could not replace strength_history')

new_record = '''@router.get("/record/{number}")
def strength_record(number: int) -> dict[str, Any]:
    if not 1 <= number <= 24:
        raise HTTPException(status_code=404, detail="Session must be 1..24")
    ensure_tables()
    with connect() as conn:
        log_row = conn.execute("SELECT * FROM strength_workout_logs WHERE number=?", (number,)).fetchone()
        mark = conn.execute("SELECT number,completed_at FROM strength_sessions WHERE number=?", (number,)).fetchone()
        if not log_row and not mark:
            raise HTTPException(status_code=404, detail="Силовая тренировка не найдена")
        prev = previous_by_exercise(conn, number)
        rows = conn.execute(
            "SELECT exercise_key,load,reps_json,loads_json,rir,pain,note FROM strength_performance WHERE session_number=? ORDER BY id",
            (number,),
        ).fetchall()

    if log_row:
        log = dict(log_row)
        log["legacy_only"] = False
    else:
        completed_at = mark["completed_at"] or now_iso()
        log = {
            "number": number,
            "date": str(completed_at)[:10],
            "workout_type": "A" if number % 2 else "B",
            "phase": phase_for(number)["name"],
            "fatigue_mode": "green",
            "overall_rpe": None,
            "notes": None,
            "completed_at": completed_at,
            "updated_at": completed_at,
            "legacy_only": True,
        }

    saved: dict[str, dict[str, Any]] = {}
    for row in rows:
        reps = json.loads(row["reps_json"] or "[]")
        loads = _decode_loads(row["loads_json"], row["load"], reps)
        meta = EXERCISES.get(row["exercise_key"])
        saved[row["exercise_key"]] = {
            "exercise_key": row["exercise_key"],
            "name": meta.name if meta else row["exercise_key"],
            "measure": meta.measure if meta else "reps",
            "reps": reps,
            "loads": loads,
            "rir": row["rir"],
            "pain": row["pain"],
            "note": row["note"],
        }

    fatigue = log.get("fatigue_mode") or "green"
    if fatigue not in {"green", "yellow", "post_hard_run", "red"}:
        fatigue = "green"
    plan = build_prescription(number, prev, fatigue_mode=fatigue)

    if "dead_bug" in saved and "front_plank" not in saved:
        legacy = EXERCISES["dead_bug"]
        for i, ex in enumerate(plan["exercises"]):
            if ex["key"] == "front_plank":
                plan["exercises"][i] = {
                    "key": legacy.key, "name": legacy.name, "sets": max(2, len(saved["dead_bug"]["reps"])),
                    "rep_min": legacy.rep_min, "rep_max": legacy.rep_max, "rir_target": plan["phase"]["rir"],
                    "load_hint": legacy.load_hint, "notes": legacy.notes, "measure": legacy.measure,
                    "previous": prev.get(legacy.key), "target_load": None,
                    "target_text": "Старая запись. Для новых тренировок это упражнение заменено планкой.",
                    "decision": "legacy",
                }
                break

    return {"log": log, "plan": plan, "saved": saved}
'''
text, n2 = re.subn(
    r'@router\.get\("/record/\{number\}"\)\ndef strength_record\(number: int\) -> dict\[str, Any\]:.*?\n    return \{"log": dict\(log\), "plan": plan, "saved": saved\}\n',
    new_record, text, count=1, flags=re.S,
)
if n2 != 1:
    raise SystemExit('Could not replace strength_record')
p.write_text(text, encoding='utf-8')

p = Path('strength-ui.js')
text = p.read_text(encoding='utf-8')
text = text.replace('v0.5.3 adaptive strength coach', 'v0.5.4 adaptive strength coach')
old = '<div class="tiny strength-history-summary">${(s.exercises||[]).map(historyExerciseText).join(\'<br>\')}</div>'
new = '<div class="tiny strength-history-summary">${(s.exercises||[]).length?(s.exercises||[]).map(historyExerciseText).join(\'<br>\'):\'Нет детализации подходов — нажми «Править» и внеси фактические результаты.\'}</div>'
if old not in text:
    raise SystemExit('Could not patch history summary')
text = text.replace(old, new, 1)
p.write_text(text, encoding='utf-8')

p = Path('index.html')
text = p.read_text(encoding='utf-8')
text = re.sub(r'strength-ui\.js\?v=[^"\']+', 'strength-ui.js?v=0.5.4', text)
text = re.sub(r'strength-ui\.css\?v=[^"\']+', 'strength-ui.css?v=0.5.4', text)
p.write_text(text, encoding='utf-8')

p = Path('backend/main.py')
text = p.read_text(encoding='utf-8').replace('version="0.5.3"', 'version="0.5.4"').replace('"version":"0.5.3"', '"version":"0.5.4"')
p.write_text(text, encoding='utf-8')
