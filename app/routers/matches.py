import os
from collections import defaultdict
from datetime import datetime, timedelta

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

    now = datetime.utcnow()

    # Voting is open only while the match is SCHEDULED *and* kick-off is still in
    # the future — once a match starts, predictions are locked even if the API
    # status hasn't flipped to IN_PLAY yet (the sync only runs every 30 min).
    def is_open(m):
        return m.status == "SCHEDULED" and m.match_datetime > now

    # Fetch user's predictions keyed by match_id
    preds = db.query(Prediction).filter(Prediction.user_id == user_id).all()
    pred_map = {p.match_id: p for p in preds}

    # Predictions of *all* players for matches that are no longer open, so the
    # template can reveal everyone's votes once a match has started.
    locked_ids = [m.id for m in matches if not is_open(m)]
    others_map: dict[int, list[dict]] = defaultdict(list)
    if locked_ids:
        rows = (
            db.query(Prediction, User)
            .join(User, User.id == Prediction.user_id)
            .filter(Prediction.match_id.in_(locked_ids))
            .order_by(User.username)
            .all()
        )
        for pred, u in rows:
            if pred.predicted_home is None:
                continue
            others_map[pred.match_id].append(
                {
                    "user_id": u.id,
                    "username": u.username,
                    "avatar": u.avatar_filename,
                    "predicted_home": pred.predicted_home,
                    "predicted_away": pred.predicted_away,
                    "points_awarded": pred.points_awarded,
                }
            )

    # Group matches by date (UTC date)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for m in matches:
        date_key = m.match_datetime.strftime("%Y-%m-%d")
        grouped[date_key].append(
            {
                "match": m,
                "prediction": pred_map.get(m.id),
                "can_predict": is_open(m),
                "others": others_map.get(m.id, []),
            }
        )

    # Hide matches older than 3 days behind a toggle; keep the last 3 days and all
    # upcoming matches visible.
    cutoff_key = (now - timedelta(days=3)).strftime("%Y-%m-%d")
    old_groups, visible_groups = [], []
    for date in sorted(grouped.keys()):
        (old_groups if date < cutoff_key else visible_groups).append((date, grouped[date]))
    old_match_count = sum(len(entries) for _, entries in old_groups)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "me": db_user,
            "visible_groups": visible_groups,
            "old_groups": old_groups,
            "old_match_count": old_match_count,
            "now": now,
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
