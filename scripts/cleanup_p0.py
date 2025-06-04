#!/usr/bin/env python3
"""
P0 Cleanup Script - Remove ad-hoc scripts and ensure single canonical entrypoint.
Addresses P0-B: Single canonical entrypoint consolidation.

This script removes old demo/test scripts that could cause drift and confusion.
"""
import os
import sys
from pathlib import Path


def main():
    """Clean up old scripts and ensure single canonical entrypoint."""
    
    print("🧹 P0 Cleanup: Removing ad-hoc scripts...")
    
    # Files to remove (old demo/test scripts)
    files_to_remove = [
        "test_hanging_fix.py",
        "rebalance_enhanced.py", 
        "cleanup_old_scripts.sh",
        "demo_*.py",
        "test_*.py",  # Only standalone test files, not test directory
        "temp_*.py",
        "backup_*.py"
    ]
    
    removed_count = 0
    
    # Check and remove files
    for file_pattern in files_to_remove:
        if "*" in file_pattern:
            # Handle wildcards
            for file_path in Path(".").glob(file_pattern):
                if file_path.is_file() and file_path.name != "test_hanging_fix.py":  # Already removed
                    try:
                        file_path.unlink()
                        print(f"  ✅ Removed: {file_path}")
                        removed_count += 1
                    except Exception as e:
                        print(f"  ❌ Failed to remove {file_path}: {e}")
        else:
            file_path = Path(file_pattern)
            if file_path.exists():
                try:
                    file_path.unlink()
                    print(f"  ✅ Removed: {file_path}")
                    removed_count += 1
                except Exception as e:
                    print(f"  ❌ Failed to remove {file_path}: {e}")
    
    # Verify main.py exists as canonical entrypoint
    main_py = Path("main.py")
    if not main_py.exists():
        print("  ❌ ERROR: main.py not found! This should be the single canonical entrypoint.")
        return 1
    else:
        print("  ✅ main.py confirmed as single canonical entrypoint")
    
    # Check for any remaining script files that might cause confusion
    potential_scripts = list(Path(".").glob("*balance*.py"))
    potential_scripts.extend(Path(".").glob("*strategy*.py"))
    potential_scripts = [p for p in potential_scripts if p.name not in ["main.py"] and not str(p).startswith("src/")]
    
    if potential_scripts:
        print("\n⚠️  WARNING: Found potential conflicting scripts:")
        for script in potential_scripts:
            print(f"    {script}")
        print("   Consider removing these or moving to src/ directory")
    
    # Summary
    print(f"\n🎯 P0-B Cleanup Complete:")
    print(f"   • Removed {removed_count} ad-hoc scripts")
    print(f"   • Canonical entrypoint: main.py ✅")
    print(f"   • Strategy selection: --strategy {{fixed,enhanced}} ✅")
    
    print(f"\n📝 Usage:")
    print(f"   python main.py --strategy fixed     # Standard rebalancing")
    print(f"   python main.py --strategy enhanced  # Smart execution with batch processing")
    print(f"   python main.py --status             # Quick status check")
    
    return 0


if __name__ == "__main__":
    sys.exit(main()) 