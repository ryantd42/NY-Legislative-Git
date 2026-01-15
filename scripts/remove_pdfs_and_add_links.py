"""
Script to remove all PDF files and add PDF links to markdown files.
"""
import re
from pathlib import Path


def extract_bill_id_and_year(folder_path: Path) -> tuple[str, int]:
    """
    Extract bill ID and session year from folder path.
    
    Example: 2023/A300-2023 -> ('A300', 2023)
    Example: 2023/S04609-2023 -> ('S04609', 2023)
    """
    # Get the folder name (e.g., "A300-2023")
    folder_name = folder_path.name
    
    # Extract session year from parent folder (e.g., "2023")
    session_year = int(folder_path.parent.name)
    
    # Extract bill ID by removing the "-YYYY" suffix
    # Pattern: remove "-2023" or similar from the end
    bill_id = re.sub(r'-\d{4}$', '', folder_name)
    
    return bill_id, session_year


def add_pdf_link_to_markdown(md_file: Path, bill_id: str, session_year: int) -> bool:
    """
    Add PDF link to markdown file after the Status line.
    
    Returns True if the file was modified, False otherwise.
    """
    try:
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check if PDF link already exists
        if '**PDF:**' in content or '**PDF Link:**' in content:
            return False
        
        # Construct PDF URL
        pdf_url = f"https://legislation.nysenate.gov/pdf/bills/{session_year}/{bill_id}"
        
        # Find the Status line and add PDF link after it
        # Pattern: **Status:** ... followed by empty line
        status_pattern = r'(\*\*Status:\*\*[^\n]*\n)'
        
        if re.search(status_pattern, content):
            # Replace Status line with Status line + PDF link
            replacement = rf'\1**PDF:** [{bill_id} PDF]({pdf_url})\n'
            new_content = re.sub(status_pattern, replacement, content)
            
            if new_content != content:
                with open(md_file, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                return True
        else:
            # If Status line not found, try to add after Session line
            session_pattern = r'(\*\*Session:\*\*[^\n]*\n)'
            if re.search(session_pattern, content):
                replacement = rf'\1**PDF:** [{bill_id} PDF]({pdf_url})\n'
                new_content = re.sub(session_pattern, replacement, content)
                
                if new_content != content:
                    with open(md_file, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    return True
        
        return False
    except Exception as e:
        print(f"Error processing {md_file}: {e}")
        return False


def main():
    """Main function to remove PDFs and add links to markdown files."""
    base_dir = Path("2023")
    
    if not base_dir.exists():
        print(f"Directory {base_dir} does not exist!")
        return
    
    pdf_count = 0
    md_updated_count = 0
    md_skipped_count = 0
    
    # Process all bill folders
    for bill_folder in sorted(base_dir.iterdir()):
        if not bill_folder.is_dir():
            continue
        
        # Delete PDF file
        pdf_file = bill_folder / "bill.pdf"
        if pdf_file.exists():
            try:
                pdf_file.unlink()
                pdf_count += 1
                if pdf_count % 100 == 0:
                    print(f"Deleted {pdf_count} PDFs so far...")
            except Exception as e:
                print(f"Error deleting {pdf_file}: {e}")
        
        # Add PDF link to markdown file
        md_file = bill_folder / "bill.md"
        if md_file.exists():
            try:
                bill_id, session_year = extract_bill_id_and_year(bill_folder)
                if add_pdf_link_to_markdown(md_file, bill_id, session_year):
                    md_updated_count += 1
                    if md_updated_count % 100 == 0:
                        print(f"Updated {md_updated_count} markdown files so far...")
                else:
                    md_skipped_count += 1
            except Exception as e:
                print(f"Error processing {md_file}: {e}")
    
    print("\n" + "=" * 60)
    print("Summary:")
    print("=" * 60)
    print(f"  PDFs deleted: {pdf_count}")
    print(f"  Markdown files updated: {md_updated_count}")
    print(f"  Markdown files skipped (already had link): {md_skipped_count}")
    print("=" * 60)


if __name__ == "__main__":
    main()
