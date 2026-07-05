"""
Reproduction for the 'zero points for everyone' bug.

Scenario (real case: Portugal 2-1 Croatia, match id 84):
  1. A knockout match first finishes as a draw (1-1) -> every non-draw
     prediction is correctly scored 0.
  2. After extra time the API corrects the final score to 2-1 -> an exact
     2-1 prediction must now score 3.

Before the fix, sync only scored predictions whose points_awarded was NULL,
so the corrected score was never re-scored and the exact prediction stayed 0.
"""
import os
import tempfile

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.sqlite")
os.environ["FOOTBALL_API_KEY"] = "test"

import database  # noqa: E402
import football_api  # noqa: E402
from models import Match, Prediction, User  # noqa: E402

database.init_db()

EXT_ID = 999


def _api_match(status, home, away):
    return {
        "id": EXT_ID,
        "homeTeam": {"name": "Portugal"},
        "awayTeam": {"name": "Croatia"},
        "utcDate": "2026-07-02T23:00:00Z",
        "status": status,
        "score": {"fullTime": {"home": home, "away": away}},
    }


# Seed a user, a scheduled match and an exact 2-1 prediction.
db = database.SessionLocal()
db.add(User(username="Violin"))
match = Match(external_id=EXT_ID, home_team="Portugal", away_team="Croatia",
              match_datetime=football_api._parse_datetime("2026-07-02T23:00:00Z"),
              status="SCHEDULED")
db.add(match)
db.flush()
user = db.query(User).first()
db.add(Prediction(user_id=user.id, match_id=match.id,
                  predicted_home=2, predicted_away=1, predicted_result="H"))
db.commit()
db.close()

# Sync #1: match finishes as a draw -> the 2-1 prediction correctly scores 0.
football_api.fetch_matches = lambda: [_api_match("FINISHED", 1, 1)]
football_api.sync_matches()

db = database.SessionLocal()
pred = db.query(Prediction).first()
assert pred.points_awarded == 0, f"after draw expected 0, got {pred.points_awarded}"
db.close()

# Sync #2: score is corrected to 2-1 -> the exact prediction must now score 3.
football_api.fetch_matches = lambda: [_api_match("FINISHED", 2, 1)]
football_api.sync_matches()

db = database.SessionLocal()
pred = db.query(Prediction).first()
db.close()

assert pred.points_awarded == 3, (
    f"BUG: corrected 2-1 score not re-scored; expected 3, got {pred.points_awarded}"
)
print("OK: corrected score re-scored to 3 points")
