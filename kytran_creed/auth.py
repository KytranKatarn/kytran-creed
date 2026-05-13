import json
import logging
import os
import urllib.parse
import urllib.request
from functools import wraps

import bcrypt
from flask import flash, redirect, render_template, request, session

_PLATFORM_PUBLIC = os.environ.get("KYTRAN_PLATFORM_URL", "https://platform.kytranempowerment.com")
_PLATFORM_INTERNAL = os.environ.get("KYTRAN_PLATFORM_INTERNAL", "http://192.168.1.200:3000")
_CREED_CLIENT_ID = os.environ.get("CREED_OAUTH_CLIENT_ID", "creed")
_CREED_CLIENT_SECRET = os.environ.get("CREED_OAUTH_SECRET", "creed_cs_k9mx4p2r7n8v3j5q")
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)

from kytran_creed.db import get_db

logger = logging.getLogger(__name__)
login_manager = LoginManager()


class User(UserMixin):
    def __init__(self, id, username, role="viewer", display_name=None, email=None, sso_provider=None):
        self.id = id
        self.username = username
        self.role = role
        self.display_name = display_name or username
        self.email = email
        self.sso_provider = sso_provider

    @property
    def is_admin(self):
        return self.role == "admin"


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            return {"error": "Admin access required"}, 403
        return f(*args, **kwargs)

    return decorated


def setup_required():
    db = get_db()
    try:
        count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        return count == 0
    finally:
        db.close()


def create_admin(username, password):
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    db = get_db()
    try:
        db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, password_hash, "admin"),
        )
        db.commit()
        logger.info("Admin user '%s' created", username)
    finally:
        db.close()


def verify_password(username, password):
    db = get_db()
    try:
        row = db.execute(
            "SELECT id, username, password_hash, role, display_name, email, sso_provider "
            "FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if not row or not row["password_hash"]:
            return None
        if bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
            return User(
                row["id"],
                row["username"],
                row["role"],
                row["display_name"],
                row["email"],
                row["sso_provider"],
            )
        return None
    finally:
        db.close()


@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    try:
        row = db.execute(
            "SELECT id, username, role, display_name, email, sso_provider "
            "FROM users WHERE id = ?",
            (int(user_id),),
        ).fetchone()
        if row:
            return User(
                row["id"],
                row["username"],
                row["role"],
                row["display_name"],
                row["email"],
                row["sso_provider"],
            )
        return None
    finally:
        db.close()


def register_auth_routes(app):
    login_manager.init_app(app)
    login_manager.login_view = "login"

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            user = verify_password(username, password)
            if user:
                login_user(user)
                next_page = request.args.get("next", "/")
                return redirect(next_page)
            flash("Invalid username or password", "error")
        return render_template("login.html")

    @app.route("/auth/kytran/login")
    def kytran_sso_login():
        session["sso_next"] = request.args.get("next", "/")
        callback = request.url_root.rstrip("/") + "/auth/kytran/callback"
        authorize_url = (
            f"{_PLATFORM_PUBLIC}/oauth/authorize"
            f"?client_id={urllib.parse.quote(_CREED_CLIENT_ID)}"
            f"&redirect_uri={urllib.parse.quote(callback)}"
            f"&response_type=code"
        )
        return redirect(authorize_url)

    @app.route("/auth/kytran/callback")
    def kytran_sso_callback():
        code = request.args.get("code")
        if not code:
            flash("SSO login failed — no code returned", "error")
            return redirect("/login")
        callback = request.url_root.rstrip("/") + "/auth/kytran/callback"
        try:
            payload = urllib.parse.urlencode({
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": callback,
                "client_id": _CREED_CLIENT_ID,
                "client_secret": _CREED_CLIENT_SECRET,
            }).encode()
            req = urllib.request.Request(
                f"{_PLATFORM_INTERNAL}/oauth/token",
                data=payload,
                method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                token_data = json.loads(resp.read())
        except Exception:
            logger.exception("CREED SSO token exchange failed")
            flash("SSO login failed — could not reach platform", "error")
            return redirect("/login")

        user_info = token_data.get("user") or {}
        username = user_info.get("username") or "sso_user"
        email = user_info.get("email") or ""
        is_owner = user_info.get("is_owner", False)
        platform_role = user_info.get("role", "viewer")
        creed_role = "admin" if (is_owner or platform_role == "admin") else "viewer"

        db = get_db()
        try:
            existing = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
            if existing:
                db.execute(
                    "UPDATE users SET email = ?, role = ?, sso_provider = 'kytran' WHERE username = ?",
                    (email, creed_role, username),
                )
                user_id = existing["id"]
            else:
                db.execute(
                    "INSERT INTO users (username, role, email, display_name, sso_provider) VALUES (?, ?, ?, ?, 'kytran')",
                    (username, creed_role, email, username.title()),
                )
                user_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.commit()
            user = User(user_id, username, creed_role, email=email)
            login_user(user)
            return redirect(session.pop("sso_next", "/"))
        except Exception:
            logger.exception("CREED SSO user upsert failed")
            flash("SSO login error — please try again", "error")
            return redirect("/login")
        finally:
            db.close()

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect("/login")

    @app.route("/settings", methods=["GET", "POST"])
    @login_required
    def settings():
        if request.method == "POST":
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")

            if not current_password or not new_password:
                flash("All fields are required", "error")
            elif new_password != confirm_password:
                flash("New passwords do not match", "error")
            else:
                db = get_db()
                try:
                    row = db.execute(
                        "SELECT password_hash FROM users WHERE id = ?",
                        (current_user.id,),
                    ).fetchone()
                    if not row or not bcrypt.checkpw(
                        current_password.encode(), row["password_hash"].encode()
                    ):
                        flash("Current password is incorrect", "error")
                    else:
                        new_hash = bcrypt.hashpw(
                            new_password.encode(), bcrypt.gensalt()
                        ).decode()
                        db.execute(
                            "UPDATE users SET password_hash = ? WHERE id = ?",
                            (new_hash, current_user.id),
                        )
                        db.commit()
                        flash("Password changed successfully", "success")
                finally:
                    db.close()
        return render_template("settings.html")

    @app.route("/setup", methods=["GET", "POST"])
    def setup():
        if not setup_required():
            return redirect("/")
        if request.method == "POST":
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            confirm = request.form.get("confirm_password", "")
            if not username or not password:
                flash("Username and password are required", "error")
            elif password != confirm:
                flash("Passwords do not match", "error")
            else:
                create_admin(username, password)
                flash("Admin account created. Please log in.", "success")
                return redirect("/login")
        return render_template("setup.html")
