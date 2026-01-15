"""
Retry script to process only the bills that failed previously.
Reads failed_bills.txt and processes each bill with detailed error reporting.
"""

from pathlib import Path
from fetch_bill import BillFetcher

def load_failed_bills(failed_file: str = "failed_bills.txt") -> list:
    """Load list of failed bill IDs from file."""
    failed_path = Path(failed_file)
    
    if not failed_path.exists():
        print(f"Error: {failed_file} not found!")
        print("Please run check_failed_bills.py first to generate the failed bills list.")
        return []
    
    failed_bills = []
    with open(failed_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                failed_bills.append(line)
    
    return failed_bills

def main():
    print("="*60)
    print("Retrying Failed Bills")
    print("="*60)
    print()
    
    # Load failed bills
    failed_bills = load_failed_bills()
    
    if not failed_bills:
        print("No failed bills to retry.")
        return
    
    print(f"Found {len(failed_bills)} failed bills to retry:")
    for bill_id in failed_bills[:10]:  # Show first 10
        print(f"  - {bill_id}")
    if len(failed_bills) > 10:
        print(f"  ... and {len(failed_bills) - 10} more")
    print()
    
    # Initialize fetcher
    print("Initializing fetcher with rate limiting...")
    fetcher = BillFetcher(rate_limit=10.0, progress_file="progress.txt")
    print()
    
    # Process only the failed bills
    print("="*60)
    print(f"Processing {len(failed_bills)} failed bills...")
    print("="*60)
    print()
    
    results = fetcher.process_all_bills_with_git(
        session_year=2023,
        bill_ids=failed_bills,
        use_html=False
    )
    
    # Report results with detailed error messages
    print("\n" + "="*60)
    print("Retry Results:")
    print("="*60)
    
    successful = sum(1 for result in results.values() if (isinstance(result, tuple) and result[0]) or (not isinstance(result, tuple) and result))
    failed = len(results) - successful
    print(f"  Total bills retried: {len(results)}")
    print(f"  Now successful: {successful}")
    print(f"  Still failed: {failed}")
    print()
    
    # List still-failed bills with detailed error messages
    still_failed = []
    for bill_id, result in results.items():
        if isinstance(result, tuple):
            success, error_msg = result
            if not success:
                still_failed.append((bill_id, error_msg))
        elif not result:
            still_failed.append((bill_id, "Unknown error"))
    
    if still_failed:
        print(f"Bills that still failed ({len(still_failed)}):")
        print()
        for bill_id, error_msg in still_failed:
            print(f"  Bill: {bill_id}")
            print(f"  Error: {error_msg}")
            print()
        
        # Save updated failed list
        still_failed_file = Path("still_failed_bills.txt")
        with open(still_failed_file, 'w', encoding='utf-8') as f:
            for bill_id, error_msg in still_failed:
                f.write(f"{bill_id}: {error_msg}\n")
        print(f"Updated failed bills list saved to: {still_failed_file}")
    else:
        print("All bills processed successfully!")
    
    print("="*60)

if __name__ == "__main__":
    main()
