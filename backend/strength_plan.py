from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Exercise:
    key: str
    name: str
    pattern: str
    rep_min: int
    rep_max: int
    base_sets: int
    increment: float
    load_hint: str
    notes: str
    leg_stress: bool = False


EXERCISES: dict[str, Exercise] = {
    "leg_press": Exercise(
        "leg_press", "Жим ногами", "legs", 8, 12, 3, 5,
        "вес тренажёра", "Не отрывать таз; не проваливаться глубоко, если тянет пах/заднюю поверхность бедра.", True,
    ),
    "incline_db_press": Exercise(
        "incline_db_press", "Наклонный жим гантелей", "push", 8, 12, 3, 2,
        "вес одной гантели", "Скамья 20–30°. Шея нейтрально, без тяжёлого жима над головой.", False,
    ),
    "lat_pulldown": Exercise(
        "lat_pulldown", "Тяга верхнего блока", "pull", 8, 12, 3, 5,
        "вес стека", "Тянуть локтями вниз, не запрокидывать голову.", False,
    ),
    "seated_row": Exercise(
        "seated_row", "Горизонтальная тяга", "pull", 8, 12, 3, 5,
        "вес стека", "Грудь спокойно, не вытягивать шею вперёд.", False,
    ),
    "lateral_raise": Exercise(
        "lateral_raise", "Разведения гантелей в стороны", "shoulders", 12, 20, 2, 1,
        "вес одной гантели", "Лёгкий вес, без шрага плечами.", False,
    ),
    "dead_bug": Exercise(
        "dead_bug", "Dead bug / мёртвый жук", "core", 8, 12, 2, 0,
        "без веса", "Повторы на сторону, поясница прижата.", False,
    ),
    "hip_thrust": Exercise(
        "hip_thrust", "Ягодичный мост / hip thrust", "hinge", 8, 12, 3, 5,
        "общий вес", "Движение тазом, не переразгибать поясницу и шею.", True,
    ),
    "reverse_lunge": Exercise(
        "reverse_lunge", "Выпады назад", "legs", 8, 12, 2, 2,
        "вес одной гантели", "Повторы на ногу. При боли в паху уменьшить шаг/вес или заменить на лёгкий жим ногами.", True,
    ),
    "chest_supported_row": Exercise(
        "chest_supported_row", "Тяга гантелей с опорой грудью", "pull", 8, 12, 3, 2,
        "вес одной гантели", "Опора грудью снимает лишнюю нагрузку с поясницы и шеи.", False,
    ),
    "pushup": Exercise(
        "pushup", "Отжимания с прогрессией", "push", 10, 15, 3, 0,
        "добавочный вес, если есть", "Не до отказа. Когда 3×15 легко — ноги выше или небольшой дополнительный вес.", False,
    ),
    "rear_delt": Exercise(
        "rear_delt", "Задняя дельта", "shoulders", 12, 20, 2, 1,
        "вес гантели/стека", "Лёгко, без подъёма плеч к ушам.", False,
    ),
    "side_plank": Exercise(
        "side_plank", "Боковая планка", "core", 25, 45, 2, 0,
        "секунды", "Время на сторону.", False,
    ),
}

A = ["leg_press", "incline_db_press", "lat_pulldown", "seated_row", "lateral_raise", "dead_bug"]
B = ["hip_thrust", "reverse_lunge", "chest_supported_row", "pushup", "rear_delt", "side_plank"]


def phase_for(number: int) -> dict[str, Any]:
    if number <= 4:
        return {"name": "Вход", "rir": "2–3", "main_sets": 2, "accessory_sets": 2,
                "message": "Подбираем рабочие веса и технику. Никакого отказа."}
    if number <= 8:
        return {"name": "Накопление", "rir": "2", "main_sets": 3, "accessory_sets": 2,
                "message": "Добавляем повторения; вес повышаем только после уверенного верхнего края диапазона."}
    if number <= 16:
        return {"name": "Прогресс", "rir": "1–2", "main_sets": 3, "accessory_sets": 2,
                "message": "Двойная прогрессия: сначала повторы, затем небольшой шаг веса."}
    if number <= 20:
        return {"name": "Закрепление", "rir": "1–2", "main_sets": 3, "accessory_sets": 2,
                "message": "Сохраняем качество, не жертвуем бегом ради рекордов в зале."}
    if number <= 23:
        return {"name": "Финиш", "rir": "1–2", "main_sets": 3, "accessory_sets": 2,
                "message": "Сильные, но контролируемые тренировки. Отказ по-прежнему не нужен."}
    return {"name": "Контроль", "rir": "1–2", "main_sets": 3, "accessory_sets": 2,
            "message": "Сравниваем с первыми тренировками на тех же упражнениях, без 1ПМ."}


