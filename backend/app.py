from __future__ import annotations

from fastapi.responses import Response

from backend.main import app
from backend.strength_api import router as strength_router

app.include_router(strength_router)

# Serve the existing frontend plus the adaptive strength extension without
# duplicating the whole HTML or main JS bundle.
app.router.routes = [
    r for r in app.router.routes
    if getattr(r, "path", None) not in {"/app.js", "/styles.css"}
]


@app.get("/app.js")
def combined_js() -> Response:
    root = __import__("pathlib").Path(__file__).resolve().parent.parent
    content = (root / "app.js").read_text(encoding="utf-8") + "\n\n" + (root / "strength-ui.js").read_text(encoding="utf-8")
    return Response(content, media_type="application/javascript", headers={"Cache-Control": "no-store"})


@app.get("/styles.css")
def combined_css() -> Response:
    root = __import__("pathlib").Path(__file__).resolve().parent.parent
    content = (root / "styles.css").read_text(encoding="utf-8") + "\n\n" + (root / "strength-ui.css").read_text(encoding="utf-8")
    return Response(content, media_type="text/css", headers={"Cache-Control": "no-store"})
