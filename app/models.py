from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=True)  # None = not yet set
    is_admin = Column(Boolean, default=False, nullable=False)

    predictions = relationship("Prediction", back_populates="user")


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(Integer, unique=True, nullable=False, index=True)
    home_team = Column(String, nullable=False)
    away_team = Column(String, nullable=False)
    match_datetime = Column(DateTime, nullable=False)
    # SCHEDULED / IN_PLAY / FINISHED / POSTPONED
    status = Column(String, default="SCHEDULED", nullable=False)
    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)
    # H = home wins, A = away wins, D = draw, None = not decided
    result = Column(String, nullable=True)

    predictions = relationship("Prediction", back_populates="match")


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    # Players predict an exact scoreline; the tendency (H/A/D) is derived from it.
    predicted_home = Column(Integer, nullable=True)
    predicted_away = Column(Integer, nullable=True)
    predicted_result = Column(String, nullable=True)  # H / A / D, derived from the scoreline
    points_awarded = Column(Integer, nullable=True)  # None until match finished

    user = relationship("User", back_populates="predictions")
    match = relationship("Match", back_populates="predictions")

    __table_args__ = (
        UniqueConstraint("user_id", "match_id", name="uq_user_match"),
    )