def session_template(number: int) -> list[Exercise]:
    return [EXERCISES[k] for k in (A if number % 2 else B)]


def sets_for(ex: Exercise, phase: dict[str, Any], fatigue_mode: str) -> int:
    accessory = ex.pattern in {"shoulders", "core"} or ex.key == "reverse_lunge"
    sets = phase["accessory_sets"] if accessory else phase["main_sets"]
    if fatigue_mode in {"yellow", "post_hard_run"} and ex.leg_stress:
        sets = max(1, sets - 1)
    if fatigue_mode == "red" and ex.leg_stress:
        sets = 0
    return sets


def progression(previous: dict[str, Any] | None, ex: Exercise, target_sets: int, rep_min: int, rep_max: int,
                allow_progression: bool) -> dict[str, Any]:
    if not previous:
        return {
            "previous": None,
            "target_load": None,
            "target_text": f"Подбери вес на {target_sets}×{rep_min}–{rep_max}, оставляя 2–3 повтора в запасе.",
            "decision": "baseline",
        }

    load = previous.get("load")
    reps = previous.get("reps") or []
    rir = previous.get("rir")
    pain = previous.get("pain") or 0
    completed = len(reps) >= max(1, target_sets)
    at_top = completed and all(int(r) >= rep_max for r in reps[:target_sets])
    below = reps and min(int(r) for r in reps) < rep_min

    if pain >= 3:
        return {
            "previous": previous,
            "target_load": load,
            "target_text": "Боль ≥3/10 в прошлый раз: не прогрессировать. Уменьши вес/амплитуду на 10–15% или замени упражнение.",
            "decision": "pain",
        }
    if not allow_progression:
        return {
            "previous": previous,
            "target_load": load,
            "target_text": f"Сегодня сохранить прошлый вес и работать с запасом: {target_sets}×{rep_min}–{rep_max}.",
            "decision": "hold_fatigue",
        }
    if load is None or ex.increment == 0:
        if at_top:
            return {
                "previous": previous,
                "target_load": load,
                "target_text": "Усложни вариант совсем немного, но сохрани 1–2 повтора в запасе.",
                "decision": "progress_variant",
            }
        return {
            "previous": previous,
            "target_load": load,
            "target_text": f"Повтори вариант и добавь 1–2 суммарных повтора: цель {target_sets}×{rep_min}–{rep_max}.",
            "decision": "add_reps",
        }
    if below or (rir is not None and float(rir) < 1):
        return {
            "previous": previous,
            "target_load": load,
            "target_text": f"Вес пока не повышать. Повтори {load:g} кг и вернись в диапазон {rep_min}–{rep_max} с запасом.",
            "decision": "hold",
        }
    if at_top and (rir is None or float(rir) >= 1):
        new_load = float(load) + ex.increment
        return {
            "previous": previous,
            "target_load": new_load,
            "target_text": f"Повысить: {new_load:g} кг ({ex.load_hint}); цель {target_sets}×{rep_min}–{rep_max}.",
            "decision": "increase_load",
        }
    return {
        "previous": previous,
        "target_load": load,
        "target_text": f"Оставить {float(load):g} кг и добавить 1–2 суммарных повтора, пока не выйдешь на {target_sets}×{rep_max}.",
        "decision": "add_reps",
    }


def build_prescription(number: int, previous_by_exercise: dict[str, dict[str, Any]], fatigue_mode: str = "green",
                       fatigue_reason: str | None = None) -> dict[str, Any]:
    number = max(1, min(24, int(number)))
    phase = phase_for(number)
    allow_progression = fatigue_mode == "green"
    exercises = []
    for ex in session_template(number):
        sets = sets_for(ex, phase, fatigue_mode)
        if sets == 0:
            target = {"previous": previous_by_exercise.get(ex.key), "target_load": None,
                      "target_text": "Сегодня пропустить из-за восстановления/нагрузки.", "decision": "skip"}
        else:
            target = progression(previous_by_exercise.get(ex.key), ex, sets, ex.rep_min, ex.rep_max, allow_progression)
        exercises.append({
            "key": ex.key,
            "name": ex.name,
            "sets": sets,
            "rep_min": ex.rep_min,
            "rep_max": ex.rep_max,
            "rir_target": phase["rir"],
            "load_hint": ex.load_hint,
            "notes": ex.notes,
            **target,
        })
    return {
        "number": number,
        "type": "A" if number % 2 else "B",
        "phase": phase,
        "fatigue_mode": fatigue_mode,
        "fatigue_reason": fatigue_reason,
        "duration_min": 35,
        "exercises": exercises,
    }
