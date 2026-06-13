from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from auth import (
    clear_auth_cookie,
    hash_password,
    set_auth_cookie,
    verify_password,
)
from database import get_db
from models import User

router = APIRouter()
templates = Jinja2Templates(directory="templates")

USERS = [
    "Boryana", "Violin", "Guido", "Ivanka",
    "Veselin", "Dilyana", "Dora", "Asparuh",
]


@router.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    from auth import get_current_user
    if get_current_user(request):
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse(
        "login.html", {"request": request, "users": USERS, "error": None}
    )


@router.post("/login")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "users": USERS, "error": "Unknown user."},
            status_code=400,
        )

    # First-time login: password not yet set
    if user.password_hash is None:
        return templates.TemplateResponse(
            "set_password.html",
            {
                "request": request,
                "username": username,
                "error": None,
            },
        )

    # Normal login
    if not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "users": USERS, "error": "Incorrect password."},
            status_code=400,
        )

    response = RedirectResponse("/dashboard", status_code=302)
    set_auth_cookie(response, user.id, user.username, user.is_admin)
    return response


@router.get("/set-password", response_class=HTMLResponse)
async def set_password_get(request: Request, username: str = ""):
    return templates.TemplateResponse(
        "set_password.html", {"request": request, "username": username, "error": None}
    )


@router.post("/set-password")
async def set_password_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    if password != confirm_password:
        return templates.TemplateResponse(
            "set_password.html",
            {"request": request, "username": username, "error": "Passwords do not match."},
            status_code=400,
        )
    if len(password) < 6:
        return templates.TemplateResponse(
            "set_password.html",
            {
                "request": request,
                "username": username,
                "error": "Password must be at least 6 characters.",
            },
            status_code=400,
        )

    user = db.query(User).filter(User.username == username).first()
    if not user:
        return templates.TemplateResponse(
            "set_password.html",
            {"request": request, "username": username, "error": "Unknown user."},
            status_code=400,
        )
    if user.password_hash is not None:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "users": USERS,
                "error": "Password already set. Please log in normally.",
            },
            status_code=400,
        )

    user.password_hash = hash_password(password)
    db.commit()

    response = RedirectResponse("/dashboard", status_code=302)
    set_auth_cookie(response, user.id, user.username, user.is_admin)
    return response


@router.post("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=302)
    clear_auth_cookie(response)
    return response
