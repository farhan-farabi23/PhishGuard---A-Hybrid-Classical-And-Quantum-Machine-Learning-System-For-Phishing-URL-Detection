"""Profile and dashboard routes for PhishGuard."""

from flask import Blueprint, render_template, request, redirect, url_for, session
from datetime import datetime, timedelta
from database.queries import (
    get_user_by_id,
    get_user_scan_stats,
    get_user_recent_scans,
    get_user_verdict_summary,
    get_scan_detail,
)

profile_bp = Blueprint('profile', __name__)


def _require_auth():
    """Redirect to login if not authenticated."""
    if not session.get('user_id'):
        return None
    return session.get('user_id')


def _parse_date(val):
    """Parse ISO date string, return None if invalid."""
    try:
        datetime.strptime(val, "%Y-%m-%d")
        return val
    except (ValueError, TypeError):
        return None


def _get_date_presets(today):
    """Get common date filter presets."""
    this_month_from = today.replace(day=1).isoformat()
    this_month_to = today.isoformat()
    last_7_from = (today - timedelta(days=7)).isoformat()
    last_30_from = (today - timedelta(days=30)).isoformat()

    return {
        "all_time": {"label": "All Time", "from": None, "to": None},
        "this_month": {"label": "This Month", "from": this_month_from, "to": this_month_to},
        "last_7": {"label": "Last 7 Days", "from": last_7_from, "to": today.isoformat()},
        "last_30": {"label": "Last 30 Days", "from": last_30_from, "to": today.isoformat()},
    }


@profile_bp.route('/profile')
def profile():
    """User profile and scan history dashboard."""
    user_id = _require_auth()
    if not user_id:
        return redirect(url_for('auth.login'))

    user = get_user_by_id(user_id)
    if not user:
        return redirect(url_for('auth.logout'))

    # Date filtering
    today = datetime.now().date()
    date_from = _parse_date(request.args.get('date_from'))
    date_to = _parse_date(request.args.get('date_to'))

    # Validate date range
    if date_from and date_to and date_from > date_to:
        from flask import flash
        flash('Start date must be before end date.', 'error')
        date_from = date_to = None

    # Get statistics and scan history
    stats = get_user_scan_stats(user_id, date_from, date_to)
    scans = get_user_recent_scans(user_id, limit=15, date_from=date_from, date_to=date_to)
    verdict_summary = get_user_verdict_summary(user_id, date_from, date_to)
    presets = _get_date_presets(today)

    return render_template(
        'profile.html',
        user=user,
        stats=stats,
        scans=scans,
        verdict_summary=verdict_summary,
        presets=presets,
        date_from=date_from,
        date_to=date_to,
    )


@profile_bp.route('/scan/<int:scan_id>')
def scan_detail(scan_id):
    """View details of a specific scan."""
    user_id = _require_auth()
    if not user_id:
        return redirect(url_for('auth.login'))

    scan = get_scan_detail(scan_id, user_id)
    if not scan:
        from flask import abort
        abort(404)

    user = get_user_by_id(user_id)
    return render_template('scan_detail.html', scan=scan, user=user)
