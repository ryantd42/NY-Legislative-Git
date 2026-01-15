"""
Script to reorganize repository structure to match the desired layout:
- Move all Python scripts to /scripts
- Flatten bill structure from 2023/BillID-2023/bill.md to 2023/BillID.md
"""
import os
import shutil
from pathlib import Path
import re


def extract_bill_id(folder_name: str) -> str:
    """Extract bill ID from folder name like 'S04609-2023' -> 'S04609'"""
    # Remove the '-2023' suffix
    return re.sub(r'-\d{4}$', '', folder_name)


def main():
    """Main reorganization function."""
    base_dir = Path(".")
    scripts_dir = base_dir / "scripts"
    year_dir = base_dir / "2023"
    
    print("=" * 60)
    print("Reorganizing repository structure...")
    print("=" * 60)
    
    # Step 1: Create scripts directory
    print("\n1. Creating /scripts directory...")
    scripts_dir.mkdir(exist_ok=True)
    print(f"   [OK] Created {scripts_dir}")
    
    # Step 2: Move Python scripts to /scripts
    print("\n2. Moving Python scripts to /scripts...")
    scripts_to_move = [
        "fetch_bill.py",
        "check_failed_bills.py",
        "retry_failed_bills.py",
        "remove_pdfs_and_add_links.py",
        "config.py",
        "requirements.txt"
    ]
    
    for script in scripts_to_move:
        src = base_dir / script
        if src.exists():
            dst = scripts_dir / script
            shutil.move(str(src), str(dst))
            print(f"   [OK] Moved {script} -> scripts/{script}")
        else:
            print(f"   [SKIP] {script} not found, skipping")
    
    # Step 3: Flatten bill structure
    print("\n3. Flattening bill structure...")
    print("   Moving 2023/BillID-2023/bill.md -> 2023/BillID.md")
    
    if not year_dir.exists():
        print(f"   ⚠ {year_dir} does not exist!")
        return
    
    moved_count = 0
    error_count = 0
    
    # Get all bill folders
    bill_folders = [d for d in year_dir.iterdir() if d.is_dir()]
    total_folders = len(bill_folders)
    
    for i, folder in enumerate(bill_folders, 1):
        if i % 1000 == 0:
            print(f"   Processing {i}/{total_folders}...")
        
        bill_md = folder / "bill.md"
        
        if bill_md.exists():
            # Extract bill ID from folder name
            bill_id = extract_bill_id(folder.name)
            new_path = year_dir / f"{bill_id}.md"
            
            try:
                # Move the file
                shutil.move(str(bill_md), str(new_path))
                moved_count += 1
                
                # Remove the empty folder
                try:
                    folder.rmdir()
                except OSError:
                    # Folder might not be empty, that's okay
                    pass
                    
            except Exception as e:
                print(f"   [ERROR] Error moving {bill_md}: {e}")
                error_count += 1
        else:
            # No bill.md in this folder, try to remove folder anyway
            try:
                folder.rmdir()
            except OSError:
                pass
    
    print(f"\n   [OK] Moved {moved_count} bill files")
    if error_count > 0:
        print(f"   [WARNING] {error_count} errors encountered")
    
    # Step 4: Create .github directory (for future Actions)
    print("\n4. Creating .github directory...")
    github_dir = base_dir / ".github"
    github_dir.mkdir(exist_ok=True)
    workflows_dir = github_dir / "workflows"
    workflows_dir.mkdir(exist_ok=True)
    print(f"   [OK] Created .github/workflows/")
    
    print("\n" + "=" * 60)
    print("Reorganization complete!")
    print("=" * 60)
    print(f"\nSummary:")
    print(f"  - Scripts moved to: /scripts")
    print(f"  - Bills flattened to: /2023/BillID.md")
    print(f"  - Total bills moved: {moved_count}")
    print("\nNext steps:")
    print("  1. Update imports in scripts (config.py path)")
    print("  2. Test that scripts still work")
    print("  3. Commit the changes")


if __name__ == "__main__":
    main()
