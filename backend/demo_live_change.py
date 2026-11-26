#!/usr/bin/env python3
"""
DataGit Live Demo Manipulator
Executes real-time database changes in PostgreSQL to demonstrate live tracking in DataGit.
"""

import os
import sys

# Ensure backend directory is in python path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from dagit.versioning.demo_scenarios import DEMO_SCENARIOS, execute_demo_scenario


def print_banner():
    print("=" * 68)
    print("  🚀 DataGit Live Demo Database Manipulator")
    print("  Manipulates PostgreSQL in real-time to demonstrate version tracking")
    print("=" * 68)


def print_menu():
    print("\nSelect a live scenario to execute on PostgreSQL:")
    for idx, (key, info) in enumerate(DEMO_SCENARIOS.items(), 1):
        print(f"  [{idx}] {info['title']}")
        print(f"      {info['description']}")
    print("  [4] Reset Database back to clean HEAD snapshot")
    print("  [5] Exit")


def main():
    print_banner()

    if len(sys.argv) > 1:
        arg = sys.argv[1].lower().strip()
        if arg in DEMO_SCENARIOS:
            scenario_key = arg
        elif arg in ("reset", "clean", "reset_clean"):
            scenario_key = "reset_clean"
        elif arg in ("1", "flash", "flash_sale"):
            scenario_key = "flash_sale"
        elif arg in ("2", "order", "new_order"):
            scenario_key = "new_order"
        elif arg in ("3", "launch", "product_launch"):
            scenario_key = "product_launch"
        else:
            print(f"Unknown argument: {arg}")
            print(f"Valid options: {list(DEMO_SCENARIOS.keys())} or 'reset'")
            sys.exit(1)
    else:
        print_menu()
        choice = input("\nEnter choice (1-5): ").strip()
        if choice == "1":
            scenario_key = "flash_sale"
        elif choice == "2":
            scenario_key = "new_order"
        elif choice == "3":
            scenario_key = "product_launch"
        elif choice == "4":
            scenario_key = "reset_clean"
        else:
            print("Exiting.")
            sys.exit(0)

    print(f"\n⚡ Executing scenario: '{scenario_key}' in PostgreSQL...")
    try:
        result = execute_demo_scenario(scenario_key)
        print("\n✅ Success!")
        print(f"  Title: {result['title']}")
        print(f"  Description: {result['description']}")
        print(f"  Suggested Commit Message: \"{result['suggested_commit_message']}\"")
        print("\n👀 Now switch to your browser running DataGit (http://localhost:5173):")
        print("  1. Notice the '🟡 Uncommitted Changes Detected' alert in the UI!")
        print("  2. Open the 'Diff' tab to see the live row/schema additions.")
        print("  3. Go to 'Snapshot' and record a commit with the suggested message.")
        print("  4. Check 'Timeline' to view your new live commit in the history graph!\n")
    except Exception as err:
        print(f"\n❌ Error executing scenario: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
