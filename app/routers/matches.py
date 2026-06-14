import os
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db, AVATAR_DIR
from models import Match, Prediction, User

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

    # One-time welcome screen on first login.
    db_user = db.query(User).filter(User.id == user_id).first()
    if db_user and not db_user.has_seen_welcome:
        return RedirectResponse("/welcome", status_code=302)

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

    # Split into past dates (before today, UTC) and current/upcoming ones, so the
    # template can collapse the past matches behind a toggle.
    today_key = datetime.utcnow().strftime("%Y-%m-%d")
    past_groups, upcoming_groups = [], []
    for date in sorted(grouped.keys()):
        (past_groups if date < today_key else upcoming_groups).append((date, grouped[date]))
    past_match_count = sum(len(entries) for _, entries in past_groups)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "upcoming_groups": upcoming_groups,
            "past_groups": past_groups,
            "past_match_count": past_match_count,
            "now": datetime.utcnow(),
        },
    )


@router.get("/avatar/{user_id}")
async def avatar(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not get_current_user(request):
        return RedirectResponse("/login", status_code=302)
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user or not db_user.avatar_filename:
        return RedirectResponse("/login", status_code=404)
    path = os.path.join(AVATAR_DIR, db_user.avatar_filename)
    if not os.path.exists(path):
        return RedirectResponse("/login", status_code=404)
    return FileResponse(path)


@router.get("/welcome", response_class=HTMLResponse)
async def welcome_get(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    db_user = db.query(User).filter(User.id == user["user_id"]).first()
    return templates.TemplateResponse(
        "welcome.html",
        {"request": request, "user": user, "player": db_user},
    )


@router.post("/welcome")
async def welcome_ack(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    db_user = db.query(User).filter(User.id == user["user_id"]).first()
    if db_user:
        db_user.has_seen_welcome = True
        db.commit()
    return RedirectResponse("/dashboard", status_code=302)
