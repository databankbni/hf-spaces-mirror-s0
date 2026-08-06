#!/usr/bin/env python3
"""Quick validation script for mktbook_2 setup."""
import sys
import asyncio

async def test_imports():
    """Test that all mktbook_2 modules can be imported."""
    print("[Test 1] Testing imports...")
    try:
        from mktbook_2 import config
        print(f"  ✓ mktbook_2.config (port={config.settings.port})")
        
        from mktbook_2.bots import bot_client, fleet
        print(f"  ✓ mktbook_2.bots.bot_client")
        print(f"  ✓ mktbook_2.bots.fleet")
        
        from mktbook_2.grading import criteria, evaluator
        print(f"  ✓ mktbook_2.grading.criteria")
        print(f"  ✓ mktbook_2.grading.evaluator")
        
        from mktbook_2 import engagement
        print(f"  ✓ mktbook_2.engagement")
        
        from mktbook_2.scheduler import loop
        print(f"  ✓ mktbook_2.scheduler.loop")
        
        from mktbook_2 import models
        print(f"  ✓ mktbook_2.models")
        
        print("  All imports successful!\n")
        return True
    except Exception as e:
        print(f"  ✗ Import failed: {e}\n")
        return False


async def test_config():
    """Test configuration loading."""
    print("[Test 2] Testing configuration...")
    try:
        from mktbook_2.config import settings
        
        checks = [
            (settings.openai_api_key, "OPENAI_API_KEY"),
            (settings.database_path, "DATABASE_PATH"),
            (settings.port, "PORT"),
        ]

        all_ok = True
        for value, name in checks:
            if value and str(value) != "0":
                print(f"  ✓ {name}: {value}")
            else:
                print(f"  ⚠ {name}: {value} (may need .env_2)")
                if name in ["OPENAI_API_KEY"]:
                    all_ok = False
        
        if all_ok:
            print("  Config looks good!\n")
        else:
            print("  Missing required config. Create .env_2 file.\n")
        
        return all_ok
    except Exception as e:
        print(f"  ✗ Config test failed: {e}\n")
        return False


async def test_models():
    """Test data models."""
    print("[Test 3] Testing data models...")
    try:
        from mktbook_2.models import (
            PersonalityType, PERSONALITY_DESCRIPTIONS,
            EngagementMetrics, SentimentShift, CloutScore
        )
        
        print(f"  ✓ Personality types: {len(PersonalityType.ALL)} defined")
        print(f"  ✓ Engagement metrics model")
        print(f"  ✓ Sentiment shift model")
        print(f"  ✓ Clout score model")
        
        # Test personality detection
        from mktbook_2.engagement import estimate_personality_type
        detected = estimate_personality_type(
            "Make people laugh", "witty and irreverent"
        )
        print(f"  ✓ Personality detection: '{detected}'")
        
        print("  Models OK!\n")
        return True
    except Exception as e:
        print(f"  ✗ Models test failed: {e}\n")
        return False


async def test_database():
    """Test database connection."""
    print("[Test 4] Testing database...")
    try:
        from mktbook.db.connection import get_db, close_db
        db = await get_db()
        print(f"  ✓ Database connection OK")
        
        from mktbook.db import queries
        bots = await queries.get_active_bots()
        print(f"  ✓ Query OK: {len(bots)} active bots in DB")
        
        await close_db()
        print("  Database OK!\n")
        return True
    except Exception as e:
        print(f"  ✗ Database test failed: {e}\n")
        return False


async def main():
    """Run all tests."""
    print("=" * 50)
    print("mktbook_2 Validation Script")
    print("=" * 50)
    print()
    
    results = []
    
    results.append(await test_imports())
    results.append(await test_config())
    results.append(await test_models())
    results.append(await test_database())
    
    print("=" * 50)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 50)
    
    if all(results):
        print("\n✓ All tests passed! mktbook_2 is ready.")
        return 0
    else:
        print("\n✗ Some tests failed. Check errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
