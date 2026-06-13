from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from auth import get_current_user
from database import get_db
from models import Match, Prediction

router = APIRouter()

VALID_RESULTS = {"H", "A", "D"}


@router.post("/predictions")
async def submit_prediction(
    request: Request,
    match_id: int = Form(...),
    predicted_result: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    if predicted_result not in VALID_RESULTS:
        return RedirectResponse("/dashboard?error=invalid_prediction", status_code=302)

    match = db.query(Match).filter(Match.id == match_id).first()
    if not match or match.status != "SCHEDULED":
        return RedirectResponse("/dashboard?error=match_not_available", status_code=302)

    user_id = user["user_id"]
    existing = (
        db.query(Prediction)
        .filter(Prediction.user_id == user_id, Prediction.match_id == match_id)
        .first()
    )

    if existing:
        existing.predicted_result = predicted_result
    else:
        pred = Prediction(
            user_id=user_id,
            match_id=match_id,
            predicted_result=predicted_result,
        )
        db.add(pred)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()

    return RedirectResponse("/dashboard", status_code=302)
