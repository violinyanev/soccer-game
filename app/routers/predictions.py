from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from auth import get_current_user
from database import get_db
from football_api import compute_result
from models import Match, Prediction

router = APIRouter()

MAX_GOALS = 99


@router.post("/predictions")
async def submit_prediction(
    request: Request,
    match_id: int = Form(...),
    predicted_home: int = Form(...),
    predicted_away: int = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    if not (0 <= predicted_home <= MAX_GOALS and 0 <= predicted_away <= MAX_GOALS):
        return RedirectResponse("/dashboard?error=invalid_prediction", status_code=302)

    match = db.query(Match).filter(Match.id == match_id).first()
    # Reject if the match doesn't exist, isn't scheduled, or has already kicked off.
    if not match or match.status != "SCHEDULED" or match.match_datetime <= datetime.utcnow():
        return RedirectResponse("/dashboard?error=match_not_available", status_code=302)

    predicted_result = compute_result(predicted_home, predicted_away)

    user_id = user["user_id"]
    existing = (
        db.query(Prediction)
        .filter(Prediction.user_id == user_id, Prediction.match_id == match_id)
        .first()
    )

    if existing:
        existing.predicted_home = predicted_home
        existing.predicted_away = predicted_away
        existing.predicted_result = predicted_result
    else:
        pred = Prediction(
            user_id=user_id,
            match_id=match_id,
            predicted_home=predicted_home,
            predicted_away=predicted_away,
            predicted_result=predicted_result,
        )
        db.add(pred)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()

    return RedirectResponse("/dashboard", status_code=302)
