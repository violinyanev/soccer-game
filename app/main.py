import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse

from database import init_db, SessionLocal, AVATAR_DIR
from football_api import sync_matches
from models import User
from routers import auth as auth_router
from routers import matches as matches_router
from routers import predictions as predictions_router
from routers import admin as admin_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

PREDEFINED_USERS = [
    ("Boryana", False),
    ("Violin", True),   # admin
    ("Guido", False),
    ("Ivanka", False),
    ("Veselin", False),
    ("Dilyana", False),
    ("Dora", False),
    ("Asparuh", False),
]


def seed_users():
    db = SessionLocal()
    try:
        for username, is_admin in PREDEFINED_USERS:
            exists = db.query(User).filter(User.username == username).first()
            if not exists:
                db.add(User(username=username, is_admin=is_admin))
        db.commit()
        logger.info("Users seeded.")
    finally:
        db.close()


app = FastAPI(title="⚽ Family World Cup Predictor")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # Convert 307 HTTPExceptions raised by login_required into redirects
    if exc.status_code in (302, 307):
        location = exc.headers.get("Location", "/login")
        return RedirectResponse(url=location, status_code=302)
    raise exc


@app.on_event("startup")
async def startup_event():
    os.makedirs("/app/data", exist_ok=True)
    os.makedirs(AVATAR_DIR, exist_ok=True)
    init_db()
    seed_users()

    # Start background scheduler for automatic sync every 30 minutes
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        sync_matches,
        trigger="interval",
        minutes=30,
        id="sync_matches",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started — syncing matches every 30 minutes.")

    # Run an initial sync on startup (non-blocking best-effort)
    try:
        result = sync_matches()
        logger.info("Initial sync: %s", result)
    except Exception as exc:
        logger.warning("Initial sync failed (will retry in 30 min): %s", exc)


# Include routers
app.include_router(matches_router.router)
app.include_router(auth_router.router)
app.include_router(predictions_router.router)
app.include_router(admin_router.router)
