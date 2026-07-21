"""Authentication routes for PhishGuard — Register, Login, Logout, Profile."""

import sqlite3
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from database.db import _get_conn

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


def _create_users_table():
    """Create users table if it doesn't exist."""
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT NOT NULL,
                email           TEXT UNIQUE NOT NULL,
                password_hash   TEXT NOT NULL,
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_login      DATETIME,
                is_active       BOOLEAN DEFAULT 1
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        conn.commit()
    finally:
        conn.close()


def _get_user_by_email(email):
    """Fetch user by email."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id, name, email, password_hash FROM users WHERE email = ? AND is_active = 1",
            (email,),
        ).fetchone()
    finally:
        conn.close()
    return row


def _create_user(name, email, password):
    """Create a new user."""
    conn = _get_conn()
    try:
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, generate_password_hash(password)),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def _update_last_login(user_id):
    """Update last login timestamp for a user."""
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
            (user_id,),
        )
        conn.commit()
    finally:
        conn.close()


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """User registration."""
    if session.get('user_id'):
        return redirect(url_for('profile'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Validation
        if not all([name, email, password, confirm_password]):
            flash('All fields are required.', 'error')
            return render_template('auth/register.html')

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('auth/register.html')

        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('auth/register.html')

        try:
            _create_user(name, email, password)
            flash('Account created! Please sign in.', 'success')
            return redirect(url_for('auth.login'))
        except sqlite3.IntegrityError:
            flash('Email already registered.', 'error')
            return render_template('auth/register.html')

    return render_template('auth/register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login."""
    if session.get('user_id'):
        return redirect(url_for('profile'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        user = _get_user_by_email(email)
        if not user or not check_password_hash(user['password_hash'], password):
            flash('Invalid email or password.', 'error')
            return render_template('auth/login.html')

        session['user_id'] = user['id']
        session['user_name'] = user['name']
        _update_last_login(user['id'])
        flash(f'Welcome back, {user["name"]}!', 'success')
        return redirect(url_for('profile'))

    return render_template('auth/login.html')


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """User logout."""
    session.clear()
    flash('You have been signed out.', 'success')
    return redirect(url_for('landing'))
