import os
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db, AVATAR_DIR
from football_api import score_prediction, sync_matches
from models import Match, Prediction, User

# Accepted avatar uploads: content-type -> file extension.
ALLOWED_IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
MAX_AVATAR_BYTES = 5 * 1024 * 1024  # 5 MB

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _require_admin(request: Request):
    user = get_current_user(request)
    if not user or not user.get("is_admin"):
        return None
    return user


@router.get("/leaderboard", response_class=HTMLResponse)
async def leaderboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    # Aggregate points and correct predictions per user
    correct_expr = func.sum(
        case((Prediction.points_awarded > 0, 1), else_=0)
    )
    total_pts_expr = func.coalesce(func.sum(Prediction.points_awarded), 0)

    rows = (
        db.query(
            User.id.label("user_id"),
            User.username,
            User.avatar_filename.label("avatar"),
            total_pts_expr.label("total_points"),
            correct_expr.label("correct_predictions"),
        )
        .outerjoin(Prediction, Prediction.user_id == User.id)
        .group_by(User.id)
        .order_by(total_pts_expr.desc(), correct_expr.desc())
        .all()
    )

    return templates.TemplateResponse(
        "leaderboard.html",
        {"request": request, "user": user, "rows": rows},
    )


@router.get("/admin", response_class=HTMLResponse)
async def admin_get(request: Request, db: Session = Depends(get_db)):
    admin = _require_admin(request)
    if not admin:
        return RedirectResponse("/dashboard", status_code=302)

    matches = db.query(Match).order_by(Match.match_datetime).all()

    # Player participation: who has predicted, and how many open matches they
    # still have left. Picks themselves are not shown, to avoid spoilers.
    scheduled_ids = [m.id for m in matches if m.status == "SCHEDULED"]
    scheduled_count = len(scheduled_ids)

    total_counts = dict(
        db.query(Prediction.user_id, func.count(Prediction.id))
        .group_by(Prediction.user_id)
        .all()
    )
    open_counts = {}
    if scheduled_ids:
        open_counts = dict(
            db.query(Prediction.user_id, func.count(Prediction.id))
            .filter(Prediction.match_id.in_(scheduled_ids))
            .group_by(Prediction.user_id)
            .all()
        )

    users = db.query(User).order_by(User.username).all()
    participation = [
        {
            "user_id": u.id,
            "username": u.username,
            "avatar": u.avatar_filename,
            "predictions": total_counts.get(u.id, 0),
            "open_remaining": scheduled_count - open_counts.get(u.id, 0),
        }
        for u in users
    ]

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "user": admin,
            "matches": matches,
            "participation": participation,
            "scheduled_count": scheduled_count,
            "message": request.query_params.get("message"),
        },
    )


@router.post("/admin/sync")
async def admin_sync(request: Request):
    admin = _require_admin(request)
    if not admin:
        return RedirectResponse("/dashboard", status_code=302)

    result = sync_matches()
    msg = (
        f"Sync complete — fetched {result.get('matches_fetched', 0)} matches, "
        f"created {result.get('created', 0)}, updated {result.get('updated', 0)}, "
        f"points awarded to {result.get('points_awarded', 0)} predictions."
        if result.get("status") == "ok"
        else f"Sync failed: {result.get('error', 'unknown error')}"
    )
    return RedirectResponse(f"/admin?message={msg}", status_code=302)


@router.post("/admin/match")
async def admin_upsert_match(
    request: Request,
    match_id: str = Form(""),
    external_id: int = Form(...),
    home_team: str = Form(...),
    away_team: str = Form(...),
    match_datetime: str = Form(...),
    status: str = Form("SCHEDULED"),
    home_score: str = Form(""),
    away_score: str = Form(""),
    db: Session = Depends(get_db),
):
    admin = _require_admin(request)
    if not admin:
        return RedirectResponse("/dashboard", status_code=302)

    try:
        dt = datetime.fromisoformat(match_datetime)
    except ValueError:
        return RedirectResponse("/admin?message=Invalid+datetime+format", status_code=302)

    hs = int(home_score) if home_score.strip() else None
    aws = int(away_score) if away_score.strip() else None

    result = None
    if status == "FINISHED" and hs is not None and aws is not None:
        if hs > aws:
            result = "H"
        elif aws > hs:
            result = "A"
        else:
            result = "D"

    if match_id:
        match = db.query(Match).filter(Match.id == int(match_id)).first()
        if match:
            match.external_id = external_id
            match.home_team = home_team
            match.away_team = away_team
            match.match_datetime = dt
            match.status = status
            match.home_score = hs
            match.away_score = aws
            match.result = result
    else:
        existing = db.query(Match).filter(Match.external_id == external_id).first()
        if existing:
            return RedirectResponse(
                "/admin?message=Match+with+that+external+ID+already+exists", status_code=302
            )
        match = Match(
            external_id=external_id,
            home_team=home_team,
            away_team=away_team,
            match_datetime=dt,
            status=status,
            home_score=hs,
            away_score=aws,
            result=result,
        )
        db.add(match)

    # Award points if match is now FINISHED with a result
    if status == "FINISHED" and result:
        match_obj = match
        db.flush()
        preds = (
            db.query(Prediction)
            .filter(
                Prediction.match_id == match_obj.id,
                Prediction.points_awarded.is_(None),
            )
            .all()
        )
        for pred in preds:
            pred.points_awarded = score_prediction(
                pred.predicted_home, pred.predicted_away, hs, aws
            )

    db.commit()
    return RedirectResponse("/admin?message=Match+saved+successfully", status_code=302)


@router.post("/admin/avatar")
async def admin_upload_avatar(
    request: Request,
    user_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    admin = _require_admin(request)
    if not admin:
        return RedirectResponse("/dashboard", status_code=302)

    ext = ALLOWED_IMAGE_TYPES.get(file.content_type)
    if not ext:
        return RedirectResponse(
            "/admin?message=Unsupported+image+type+(use+PNG,+JPG,+WEBP+or+GIF)",
            status_code=302,
        )

    data = await file.read()
    if len(data) > MAX_AVATAR_BYTES:
        return RedirectResponse("/admin?message=Image+too+large+(max+5+MB)", status_code=302)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return RedirectResponse("/admin?message=Unknown+user", status_code=302)

    os.makedirs(AVATAR_DIR, exist_ok=True)
    # Remove any previous avatar for this user (extension may differ).
    for old in ALLOWED_IMAGE_TYPES.values():
        prev = os.path.join(AVATAR_DIR, f"{user_id}{old}")
        if os.path.exists(prev):
            os.remove(prev)

    filename = f"{user_id}{ext}"
    with open(os.path.join(AVATAR_DIR, filename), "wb") as fh:
        fh.write(data)

    user.avatar_filename = filename
    db.commit()
    return RedirectResponse(
        f"/admin?message=Picture+updated+for+{user.username}", status_code=302
    )
