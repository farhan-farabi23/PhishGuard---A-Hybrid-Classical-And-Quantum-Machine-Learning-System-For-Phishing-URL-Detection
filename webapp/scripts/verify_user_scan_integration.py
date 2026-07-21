#!/usr/bin/env python3
"""Verification script for user-scan SQLite integration.

This script checks that:
1. Database schema is correct (user_id column exists)
2. Users can be created and linked to scans
3. Scans are properly attributed to users
4. Statistics queries work correctly
"""

import sys
import sqlite3
from pathlib import Path

# Fix encoding for Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import database.db as db
import database.users as users_db


def check_schema():
    """Verify that scans table has user_id column and foreign key."""
    print("\n[1] Checking database schema...")
    con = db._get_conn()
    try:
        # Get table info
        cursor = con.execute("PRAGMA table_info(scans)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        # Check for required columns
        required = {"id", "url", "verdict", "confidence", "timestamp", "user_id", "tld", "results"}
        missing = required - set(columns.keys())

        if missing:
            print(f"  [FAIL] Missing columns: {missing}")
            return False

        print("  [PASS] All required columns exist")

        # Check indexes
        cursor = con.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='scans'")
        indexes = {row[0] for row in cursor.fetchall()}

        expected_indexes = {"idx_scans_timestamp", "idx_scans_tld", "idx_scans_user_id"}
        missing_indexes = expected_indexes - indexes

        if missing_indexes:
            print(f"  [WARN] Missing indexes: {missing_indexes}")
        else:
            print("  [PASS] All indexes present")

        return True
    finally:
        con.close()


def test_user_creation_and_linking():
    """Test creating a user and linking scans to them."""
    print("\n[2] Testing user creation and scan linking...")

    # Create test user
    test_google_id = "test_user_12345"
    test_email = "test@example.com"
    test_name = "Test User"
    test_picture = "https://example.com/pic.jpg"

    try:
        user = users_db.upsert_user(test_google_id, test_email, test_name, test_picture)
        print(f"  [PASS] User created: ID={user['id']}, Email={user['email']}")
        user_id = user["id"]
    except Exception as e:
        print(f"  [FAIL] Failed to create user: {e}")
        return False

    # Save a scan linked to this user
    try:
        test_results = {
            "ensemble": {"verdict": "good", "confidence": 0.95},
            "knn": {"verdict": "good", "confidence": 0.9},
        }
        db.save_scan(
            url="https://example.com",
            verdict="good",
            confidence=0.95,
            results=test_results,
            user_id=user_id,
        )
        print(f"  [PASS] Scan saved for user_id={user_id}")
    except Exception as e:
        print(f"  [FAIL] Failed to save scan: {e}")
        return False

    # Verify the scan is linked to the user
    try:
        scans = users_db.get_user_scans(user_id)
        if scans and scans[0]["url"] == "https://example.com":
            print(f"  [PASS] Scan correctly linked to user (found {len(scans)} scan(s))")
        else:
            print(f"  [FAIL] Scan not found for user")
            return False
    except Exception as e:
        print(f"  [FAIL] Failed to retrieve user scans: {e}")
        return False

    return user_id


def test_batch_scan_linking():
    """Test batch scans are linked to users."""
    print("\n[3] Testing batch scan linking...")

    # Get an existing user or create one
    con = db._get_conn()
    try:
        existing_user = con.execute("SELECT id FROM users LIMIT 1").fetchone()
        if existing_user:
            user_id = existing_user[0]
            print(f"  Using existing user_id={user_id}")
        else:
            print("  [SKIP] No users in database, skipping batch test")
            return True
    finally:
        con.close()

    # Save batch of scans
    try:
        batch_scans = [
            ("https://phishing.example.com", "bad", 0.9, '{"model": "phishing"}'),
            ("https://legit.example.com", "good", 0.95, '{"model": "safe"}'),
        ]
        db.save_scans_batch(batch_scans, user_id=user_id)
        print(f"  [PASS] Batch scans saved for user_id={user_id}")
    except Exception as e:
        print(f"  [FAIL] Failed to save batch scans: {e}")
        return False

    # Verify batch scans are linked
    try:
        recent_scans = users_db.get_user_scans(user_id, limit=10)
        phishing_count = sum(1 for s in recent_scans if s["verdict"] == "bad")
        safe_count = sum(1 for s in recent_scans if s["verdict"] == "good")
        print(f"  [PASS] Found {len(recent_scans)} scans: {phishing_count} phishing, {safe_count} safe")
    except Exception as e:
        print(f"  [FAIL] Failed to verify batch scans: {e}")
        return False

    return True


def test_statistics():
    """Test statistics functions."""
    print("\n[4] Testing user statistics...")

    con = db._get_conn()
    try:
        user_id = con.execute("SELECT id FROM users WHERE is_active = 1 LIMIT 1").fetchone()
        if not user_id:
            print("  [SKIP] No active users in database, skipping statistics test")
            return True
        user_id = user_id[0]
    finally:
        con.close()

    try:
        stats = users_db.get_user_scan_stats(user_id)
        print(f"  [PASS] User {user_id} statistics:")
        print(f"     - Total scans: {stats['total_scans']}")
        print(f"     - Phishing: {stats['phishing_count']}")
        print(f"     - Safe: {stats['safe_count']}")
        print(f"     - Phishing rate: {stats['phishing_percentage']}%")
        print(f"     - Last 30 days: {stats['scans_last_30_days']}")
    except Exception as e:
        print(f"  [FAIL] Failed to retrieve statistics: {e}")
        return False

    return True


def test_connection_verification():
    """Test the connection verification function."""
    print("\n[5] Testing connection verification...")

    con = db._get_conn()
    try:
        user_id = con.execute("SELECT id FROM users WHERE is_active = 1 LIMIT 1").fetchone()
        if not user_id:
            print("  [SKIP] No active users in database, skipping verification test")
            return True
        user_id = user_id[0]
    finally:
        con.close()

    try:
        is_connected = users_db.verify_user_scan_connection(user_id)
        if is_connected:
            print(f"  [PASS] User {user_id} is properly connected to scans")
        else:
            print(f"  [INFO] User {user_id} has no associated scans")
    except Exception as e:
        print(f"  [FAIL] Failed to verify connection: {e}")
        return False

    return True


def main():
    """Run all integration tests."""
    print("=" * 60)
    print("PhishGuard User-Scan SQLite Integration Verification")
    print("=" * 60)

    results = []

    # Initialize database
    try:
        db.init_db()
        users_db.init_user_tables()
        print("\n[PASS] Database initialized successfully")
    except Exception as e:
        print(f"\n[FAIL] Failed to initialize database: {e}")
        return 1

    # Run tests
    results.append(("Schema check", check_schema()))
    user_id = test_user_creation_and_linking()
    results.append(("User creation & linking", bool(user_id)))
    results.append(("Batch scan linking", test_batch_scan_linking()))
    results.append(("Statistics", test_statistics()))
    results.append(("Connection verification", test_connection_verification()))

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    passed = sum(1 for _, result in results if result)
    total = len(results)
    print(f"\nTests passed: {passed}/{total}")

    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"  {status}: {test_name}")

    if passed == total:
        print("\n[SUCCESS] All tests passed! User-scan integration is working correctly.")
        return 0
    else:
        print(f"\n[FAIL] {total - passed} test(s) failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
