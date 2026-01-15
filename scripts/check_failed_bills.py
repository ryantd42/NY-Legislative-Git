"""
Diagnostic script to identify which bills failed to process.
Compares the full list of bills with what's in progress.txt.
"""

from pathlib import Path
from fetch_bill import BillFetcher

def get_processed_bill_ids(progress_file: str = "progress.txt") -> set:
    """Extract unique bill IDs from progress.txt."""
    processed = set()
    progress_path = Path(progress_file)
    
    if not progress_path.exists():
        return processed
    
    with open(progress_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                # Format is "bill_id:version_suffix" or "bill_id:"
                # Extract just the bill_id part
                if ':' in line:
                    bill_id = line.split(':')[0]
                    processed.add(bill_id)
                else:
                    processed.add(line)
    
    return processed

def main():
    print("="*60)
    print("Checking for failed bills...")
    print("="*60)
    print()
    
    # Get all bill IDs for 2023
    print("Step 1: Fetching all bill IDs from 2023 session...")
    fetcher = BillFetcher(rate_limit=10.0, progress_file="progress.txt")
    all_bill_ids = fetcher.fetch_all_bill_ids(session_year=2023)
    print(f"Total bills found: {len(all_bill_ids)}")
    print()
    
    # Get processed bill IDs
    print("Step 2: Checking progress.txt...")
    processed_bill_ids = get_processed_bill_ids()
    print(f"Bills with at least one version processed: {len(processed_bill_ids)}")
    print()
    
    # Find failed bills (bills that have no entries in progress.txt)
    all_bill_ids_set = set(all_bill_ids)
    failed_bills = all_bill_ids_set - processed_bill_ids
    
    print("="*60)
    print("Results:")
    print("="*60)
    print(f"  Total bills: {len(all_bill_ids)}")
    print(f"  Processed (at least one version): {len(processed_bill_ids)}")
    print(f"  Failed (no versions processed): {len(failed_bills)}")
    print()
    
    if failed_bills:
        print(f"Failed bills ({len(failed_bills)}):")
        # Sort for easier reading
        sorted_failed = sorted(failed_bills)
        for bill_id in sorted_failed:
            print(f"  - {bill_id}")
        
        # Save to file
        failed_file = Path("failed_bills.txt")
        with open(failed_file, 'w', encoding='utf-8') as f:
            for bill_id in sorted_failed:
                f.write(f"{bill_id}\n")
        print(f"\nFailed bills list saved to: {failed_file}")
    else:
        print("No failed bills found! All bills have at least one version processed.")
    
    print("="*60)

if __name__ == "__main__":
    main()
