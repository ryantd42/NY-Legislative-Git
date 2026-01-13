"""
NY Legislative Git - Bill Fetcher

This module handles fetching bill data from the NYS Senate Open Legislation API,
sanitizing HTML, and saving bills as Markdown files.
"""

import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md

from config import Config


class BillFetcher:
    """Handles fetching bill data from the NYS Senate Open Legislation API."""
    
    def __init__(self):
        """Initialize the BillFetcher with configuration."""
        self.base_url = Config.SENATE_API_BASE_URL
        self.headers = Config.get_senate_headers()
    
    def fetch_bill(self, bill_id: str, session_year: Optional[int] = None) -> Optional[Dict]:
        """
        Fetch bill data from the NYS Senate Open Legislation API.
        
        According to the official API documentation:
        https://legislation.nysenate.gov/static/docs/html/bills.html#get-a-single-bill
        
        Endpoint: (GET) /api/3/bills/{sessionYear}/{printNo}
        
        Args:
            bill_id: The bill identifier (e.g., 'S04609')
            session_year: The legislative session year (e.g., 2023). 
                         If None, will try to infer from current date.
            
        Returns:
            dict: Bill data including fullText, or None if request fails
            
        Raises:
            requests.RequestException: If the API request fails
        """
        # The API requires a session year in the URL format: /bills/{sessionYear}/{printNo}
        # Reference: https://legislation.nysenate.gov/static/docs/html/bills.html#get-a-single-bill
        if session_year is None:
            # Default to current year or most recent session
            from datetime import datetime
            session_year = datetime.now().year
        
        # Construct the API endpoint with session year
        # Format: /api/3/bills/{sessionYear}/{printNo}
        endpoint = f"{self.base_url}/bills/{session_year}/{bill_id}"
        
        # Prepare query parameters for API key
        params = {}
        if Config.SENATE_API_KEY:
            # Try common query parameter names for API keys
            params['key'] = Config.SENATE_API_KEY
        
        try:
            response = requests.get(
                endpoint,
                headers=self.headers,
                params=params,
                timeout=30
            )
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            # Sanitize error message to avoid exposing API key in URLs
            error_msg = str(e)
            if Config.SENATE_API_KEY and Config.SENATE_API_KEY in error_msg:
                error_msg = error_msg.replace(Config.SENATE_API_KEY, '[REDACTED]')
            print(f"Error fetching bill {bill_id}: {error_msg}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response status: {e.response.status_code}")
                # Sanitize response body in case it contains the API key
                response_body = e.response.text[:500]
                if Config.SENATE_API_KEY and Config.SENATE_API_KEY in response_body:
                    response_body = response_body.replace(Config.SENATE_API_KEY, '[REDACTED]')
                print(f"Response body: {response_body}")
            return None
    
    def get_bill_versions(
        self, 
        bill_id: str, 
        session_year: Optional[int] = None
    ) -> Tuple[List[str], List[str]]:
        """
        Extract all version suffixes from the amendments object and construct full bill IDs.
        
        The amendments.items dictionary contains keys that are version suffixes:
        - '' (empty string) for the base version
        - 'A', 'B', 'C', etc. for amended versions
        
        Args:
            bill_id: The base bill identifier (e.g., 'S04609')
            session_year: The legislative session year (e.g., 2023). 
                         If None, will try to infer from current date.
            
        Returns:
            Tuple[List[str], List[str]]: Tuple of (version_suffixes, full_bill_ids)
                                         e.g., (['', 'A', 'B'], ['S04609', 'S04609A', 'S04609B'])
        """
        bill_data = self.fetch_bill(bill_id, session_year)
        
        if not bill_data:
            return [], []
        
        # Extract from the API response structure
        result = bill_data.get('result', {})
        amendments = result.get('amendments', {})
        items = amendments.get('items', {})
        
        if not isinstance(items, dict) or not items:
            return [], []
        
        # Extract all version suffixes (keys of the items dict)
        version_suffixes = list(items.keys())
        
        # Sort suffixes logically: empty string first, then alphabetical
        def sort_key(suffix: str) -> tuple:
            """Sort key: empty string first, then by letter."""
            if suffix == '':
                return (0, '')
            return (1, suffix)
        
        version_suffixes.sort(key=sort_key)
        
        # Construct full bill IDs by appending each suffix to the base bill ID
        full_bill_ids = []
        for suffix in version_suffixes:
            if suffix == '':
                # Base version - use original bill_id
                full_bill_ids.append(bill_id)
            else:
                # Amended version - append suffix
                full_bill_ids.append(f"{bill_id}{suffix}")
        
        # Log the versions found
        print(f"\nBill versions found for {bill_id}:")
        print(f"  Version suffixes: {version_suffixes}")
        print(f"  Full bill IDs: {full_bill_ids}")
        print(f"  Total versions: {len(full_bill_ids)}\n")
        
        return version_suffixes, full_bill_ids
    
    def get_amendment_data(
        self,
        bill_id: str,
        session_year: Optional[int] = None,
        version_suffix: str = ''
    ) -> Optional[Dict]:
        """
        Get the amendment data object for a specific version.
        
        Args:
            bill_id: The bill identifier (e.g., 'S04609')
            session_year: The legislative session year (e.g., 2023). 
                         If None, will try to infer from current date.
            version_suffix: The version suffix (e.g., '' for base, 'A' for amendment A).
                           Defaults to '' (base version).
            
        Returns:
            dict: The amendment data object, or None if not found
        """
        bill_data = self.fetch_bill(bill_id, session_year)
        
        if not bill_data:
            return None
        
        result = bill_data.get('result', {})
        amendments = result.get('amendments', {})
        items = amendments.get('items', {})
        
        if isinstance(items, dict) and items:
            if version_suffix in items:
                return items[version_suffix]
            else:
                # If specific version not found, try to get first available
                first_key = list(items.keys())[0]
                return items[first_key]
        
        return None
    
    def get_full_text(
        self, 
        bill_id: str, 
        session_year: Optional[int] = None,
        version_suffix: str = ''
    ) -> Optional[str]:
        """
        Extract the fullText field from bill data for a specific version.
        
        Args:
            bill_id: The bill identifier (e.g., 'S04609')
            session_year: The legislative session year (e.g., 2023). 
                         If None, will try to infer from current date.
            version_suffix: The version suffix (e.g., '' for base, 'A' for amendment A).
                           Defaults to '' (base version).
            
        Returns:
            str: The fullText HTML content, or None if not found
        """
        amendment = self.get_amendment_data(bill_id, session_year, version_suffix)
        
        if not amendment:
            print(f"Warning: Amendment data not found for {bill_id} (version suffix: '{version_suffix}')")
            return None
        
        # Prefer fullTextHtml if available and not empty, otherwise use fullText
        if 'fullTextHtml' in amendment and amendment['fullTextHtml']:
            return amendment['fullTextHtml']
        elif 'fullText' in amendment:
            return amendment['fullText']
        
        return None
    
    def get_sponsor_memo_first_paragraph(
        self,
        bill_id: str,
        session_year: Optional[int] = None,
        version_suffix: str = ''
    ) -> Optional[str]:
        """
        Extract the first paragraph of the sponsorMemo for a specific version.
        
        Args:
            bill_id: The bill identifier (e.g., 'S04609')
            session_year: The legislative session year (e.g., 2023). 
                         If None, will try to infer from current date.
            version_suffix: The version suffix (e.g., '' for base, 'A' for amendment A).
                           Defaults to '' (base version).
            
        Returns:
            str: The first paragraph of the sponsorMemo, or None if not found
        """
        amendment = self.get_amendment_data(bill_id, session_year, version_suffix)
        
        if not amendment:
            return None
        
        # Try to get sponsorMemo from the amendment
        sponsor_memo = None
        if 'sponsorMemo' in amendment and amendment['sponsorMemo']:
            sponsor_memo = amendment['sponsorMemo']
        elif 'memo' in amendment and amendment['memo']:
            sponsor_memo = amendment['memo']
        elif 'summary' in amendment and amendment['summary']:
            sponsor_memo = amendment['summary']
        
        if not sponsor_memo:
            return None
        
        # Extract first paragraph
        # Remove HTML tags if present
        if isinstance(sponsor_memo, str):
            # Remove HTML tags
            soup = BeautifulSoup(sponsor_memo, 'lxml')
            text = soup.get_text()
            
            # Clean up the text first
            text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
            text = text.strip()
            
            # Try to split by double newlines first (most reliable paragraph separator)
            paragraphs = re.split(r'\n\s*\n', text)
            if paragraphs and paragraphs[0]:
                first_paragraph = paragraphs[0].strip()
            else:
                # If no double newlines, try to find first sentence or reasonable chunk
                # Look for first sentence ending with period, exclamation, or question mark
                sentence_match = re.match(r'^([^.!?]+[.!?])', text)
                if sentence_match:
                    first_paragraph = sentence_match.group(1).strip()
                else:
                    # Fallback: take first 300 characters
                    first_paragraph = text[:300].strip()
            
            # Clean up whitespace again
            first_paragraph = re.sub(r'\s+', ' ', first_paragraph)
            
            # Limit length to reasonable size for commit message body
            # Git commit messages typically work best with shorter bodies
            if len(first_paragraph) > 500:
                # Try to cut at a sentence boundary
                cut_point = first_paragraph[:500].rfind('.')
                if cut_point > 200:  # Only use sentence boundary if it's not too short
                    first_paragraph = first_paragraph[:cut_point + 1]
                else:
                    first_paragraph = first_paragraph[:497] + "..."
            
            return first_paragraph if first_paragraph else None
        
        return None
    
    def sanitize_html(self, html_content: str) -> str:
        """
        Sanitize HTML content using BeautifulSoup.
        
        Args:
            html_content: Raw HTML content to sanitize
            
        Returns:
            str: Sanitized HTML content
        """
        if not html_content:
            return ""
        
        # Parse HTML with BeautifulSoup
        soup = BeautifulSoup(html_content, 'lxml')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        # Remove comments
        from bs4 import Comment
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()
        
        # Clean up whitespace and formatting
        # Get text and preserve some structure
        text = soup.get_text()
        
        # Clean up excessive whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        return text
    
    def html_to_markdown(self, html_content: str) -> str:
        """
        Convert HTML content to Markdown format.
        
        Args:
            html_content: HTML content to convert
            
        Returns:
            str: Markdown formatted content
        """
        if not html_content:
            return ""
        
        # First sanitize the HTML
        soup = BeautifulSoup(html_content, 'lxml')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        # Convert to markdown
        # Use markdownify with some custom options
        markdown = md(
            str(soup),
            heading_style="ATX",  # Use # for headings
            bullets="-",  # Use - for bullet lists
            strip=['a'],  # Strip anchor tags but keep text
        )
        
        # Clean up the markdown
        # Remove excessive blank lines
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)
        
        # Clean up whitespace
        markdown = markdown.strip()
        
        return markdown
    
    def get_bill_folder_path(
        self, 
        bill_id: str, 
        session_year: Optional[int] = None
    ) -> Path:
        """
        Get the folder path for a bill based on its ID and session year.
        
        Args:
            bill_id: The bill identifier (e.g., 'S04609')
            session_year: Optional session year to include in folder name
            
        Returns:
            Path: Path to the bill folder
        """
        # Sanitize bill_id for filesystem (remove any invalid characters)
        safe_bill_id = re.sub(r'[<>:"/\\|?*]', '_', bill_id)
        folder_name = safe_bill_id
        
        # Optionally include session year in folder name
        if session_year:
            folder_name = f"{safe_bill_id}-{session_year}"
        
        return Path(folder_name)
    
    def download_bill_pdf(
        self, 
        bill_id: str, 
        session_year: Optional[int] = None,
        bill_dir: Optional[Path] = None
    ) -> Optional[Path]:
        """
        Download the original PDF of a bill from the NYS Senate website.
        
        According to the official API documentation:
        https://legislation.nysenate.gov/static/docs/html/bills.html#get-pdf-of-bill-text
        
        The PDF is available at: /pdf/bills/{sessionYear}/{printNo}
        
        Args:
            bill_id: The bill identifier (e.g., 'S04609')
            session_year: The legislative session year (e.g., 2023)
            bill_dir: Optional directory to save the PDF in. If None, uses get_bill_folder_path
            
        Returns:
            Path: Path to the downloaded PDF file, or None if download failed
        """
        if session_year is None:
            from datetime import datetime
            session_year = datetime.now().year
        
        # Construct PDF URL according to official API documentation
        # Reference: https://legislation.nysenate.gov/static/docs/html/bills.html#get-pdf-of-bill-text
        # Format: https://legislation.nysenate.gov/pdf/bills/{sessionYear}/{printNo}
        pdf_url = f"https://legislation.nysenate.gov/pdf/bills/{session_year}/{bill_id}"
        
        # Get the bill directory
        if bill_dir is None:
            bill_dir = self.get_bill_folder_path(bill_id, session_year)
        
        # Create directory if it doesn't exist
        bill_dir.mkdir(exist_ok=True)
        
        # Create PDF file path
        pdf_file = bill_dir / "bill.pdf"
        
        try:
            # Download the PDF
            # Note: PDF endpoint may not require API key, but include it if available
            params = {}
            if Config.SENATE_API_KEY:
                params['key'] = Config.SENATE_API_KEY
            
            response = requests.get(
                pdf_url,
                params=params,
                headers=self.headers,
                timeout=30,
                stream=True  # Stream for large files
            )
            
            # Check if the response is actually a PDF
            content_type = response.headers.get('Content-Type', '')
            if 'pdf' not in content_type.lower() and response.status_code != 200:
                print(f"Warning: PDF download returned status {response.status_code} or non-PDF content type: {content_type}")
                return None
            
            # Save the PDF
            with open(pdf_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"Downloaded PDF to: {pdf_file}")
            return pdf_file
            
        except requests.exceptions.RequestException as e:
            # Sanitize error message
            error_msg = str(e)
            if Config.SENATE_API_KEY and Config.SENATE_API_KEY in error_msg:
                error_msg = error_msg.replace(Config.SENATE_API_KEY, '[REDACTED]')
            print(f"Error downloading PDF for bill {bill_id}: {error_msg}")
            return None
        except Exception as e:
            print(f"Error saving PDF for bill {bill_id}: {e}")
            return None
    
    def save_bill_as_markdown(
        self, 
        bill_id: str, 
        markdown_content: str, 
        session_year: Optional[int] = None,
        bill_dir: Optional[Path] = None
    ) -> Optional[Path]:
        """
        Save bill content as a Markdown file in a folder named after the Bill ID.
        
        Args:
            bill_id: The bill identifier (e.g., 'S04609')
            markdown_content: The markdown content to save
            session_year: Optional session year to include in folder name
            bill_dir: Optional directory to save the markdown in. If None, uses get_bill_folder_path
            
        Returns:
            Path: Path to the saved file, or None if save failed
        """
        if not markdown_content:
            print(f"Warning: No content to save for bill {bill_id}")
            return None
        
        # Get the bill directory
        if bill_dir is None:
            bill_dir = self.get_bill_folder_path(bill_id, session_year)
        
        # Create the directory
        bill_dir.mkdir(exist_ok=True)
        
        # Create markdown file path
        markdown_file = bill_dir / "bill.md"
        
        # Write the markdown content
        try:
            with open(markdown_file, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            
            print(f"Saved bill to: {markdown_file}")
            return markdown_file
        except Exception as e:
            print(f"Error saving bill {bill_id}: {e}")
            return None
    
    def fetch_and_save_bill(
        self, 
        bill_id: str, 
        session_year: Optional[int] = None,
        use_html: bool = False
    ) -> Optional[Path]:
        """
        Fetch a bill, sanitize it, convert to Markdown, and save it.
        
        Args:
            bill_id: The bill identifier (e.g., 'S04609')
            session_year: The legislative session year (e.g., 2023)
            use_html: If True, prefer HTML version; if False, use plain text
            
        Returns:
            Path: Path to the saved markdown file, or None if failed
        """
        # Fetch the bill data to get metadata
        bill_data = self.fetch_bill(bill_id, session_year)
        
        if not bill_data:
            print(f"Failed to fetch bill {bill_id}")
            return None
        
        # Extract metadata
        result = bill_data.get('result', {})
        title = result.get('title', f'Bill {bill_id}')
        summary = result.get('summary', '')
        sponsor = result.get('sponsor', {})
        sponsor_name = sponsor.get('member', {}).get('fullName', 'Unknown') if sponsor else 'Unknown'
        status = result.get('status', {})
        status_desc = status.get('statusDesc', 'Unknown') if status else 'Unknown'
        
        # Fetch the bill text
        full_text = self.get_full_text(bill_id, session_year)
        
        if not full_text:
            print(f"Failed to fetch bill text for {bill_id}")
            return None
        
        # Build markdown content with metadata
        markdown_lines = [
            f"# {title}",
            "",
            f"**Bill ID:** {bill_id}",
            f"**Session:** {session_year or 'Unknown'}",
            f"**Sponsor:** {sponsor_name}",
            f"**Status:** {status_desc}",
        ]
        
        if summary:
            markdown_lines.extend([
                "",
                "## Summary",
                "",
                summary,
            ])
        
        markdown_lines.extend([
            "",
            "---",
            "",
            "## Full Text",
            "",
        ])
        
        # Convert to markdown
        # Check if we have HTML or plain text
        if use_html or ('<' in full_text and '>' in full_text):
            # It's HTML, convert to markdown
            text_markdown = self.html_to_markdown(full_text)
        else:
            # It's plain text, format it nicely
            # Preserve formatting but clean up excessive whitespace
            text_markdown = full_text.strip()
            # Convert multiple spaces to single spaces (except for intentional formatting)
            text_markdown = re.sub(r' {3,}', '  ', text_markdown)
        
        markdown_lines.append(text_markdown)
        
        markdown_content = '\n'.join(markdown_lines)
        
        # Get the bill directory path (will be created if needed)
        bill_dir = self.get_bill_folder_path(bill_id, session_year)
        
        # Save the markdown file
        markdown_path = self.save_bill_as_markdown(bill_id, markdown_content, session_year, bill_dir)
        
        # Download and save the PDF
        pdf_path = self.download_bill_pdf(bill_id, session_year, bill_dir)
        
        # Return the markdown path (or PDF path if markdown failed but PDF succeeded)
        return markdown_path or pdf_path
    
    def process_bill_versions_with_git(
        self,
        bill_id: str,
        session_year: Optional[int] = None,
        use_html: bool = False
    ) -> bool:
        """
        Process all bill versions in chronological order and commit each to Git.
        
        For each version:
        1. Fetch the text for that specific version
        2. Overwrite the existing bill.md file with this version's text
        3. Stage the file: git add bill.md
        4. Commit the change: git commit -m "Amendment [Suffix] for [BillID]"
        
        Commits happen in chronological order (Original -> A -> B) so the Git history
        reflects the real-world timeline.
        
        Args:
            bill_id: The base bill identifier (e.g., 'S04609')
            session_year: The legislative session year (e.g., 2023)
            use_html: If True, prefer HTML version; if False, use plain text
            
        Returns:
            bool: True if all versions were processed successfully, False otherwise
        """
        if session_year is None:
            from datetime import datetime
            session_year = datetime.now().year
        
        # Get all versions in chronological order
        version_suffixes, full_bill_ids = self.get_bill_versions(bill_id, session_year)
        
        if not version_suffixes:
            print(f"No versions found for bill {bill_id}")
            return False
        
        # Get bill directory
        bill_dir = self.get_bill_folder_path(bill_id, session_year)
        bill_dir.mkdir(exist_ok=True)
        markdown_file = bill_dir / "bill.md"
        
        # Fetch bill metadata once (same for all versions)
        bill_data = self.fetch_bill(bill_id, session_year)
        if not bill_data:
            print(f"Failed to fetch bill data for {bill_id}")
            return False
        
        result = bill_data.get('result', {})
        title = result.get('title', f'Bill {bill_id}')
        summary = result.get('summary', '')
        sponsor = result.get('sponsor', {})
        sponsor_name = sponsor.get('member', {}).get('fullName', 'Unknown') if sponsor else 'Unknown'
        status = result.get('status', {})
        status_desc = status.get('statusDesc', 'Unknown') if status else 'Unknown'
        
        success_count = 0
        
        # Process each version in chronological order
        for i, (suffix, full_bill_id) in enumerate(zip(version_suffixes, full_bill_ids)):
            print(f"\n{'='*60}")
            print(f"Processing version {i+1}/{len(version_suffixes)}: {full_bill_id}")
            print(f"{'='*60}")
            
            # Fetch the text for this specific version
            full_text = self.get_full_text(bill_id, session_year, version_suffix=suffix)
            
            if not full_text:
                print(f"Warning: Failed to fetch text for version {full_bill_id}, skipping...")
                continue
            
            # Build markdown content with metadata
            markdown_lines = [
                f"# {title}",
                "",
                f"**Bill ID:** {full_bill_id}",
                f"**Session:** {session_year or 'Unknown'}",
                f"**Sponsor:** {sponsor_name}",
                f"**Status:** {status_desc}",
            ]
            
            if summary:
                markdown_lines.extend([
                    "",
                    "## Summary",
                    "",
                    summary,
                ])
            
            markdown_lines.extend([
                "",
                "---",
                "",
                "## Full Text",
                "",
            ])
            
            # Convert to markdown
            if use_html or ('<' in full_text and '>' in full_text):
                text_markdown = self.html_to_markdown(full_text)
            else:
                text_markdown = full_text.strip()
                text_markdown = re.sub(r' {3,}', '  ', text_markdown)
            
            markdown_lines.append(text_markdown)
            markdown_content = '\n'.join(markdown_lines)
            
            # Overwrite the markdown file
            try:
                with open(markdown_file, 'w', encoding='utf-8') as f:
                    f.write(markdown_content)
                print(f"Saved bill text to: {markdown_file}")
            except Exception as e:
                print(f"Error saving bill {full_bill_id}: {e}")
                continue
            
            # Stage the file with git add
            git_add_success = False
            try:
                # Use relative path from repository root
                relative_path = markdown_file.relative_to(Path.cwd())
                result = subprocess.run(
                    ['git', 'add', str(relative_path)],
                    capture_output=True,
                    text=True,
                    check=False
                )
                if result.returncode != 0:
                    print(f"Warning: git add failed: {result.stderr}")
                    print(f"  Skipping commit for {full_bill_id}")
                else:
                    print(f"Staged file: {relative_path}")
                    git_add_success = True
            except Exception as e:
                print(f"Error staging file: {e}")
                print(f"  Skipping commit for {full_bill_id}")
                continue
            
            # Commit the change (only if git add succeeded)
            if git_add_success:
                try:
                    # Get sponsorMemo for this version to use as commit body
                    sponsor_memo = self.get_sponsor_memo_first_paragraph(bill_id, session_year, version_suffix=suffix)
                    
                    # Create commit message title
                    if suffix == '':
                        commit_title = f"Initial version for {bill_id}"
                    else:
                        commit_title = f"Amendment {suffix} for {bill_id}"
                    
                    # Build commit command with multi-line message
                    commit_args = ['git', 'commit', '-m', commit_title]
                    
                    # Add sponsorMemo as body if available
                    if sponsor_memo:
                        commit_args.extend(['-m', sponsor_memo])
                        print(f"Commit message includes sponsor memo: {sponsor_memo[:100]}...")
                    
                    result = subprocess.run(
                        commit_args,
                        capture_output=True,
                        text=True,
                        check=False
                    )
                    if result.returncode != 0:
                        if 'nothing to commit' in result.stdout or 'nothing to commit' in result.stderr:
                            print(f"No changes to commit for {full_bill_id} (file unchanged)")
                        elif 'Author identity unknown' in result.stderr:
                            print(f"Error: Git user not configured. Please run:")
                            print(f"  git config user.name 'Your Name'")
                            print(f"  git config user.email 'your.email@example.com'")
                        else:
                            print(f"Warning: git commit failed: {result.stderr}")
                            print(f"  stdout: {result.stdout}")
                    else:
                        print(f"Committed: {commit_title}")
                        if sponsor_memo:
                            print(f"  With memo: {sponsor_memo[:80]}...")
                        success_count += 1
                except Exception as e:
                    print(f"Error committing: {e}")
                    continue
        
        print(f"\n{'='*60}")
        print(f"Processing complete: {success_count}/{len(version_suffixes)} versions committed")
        print(f"{'='*60}\n")
        
        return success_count == len(version_suffixes)


if __name__ == "__main__":
    # Example usage
    fetcher = BillFetcher()
    
    # Test with example bill ID
    test_bill_id = "S04609"
    test_session = 2023  # Specify the session year
    print(f"Fetching bill {test_bill_id} from session {test_session}...")
    
    # Test the new get_bill_versions function
    version_suffixes, full_bill_ids = fetcher.get_bill_versions(test_bill_id, test_session)
    
    # Process all versions with Git automation
    print("\n" + "="*60)
    print("Processing bill versions with Git automation")
    print("="*60)
    success = fetcher.process_bill_versions_with_git(test_bill_id, test_session)
    
    if success:
        print("Successfully processed all bill versions!")
    else:
        print("Some versions failed to process. Check the output above for details.")
    
    # Fetch, sanitize, and save the bill
    saved_path = fetcher.fetch_and_save_bill(test_bill_id, test_session)
    
    if saved_path:
        print(f"Successfully saved bill to: {saved_path}")
        # Show preview of saved content
        with open(saved_path, 'r', encoding='utf-8') as f:
            content = f.read()
            print(f"\nMarkdown preview (first 300 chars):")
            print("-" * 50)
            print(content[:300])
            print("-" * 50)
    else:
        print("Failed to fetch and save bill")
