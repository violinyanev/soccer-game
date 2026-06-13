from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import Match, Prediction

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse("/dashboard", status_code=302)
    return RedirectResponse("/login", status_code=302)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    user_id = user["user_id"]

    # Fetch all matches ordered by datetime
    matches = (
        db.query(Match)
        .order_by(Match.match_datetime)
        .all()
    )

    # Fetch user's predictions keyed by match_id
    preds = db.query(Prediction).filter(Prediction.user_id == user_id).all()
    pred_map = {p.match_id: p for p in preds}

    # Group matches by date (UTC date)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for m in matches:
        date_key = m.match_datetime.strftime("%Y-%m-%d")
        prediction = pred_map.get(m.id)
        grouped[date_key].append(
            {
                "match": m,
                "prediction": prediction,
                "can_predict": m.status == "SCHEDULED",
            }
        )

    # Sort date keys
    sorted_dates = sorted(grouped.keys())
    match_groups = [(date, grouped[date]) for date in sorted_dates]

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "match_groups": match_groups,
            "now": datetime.utcnow(),
        },
    )
