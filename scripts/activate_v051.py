from pathlib import Path
import re

# Remove the stale embedded v0.4 strength UI. The current UI is a standalone asset.
p = Path("app.js")
text = p.read_text(encoding="utf-8")
marker = "// v0.4 adaptive strength coach UI."
if marker in text:
    text = text.split(marker, 1)[0].rstrip() + "\n"
    p.write_text(text, encoding="utf-8")

# Version assets and make the standalone strength UI/CSS load explicitly.
p = Path("index.html")
text = p.read_text(encoding="utf-8")
text = re.sub(r"styles\.css\?v=[^\"']+", "styles.css?v=0.5.1", text)
if "strength-ui.css" not in text:
    text = text.replace(
        '<link rel="stylesheet" href="styles.css?v=0.5.1">',
        '<link rel="stylesheet" href="styles.css?v=0.5.1">\n  <link rel="stylesheet" href="strength-ui.css?v=0.5.1">',
        1,
    )
text = re.sub(r"app\.js\?v=[^\"']+", "app.js?v=0.5.1", text)
if "strength-ui.js" not in text:
    text = text.replace(
        '<script src="app.js?v=0.5.1"></script>',
        '<script src="app.js?v=0.5.1"></script>\n  <script src="strength-ui.js?v=0.5.1"></script>',
        1,
    )

# Keep the overview consistent with the adaptive programme. The exact set count is
# phase-dependent: first 4 sessions have 2 working sets; main lifts then move to 3.
a = '''<h2>Силовая А</h2>
          <ol class="exercise-list">
            <li><span>Жим ногами</span><b>2–3×8–12</b></li>
            <li><span>Наклонный жим гантелей</span><b>2–3×8–12</b></li>
            <li><span>Тяга верхнего блока</span><b>2–3×8–12</b></li>
            <li><span>Горизонтальная тяга</span><b>2–3×8–12</b></li>
            <li><span>Разведения гантелей в стороны</span><b>2×12–20</b></li>
            <li><span>Мёртвый жук</span><b>2×8–12/сторона</b></li>
          </ol>'''
b = '''<h2>Силовая Б</h2>
          <ol class="exercise-list">
            <li><span>Ягодичный мост</span><b>2–3×8–12</b></li>
            <li><span>Выпады назад</span><b>2×8–12/нога</b></li>
            <li><span>Тяга гантелей с опорой грудью</span><b>2–3×8–12</b></li>
            <li><span>Отжимания с прогрессией</span><b>2–3×10–15</b></li>
            <li><span>Задняя дельта</span><b>2×12–20</b></li>
            <li><span>Боковая планка</span><b>2×25–45 сек/сторона</b></li>
          </ol>'''
text = re.sub(r'<h2>Силовая А</h2>\s*<ol class="exercise-list">.*?</ol>', a, text, count=1, flags=re.S)
text = re.sub(r'<h2>Силовая Б</h2>\s*<ol class="exercise-list">.*?</ol>', b, text, count=1, flags=re.S)
old_logic = "Дни можно переставлять под беговой план тренера. Важна логика: силовые ставим рядом со спокойными пробежками, а не перед интервалами и длительной."
new_logic = old_logic + " Первые 4 силовые — по 2 рабочих подхода; затем основные упражнения переходят на 3 подхода. Точное задание всегда показывает карточка следующей тренировки."
if new_logic not in text:
    text = text.replace(old_logic, new_logic)
p.write_text(text, encoding="utf-8")

# Serve the standalone UI assets and align the backend version.
p = Path("backend/main.py")
text = p.read_text(encoding="utf-8")
text = text.replace('version="0.4.1"', 'version="0.5.1"')
text = text.replace('version="0.5.0"', 'version="0.5.1"')
text = text.replace('"version":"0.4.1"', '"version":"0.5.1"')
text = text.replace('"version":"0.5.0"', '"version":"0.5.1"')
if '@app.get("/strength-ui.js")' not in text:
    anchor = '@app.get("/body-ui.js")\ndef body_ui_js() -> FileResponse:\n'
    routes = '''@app.get("/strength-ui.js")
def strength_ui_js() -> FileResponse:
    return FileResponse(ROOT/"strength-ui.js", media_type="application/javascript", headers={"Cache-Control": "no-store"})


@app.get("/strength-ui.css")
def strength_ui_css() -> FileResponse:
    return FileResponse(ROOT/"strength-ui.css", media_type="text/css", headers={"Cache-Control": "no-store"})


'''
    if anchor in text:
        text = text.replace(anchor, routes + anchor, 1)
    else:
        text += "\n\n" + routes
p.write_text(text, encoding="utf-8")
