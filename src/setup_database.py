"""
ForgeForce Procurement Agents - Database Setup Script
Run this single script to create the complete database with all tables and realistic seed data.

Usage:
    python src/setup_database.py
"""

import subprocess
import sys
from pathlib import Path

# Resolve paths relative to project root (two levels up from this file in src/)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_CREATION_DIR = PROJECT_ROOT / "src" / "database_creation"
DB_PATH = PROJECT_ROOT / "data" / "forgeforce_procurement.db"

SCRIPTS_IN_ORDER = [
    "create_database.py",
    "generate_products.py",
    "generate_items.py",
    "generate_bom_lines.py",
    "generate_seed_data.py",
    "generate_remaining_tables.py",
]

def run_script(script_name):
    script_path = DB_CREATION_DIR / script_name
    if not script_path.exists():
        print(f"❌ Script not found: {script_path}")
        return False
    
    print(f"\n{'='*60}")
    print(f"▶ Running: {script_name}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            check=True,
            capture_output=False
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error running {script_name}")
        return False

def main():
    print("\n" + "="*70)
    print("   ForgeForce Procurement Agents - Database Setup")
    print("="*70)
    
    # Optional: Delete old database
    if DB_PATH.exists():
        print(f"\n⚠️  Existing database found at: {DB_PATH}")
        choice = input("Do you want to delete it and create a fresh one? (y/n): ").strip().lower()
        if choice == 'y':
            DB_PATH.unlink()
            print("🗑️  Old database deleted.")
        else:
            print("Keeping existing database. Exiting.")
            return
    
    print("\n🚀 Starting database creation process...\n")
    
    success_count = 0
    for script in SCRIPTS_IN_ORDER:
        if run_script(script):
            success_count += 1
        else:
            print(f"\n❌ Setup failed at: {script}")
            print("Please check the error above and fix it.")
            return
    
    print("\n" + "="*70)
    print(f"✅ Database setup completed successfully! ({success_count}/{len(SCRIPTS_IN_ORDER)} scripts ran)")
    print(f"📁 Database location: {DB_PATH}")
    print("="*70)
    
    print("\n📌 Next Steps:")
    print("   • To verify the data layer, run:")
    print("     python src/database_creation/verify_data_layer.py")
    print("   • To start building agents, check the README or src/ folder.")
    print("\nHappy coding! 🚀\n")

if __name__ == "__main__":
    main()