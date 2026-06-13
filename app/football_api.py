"""
football-data.org API client and match sync logic.
"""

import logging
import os
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Match, Prediction

logger = logging.getLogger(__name__)

API_BASE = "https://api.football-data.org/v4"
COMPETITION = "WC"
POINTS_CORRECT = 5
POINTS_WRONG = 0

# Normalise the many status strings the API returns into our four buckets
STATUS_MAP = {
    "SCHEDULED": "SCHEDULED",
    "TIMED": "SCHEDULED",
    "IN_PLAY": "IN_PLAY",
    "PAUSED": "IN_PLAY",
    "HALFTIME": "IN_PLAY",
    "EXTRA_TIME": "IN_PLAY",
    "PENALTY_SHOOTOUT": "IN_PLAY",
    "FINISHED": "FINISHED",
    "AWARDED": "FINISHED",
    "POSTPONED": "POSTPONED",
    "SUSPENDED": "POSTPONED",
    "CANCELLED": "POSTPONED",
}


def _api_key() -> str:
    key = os.getenv("FOOTBALL_API_KEY", "")
    if not key:
        logger.warning("FOOTBALL_API_KEY is not set – API calls will fail.")
    return key


def fetch_matches() -> list[dict]:
    """Fetch all WC 2026 matches from football-data.org."""
    url = f"{API_BASE}/competitions/{COMPETITION}/matches"
    headers = {"X-Auth-Token": _api_key()}
    try:
        with httpx.Client(timeout=20) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data.get("matches", [])
    except httpx.HTTPStatusError as exc:
        logger.error("API HTTP error %s: %s", exc.response.status_code, exc.response.text)
        return []
    except Exception as exc:
        logger.error("API request failed: %s", exc)
        return []


def _compute_result(home: int | None, away: int | None) -> str | None:
    if home is None or away is None:
        return None
    if home > away:
        return "H"
    if away > home:
        return "A"
    return "D"


def _parse_datetime(dt_str: str) -> datetime:
    """Parse ISO 8601 string from the API into a naive UTC datetime."""
    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    # Store as naive UTC
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def sync_matches() -> dict:
    """
    Full sync: fetch matches from API, upsert into DB, award points for
    FINISHED matches.  Returns a summary dict for logging / admin display.
    """
    logger.info("Starting match sync …")
    raw_matches = fetch_matches()

    db: Session = SessionLocal()
    created = updated = points_awarded = 0

    try:
        for m in raw_matches:
            ext_id = m["id"]
            home_team = m.get("homeTeam", {}).get("name") or "TBD"
            away_team = m.get("awayTeam", {}).get("name") or "TBD"
            match_dt = _parse_datetime(m["utcDate"])
            raw_status = m.get("status", "SCHEDULED")
            status = STATUS_MAP.get(raw_status, "SCHEDULED")

            score = m.get("score", {})
            full_time = score.get("fullTime", {}) or {}
            home_score = full_time.get("home")
            away_score = full_time.get("away")
            result = _compute_result(home_score, away_score) if status == "FINISHED" else None

            existing = db.query(Match).filter(Match.external_id == ext_id).first()
            if existing is None:
                match = Match(
                    external_id=ext_id,
                    home_team=home_team,
                    away_team=away_team,
                    match_datetime=match_dt,
                    status=status,
                    home_score=home_score,
                    away_score=away_score,
                    result=result,
                )
                db.add(match)
                db.flush()  # get match.id
                created += 1
            else:
                existing.home_team = home_team
                existing.away_team = away_team
                existing.match_datetime = match_dt
                existing.status = status
                existing.home_score = home_score
                existing.away_score = away_score
                existing.result = result
                match = existing
                updated += 1

            # Award points for FINISHED matches with a known result
            if status == "FINISHED" and result:
                preds = (
                    db.query(Prediction)
                    .filter(
                        Prediction.match_id == match.id,
                        Prediction.points_awarded.is_(None),
                    )
                    .all()
                )
                for pred in preds:
                    pred.points_awarded = (
                        POINTS_CORRECT if pred.predicted_result == result else POINTS_WRONG
                    )
                    points_awarded += 1

        db.commit()
        summary = {
            "status": "ok",
            "matches_fetched": len(raw_matches),
            "created": created,
            "updated": updated,
            "points_awarded": points_awarded,
        }
        logger.info("Sync complete: %s", summary)
        return summary

    except Exception as exc:
        db.rollback()
        logger.error("Sync failed: %s", exc, exc_info=True)
        return {"status": "error", "error": str(exc)}
    finally:
        db.close()
