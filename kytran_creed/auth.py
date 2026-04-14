import logging
from functools import wraps

import bcrypt
from flask import flash, redirect, render_template, request, session
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
