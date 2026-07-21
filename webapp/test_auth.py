#!/usr/bin/env python3
"""Quick test of the new simple authentication system."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import database.db as db
import database.users as users_db

print("=" * 60)
print("PhishGuard Simple Authentication Test")
print("=" * 60)

try:
    # Initialize database
    print("\n[1] Initializing database...")
    db.init_db()
    users_db.init_user_tables()
    print("    [PASS] Database initialized")

    # Create a test user
    print("\n[2] Creating test user...")
    user = users_db.create_user("test@example.com", "password123", "Test User")
    print(f"    [PASS] User created: ID={user['id']}, Email={user['email']}")
    user_id = user['id']

    # Verify password
    print("\n[3] Testing password verification...")
    correct_password = users_db.verify_password(user['password'], "password123")
    wrong_password = users_db.verify_password(user['password'], "wrongpassword")

    if correct_password and not wrong_password:
        print("    [PASS] Password verification works correctly")
    else:
        print("    [FAIL] Password verification failed")
        sys.exit(1)

    # Get user by email
    print("\n[4] Getting user by email...")
    retrieved_user = users_db.get_user_by_email("test@example.com")
    if retrieved_user and retrieved_user['id'] == user_id:
        print("    [PASS] User retrieved by email correctly")
    else:
        print("    [FAIL] Failed to retrieve user by email")
        sys.exit(1)

    # Test scan saving and linking
    print("\n[5] Testing scan linking to user...")
    db.save_scan(
        url="https://test.example.com",
        verdict="good",
        confidence=0.95,
        results={"test": "data"},
        user_id=user_id
    )
    print("    [PASS] Scan saved and linked to user")

    # Get user scans
    print("\n[6] Retrieving user scans...")
    scans = users_db.get_user_scans(user_id)
    if scans and len(scans) > 0:
        print(f"    [PASS] Found {len(scans)} scan(s) for user")
    else:
        print("    [FAIL] No scans found for user")
        sys.exit(1)

    # Get user statistics
    print("\n[7] Getting user statistics...")
    stats = users_db.get_user_scan_stats(user_id)
    print(f"    [PASS] Statistics: {stats['total_scans']} total, {stats['phishing_count']} phishing")

    print("\n" + "=" * 60)
    print("[SUCCESS] All authentication tests passed!")
    print("=" * 60)
    sys.exit(0)

except Exception as e:
    print(f"\n[ERROR] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
