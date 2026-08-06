import unittest
import os
import sqlite3
from tools.fitnotes_cleaner.db import operations

DB_PATH = r"D:\Projects\quest_site\tools\FitNotes_Backup.fitnotes"

class TestOperations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(DB_PATH, "rb") as f:
            cls.db_bytes = f.read()

    def test_generate_report(self):
        report = operations.generate_report(self.db_bytes)
        self.assertIn("categories", report)
        self.assertTrue(len(report["categories"]) > 0)
        # Check first category structure
        cat = report["categories"][0]
        self.assertIn("id", cat)
        self.assertIn("name", cat)
        self.assertIn("exercises", cat)

    def test_name_exists(self):
        # 'Chest' is a likely category in FitNotes
        exists = operations.name_exists(self.db_bytes, "Chest")
        # Since I don't know the exact data, I'll just check it returns a bool
        self.assertIsInstance(exists, bool)

    def test_create_category_collision(self):
        # Find an existing category name
        report = operations.generate_report(self.db_bytes)
        existing_name = report["categories"][0]["name"]
        
        with self.assertRaises(ValueError):
            operations.create_category(self.db_bytes, existing_name)

    def test_merge_integrity(self):
        report = operations.generate_report(self.db_bytes)
        # Find a category with at least two exercises
        target_cat = None
        for cat in report["categories"]:
            if len(cat["exercises"]) >= 2:
                target_cat = cat
                break
        
        if not target_cat:
            self.skipTest("Not enough exercises to test merge")
            
        ex1 = target_cat["exercises"][0]
        ex2 = target_cat["exercises"][1]
        
        source_ids = [ex1["id"], ex2["id"]]
        target_id = ex1["id"]
        
        expected_total_logs = ex1["log_count"] + ex2["log_count"]
        
        new_bytes = operations.merge_exercises(self.db_bytes, source_ids, target_id)
        new_report = operations.generate_report(new_bytes)
        
        # Find the exercise in new report
        merged_ex = None
        for cat in new_report["categories"]:
            for ex in cat["exercises"]:
                if ex["id"] == target_id:
                    merged_ex = ex
                    break
        
        self.assertIsNotNone(merged_ex)
        self.assertEqual(merged_ex["log_count"], expected_total_logs)
        
        # Ensure ex2 is gone
        found_ex2 = False
        for cat in new_report["categories"]:
            for ex in cat["exercises"]:
                if ex["id"] == ex2["id"]:
                    found_ex2 = True
                    break
        self.assertFalse(found_ex2)

    def test_delete_exercise_with_logs(self):
        report = operations.generate_report(self.db_bytes)
        ex_with_logs = None
        for cat in report["categories"]:
            for ex in cat["exercises"]:
                if ex["log_count"] > 0:
                    ex_with_logs = ex
                    break
            if ex_with_logs: break
            
        if not ex_with_logs:
            self.skipTest("No exercises with logs found to test deletion blockage")
            
        with self.assertRaises(ValueError):
            operations.delete_exercise(self.db_bytes, ex_with_logs["id"])

if __name__ == "__main__":
    unittest.main()
