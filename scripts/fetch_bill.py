"""
NY Legislative Git - Bill Fetcher

This module handles fetching bill data from the NYS Senate Open Legislation API,
sanitizing HTML, and saving bills as Markdown files.
"""

import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md

from config import Config


class RateLimiter:
    """Rate limiter to ensure maximum requests per second."""
    
    def __init__(self, max_requests_per_second: float = 2.0):
        """
        Initialize rate limiter.
        
        Args:
            max_requests_per_second: Maximum number of requests per second (default: 2.0)
        """
        self.min_interval = 1.0 / max_requests_per_second
        self.last_request_time = 0.0
    
    def wait_if_needed(self):
        """Wait if necessary to maintain rate limit."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_interval:
            sleep_time = self.min_interval - time_since_last
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()


class ProgressTracker:
    """Tracks processing progress to enable resumable downloads."""
    
    def __init__(self, progress_file: str = "progress.txt"):
        """
        Initialize progress tracker.
        
        Args:
            progress_file: Path to the progress file
        """
        self.progress_file = Path(progress_file)
        self.processed_bills: set = set()
        self.load_progress()
    
    def load_progress(self):
        """Load progress from file."""
        if self.progress_file.exists():
            try:
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            # Format: bill_id:version_suffix or just bill_id
                            self.processed_bills.add(line)
                print(f"Loaded progress: {len(self.processed_bills)} items already processed")
            except Exception as e:
                print(f"Warning: Could not load progress file: {e}")
    
    def is_processed(self, bill_id: str, version_suffix: str = '') -> bool:
        """
        Check if a bill version has been processed.
        
        Args:
            bill_id: The bill identifier
            version_suffix: The version suffix (empty string for original)
            
        Returns:
            bool: True if already processed
        """
        if version_suffix:
            key = f"{bill_id}:{version_suffix}"
        else:
            key = f"{bill_id}:"
        return key in self.processed_bills
    
    def mark_processed(self, bill_id: str, version_suffix: str = ''):
        """
        Mark a bill version as processed.
        
        Args:
            bill_id: The bill identifier
            version_suffix: The version suffix (empty string for original)
        """
        if version_suffix:
            key = f"{bill_id}:{version_suffix}"
        else:
            key = f"{bill_id}:"
        
        self.processed_bills.add(key)
        
        # Append to progress file
        try:
            with open(self.progress_file, 'a', encoding='utf-8') as f:
                f.write(f"{key}\n")
        except Exception as e:
            print(f"Warning: Could not write to progress file: {e}")


class BillFetcher:
    """Handles fetching bill data from the NYS Senate Open Legislation API."""
    
    def __init__(self, rate_limit: float = 2.0, progress_file: str = "progress.txt"):
        """
        Initialize the BillFetcher with configuration.
        
        Args:
            rate_limit: Maximum requests per second (default: 2.0)
            progress_file: Path to progress tracking file (default: "progress.txt")
        """
        self.base_url = Config.SENATE_API_BASE_URL
        self.headers = Config.get_senate_headers()
        self.rate_limiter = RateLimiter(max_requests_per_second=rate_limit)
        self.progress_tracker = ProgressTracker(progress_file=progress_file)
    
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
        
        max_retries = 3
        retry_delay = 1  # Start with 1 second
        
        for attempt in range(max_retries):
            try:
                # Apply rate limiting
                self.rate_limiter.wait_if_needed()
                
                response = requests.get(
                    endpoint,
                    headers=self.headers,
                    params=params,
                    timeout=30
                )
                
                # Handle rate limiting (HTTP 429)
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', retry_delay * (2 ** attempt)))
                    print(f"Rate limited (429) for bill {bill_id}! Waiting {retry_after} seconds before retry {attempt + 1}/{max_retries}...")
                    time.sleep(retry_after)
                    continue  # Retry the request
                
                response.raise_for_status()
                
                return response.json()
                
            except requests.exceptions.RequestException as e:
                # If this is the last attempt, raise the exception
                if attempt == max_retries - 1:
                    raise
                
                # For other errors, wait and retry with exponential backoff
                wait_time = retry_delay * (2 ** attempt)
                print(f"Request failed for bill {bill_id} (attempt {attempt + 1}/{max_retries}), retrying in {wait_time} seconds...")
                time.sleep(wait_time)
        
        # If we get here, all retries failed
        # Sanitize error message to avoid exposing API key in URLs
        error_msg = f"Failed to fetch bill {bill_id} after {max_retries} attempts"
        print(f"Error: {error_msg}")
        
        # Try to get more error details if available
        try:
            # This will only execute if we somehow got here without an exception
            pass
        except Exception as e:
            error_details = str(e)
            if Config.SENATE_API_KEY and Config.SENATE_API_KEY in error_details:
                error_details = error_details.replace(Config.SENATE_API_KEY, '[REDACTED]')
            print(f"Error details: {error_details}")
        
        return None
    
    def fetch_all_bill_ids(
        self,
        session_year: int = 2023,
        limit: int = 1000
    ) -> List[str]:
        """
        Fetch all bill IDs for a given session year, handling pagination.
        
        According to the NYS Senate API, the bills list endpoint is:
        /api/3/bills/{sessionYear}
        
        The API typically uses offset/limit pagination or provides 'next' links.
        
        Args:
            session_year: The legislative session year (e.g., 2023)
            limit: Maximum number of bills per page (default: 1000)
            
        Returns:
            List[str]: List of all bill IDs (e.g., ['S00001', 'S00002', 'A00001', ...])
        """
        all_bill_ids = []
        offset = 0
        page = 1
        
        endpoint = f"{self.base_url}/bills/{session_year}"
        
        # Prepare query parameters
        params = {
            'limit': limit,
            'offset': offset
        }
        if Config.SENATE_API_KEY:
            params['key'] = Config.SENATE_API_KEY
        
        print(f"Fetching all bills from session {session_year}...")
        print(f"Starting with limit={limit}, offset={offset}")
        
        while True:
            try:
                # Apply rate limiting
                self.rate_limiter.wait_if_needed()
                
                # Update offset for current page
                params['offset'] = offset
                
                max_retries = 3
                retry_delay = 1
                
                for attempt in range(max_retries):
                    response = requests.get(
                        endpoint,
                        headers=self.headers,
                        params=params,
                        timeout=60  # Longer timeout for large requests
                    )
                    
                    # Handle rate limiting (HTTP 429)
                    if response.status_code == 429:
                        retry_after = int(response.headers.get('Retry-After', retry_delay * (2 ** attempt)))
                        print(f"Rate limited (429) on page {page}! Waiting {retry_after} seconds before retry {attempt + 1}/{max_retries}...")
                        time.sleep(retry_after)
                        continue  # Retry the request
                    
                    response.raise_for_status()
                    break  # Success, exit retry loop
                else:
                    # All retries failed
                    print(f"Failed to fetch page {page} after {max_retries} attempts")
                    raise requests.exceptions.RequestException(f"Failed after {max_retries} retries")
                
                data = response.json()
                
                # Extract bill IDs from the response
                # The structure may vary, but typically bills are in 'result.items' or 'result'
                result = data.get('result', {})
                
                # Try different possible response structures
                bills = []
                if 'items' in result:
                    bills = result['items']
                elif isinstance(result, list):
                    bills = result
                elif 'bills' in result:
                    bills = result['bills']
                elif 'data' in result:
                    bills = result['data']
                
                if not bills:
                    # If no items found, check if we got a different structure
                    # Sometimes the response is directly a list
                    if isinstance(data, list):
                        bills = data
                    else:
                        print(f"Warning: No bills found in response structure. Keys: {list(data.keys())}")
                        if 'result' in data:
                            print(f"Result keys: {list(result.keys())}")
                        break
                
                # Extract bill IDs from each bill object
                page_bill_ids = []
                for bill in bills:
                    # Try different possible field names for bill ID
                    bill_id = None
                    if isinstance(bill, str):
                        # If bill is already a string ID
                        bill_id = bill
                    elif isinstance(bill, dict):
                        # Try common field names
                        bill_id = (
                            bill.get('printNo') or
                            bill.get('print_no') or
                            bill.get('billId') or
                            bill.get('bill_id') or
                            bill.get('id') or
                            bill.get('basePrintNo') or
                            bill.get('base_print_no')
                        )
                    
                    if bill_id:
                        page_bill_ids.append(bill_id)
                
                if not page_bill_ids:
                    print(f"Warning: No bill IDs extracted from page {page}")
                    print(f"Sample bill object: {bills[0] if bills else 'N/A'}")
                
                all_bill_ids.extend(page_bill_ids)
                print(f"Page {page}: Found {len(page_bill_ids)} bills (Total so far: {len(all_bill_ids)})")
                
                # Check for pagination
                # Look for 'next' link or check if we got fewer results than the limit
                has_next = False
                
                # Check for 'next' link in response
                if 'next' in result:
                    next_url = result['next']
                    if next_url:
                        has_next = True
                        # Extract offset from next URL if it's a full URL
                        # Otherwise, increment offset
                        if 'offset=' in str(next_url):
                            try:
                                offset = int(re.search(r'offset=(\d+)', str(next_url)).group(1))
                            except:
                                offset += len(page_bill_ids)
                        else:
                            offset += len(page_bill_ids)
                
                # Check pagination metadata
                elif 'pagination' in result:
                    pagination = result['pagination']
                    if pagination.get('hasNext', False) or pagination.get('has_next', False):
                        has_next = True
                        offset += len(page_bill_ids)
                    elif 'nextOffset' in pagination or 'next_offset' in pagination:
                        has_next = True
                        offset = pagination.get('nextOffset') or pagination.get('next_offset', offset + len(page_bill_ids))
                
                # If we got fewer results than the limit, we're probably done
                elif len(page_bill_ids) < limit:
                    print(f"Received {len(page_bill_ids)} bills (less than limit {limit}), assuming last page")
                    break
                
                # If no pagination info but we got a full page, try next page
                elif len(page_bill_ids) == limit:
                    # Assume there might be more and try next page
                    offset += len(page_bill_ids)
                    has_next = True
                else:
                    # No more pages
                    break
                
                if not has_next:
                    break
                
                page += 1
                
                # Safety limit to prevent infinite loops
                if page > 1000:
                    print(f"Warning: Reached safety limit of 1000 pages. Stopping.")
                    break
                
            except requests.exceptions.RequestException as e:
                error_msg = str(e)
                if Config.SENATE_API_KEY and Config.SENATE_API_KEY in error_msg:
                    error_msg = error_msg.replace(Config.SENATE_API_KEY, '[REDACTED]')
                print(f"Error fetching bills page {page}: {error_msg}")
                if hasattr(e, 'response') and e.response is not None:
                    print(f"Response status: {e.response.status_code}")
                    try:
                        error_data = e.response.json()
                        print(f"Error response: {error_data}")
                    except:
                        print(f"Response body: {e.response.text[:500]}")
                break
            except Exception as e:
                print(f"Unexpected error on page {page}: {e}")
                break
        
        print(f"\nCompleted fetching bills. Total bill IDs: {len(all_bill_ids)}")
        return all_bill_ids
    
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
        result = bill_data.get('result')
        if not result or not isinstance(result, dict):
            return [], []
        
        amendments = result.get('amendments')
        if not amendments or not isinstance(amendments, dict):
            return [], []
        
        items = amendments.get('items')
        
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
        
        result = bill_data.get('result')
        if not result or not isinstance(result, dict):
            return None
        
        amendments = result.get('amendments')
        if not amendments or not isinstance(amendments, dict):
            return None
        
        items = amendments.get('items')
        
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
    
    def get_amendment_date(
        self,
        bill_id: str,
        session_year: Optional[int] = None,
        version_suffix: str = ''
    ) -> Optional[datetime]:
        """
        Extract the introduction/published date for a specific amendment version.
        
        Args:
            bill_id: The bill identifier (e.g., 'S04609')
            session_year: The legislative session year (e.g., 2023). 
                         If None, will try to infer from current date.
            version_suffix: The version suffix (e.g., '' for base, 'A' for amendment A).
                           Defaults to '' (base version).
            
        Returns:
            datetime: The amendment date, or None if not found
        """
        amendment = self.get_amendment_data(bill_id, session_year, version_suffix)
        
        if not amendment:
            return None
        
        # Try to find date fields in the amendment
        # Based on API inspection, the field is 'publishDate' in format 'YYYY-MM-DD'
        date_str = None
        date_fields = [
            'publishDate',  # Primary field found in API (format: YYYY-MM-DD)
            'publishedDate',
            'published_date',
            'publishedDateTime',
            'published_date_time',
            'introducedDate',
            'introduced_date',
            'actionDate',
            'action_date',
            'date',
            'createdDate',
            'created_date'
        ]
        
        for field in date_fields:
            if field in amendment and amendment[field]:
                date_str = amendment[field]
                break
        
        if not date_str:
            return None
        
        # Parse the date string
        # Try common date formats
        date_formats = [
            '%Y-%m-%dT%H:%M:%S',  # ISO format with time
            '%Y-%m-%dT%H:%M:%S.%f',  # ISO format with microseconds
            '%Y-%m-%dT%H:%M:%SZ',  # ISO format with Z
            '%Y-%m-%d',  # Simple date
            '%m/%d/%Y',  # US format
            '%Y-%m-%d %H:%M:%S',  # SQL format
        ]
        
        for fmt in date_formats:
            try:
                return datetime.strptime(str(date_str), fmt)
            except (ValueError, TypeError):
                continue
        
        # If all formats fail, try to extract just the date part
        try:
            # Extract YYYY-MM-DD pattern
            match = re.search(r'(\d{4}-\d{2}-\d{2})', str(date_str))
            if match:
                return datetime.strptime(match.group(1), '%Y-%m-%d')
        except (ValueError, TypeError):
            pass
        
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
    
    def get_bill_file_path(
        self, 
        bill_id: str, 
        session_year: Optional[int] = None
    ) -> Path:
        """
        Get the file path for a bill based on its ID and session year.
        
        Bills are organized by year in a top-level folder (e.g., 2023/S04609.md)
        
        Args:
            bill_id: The bill identifier (e.g., 'S04609')
            session_year: Optional session year to include as top-level folder
            
        Returns:
            Path: Path to the bill file (e.g., 2023/S04609.md)
        """
        # Sanitize bill_id for filesystem (remove any invalid characters)
        safe_bill_id = re.sub(r'[<>:"/\\|?*]', '_', bill_id)
        
        # Create path with year as top-level folder: 2023/S04609.md
        if session_year:
            return Path(str(session_year)) / f"{safe_bill_id}.md"
        else:
            # If no session year, just use bill ID
            return Path(f"{safe_bill_id}.md")
    
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
            bill_dir: Optional directory to save the PDF in. If None, uses get_bill_file_path
            
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
        
        # Note: PDFs are no longer downloaded, but this method is kept for compatibility
        # Get the bill directory (for legacy support)
        if bill_dir is None:
            # Use the year directory
            if session_year:
                bill_dir = Path(str(session_year))
            else:
                bill_dir = Path(".")
        
        # Create directory if it doesn't exist
        bill_dir.mkdir(exist_ok=True)
        
        # Create PDF file path (not used anymore, but kept for compatibility)
        pdf_file = bill_dir / "bill.pdf"
        
        max_retries = 3
        retry_delay = 1
        response = None
        
        for attempt in range(max_retries):
            try:
                # Apply rate limiting
                self.rate_limiter.wait_if_needed()
                
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
                
                # Handle rate limiting (HTTP 429)
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', retry_delay * (2 ** attempt)))
                    print(f"Rate limited (429) for PDF {bill_id}! Waiting {retry_after} seconds before retry {attempt + 1}/{max_retries}...")
                    time.sleep(retry_after)
                    continue  # Retry the request
                
                # Check if the response is actually a PDF
                content_type = response.headers.get('Content-Type', '')
                if 'pdf' not in content_type.lower() and response.status_code != 200:
                    print(f"Warning: PDF download returned status {response.status_code} or non-PDF content type: {content_type}")
                    return None
                
                # Success - break out of retry loop
                break
                
            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:
                    # Last attempt failed - sanitize and return None
                    error_msg = str(e)
                    if Config.SENATE_API_KEY and Config.SENATE_API_KEY in error_msg:
                        error_msg = error_msg.replace(Config.SENATE_API_KEY, '[REDACTED]')
                    print(f"Error downloading PDF for bill {bill_id}: {error_msg}")
                    return None
                wait_time = retry_delay * (2 ** attempt)
                print(f"PDF download failed for {bill_id} (attempt {attempt + 1}/{max_retries}), retrying in {wait_time} seconds...")
                time.sleep(wait_time)
        
        # If we get here and response is None, all retries failed
        if response is None:
            return None
        
        # Save the PDF
        try:
            with open(pdf_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"Downloaded PDF to: {pdf_file}")
            return pdf_file
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
            bill_dir: Optional directory to save the markdown in. If None, uses get_bill_file_path
            
        Returns:
            Path: Path to the saved file, or None if save failed
        """
        if not markdown_content:
            print(f"Warning: No content to save for bill {bill_id}")
            return None
        
        # Get the bill file path (flat structure: 2023/BillID.md)
        if bill_dir is None:
            markdown_file = self.get_bill_file_path(bill_id, session_year)
        else:
            # Legacy support: if bill_dir is provided, use it
            bill_dir.mkdir(exist_ok=True)
            markdown_file = bill_dir / "bill.md"
        
        # Create the directory if needed
        markdown_file.parent.mkdir(exist_ok=True)
        
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
        # Construct PDF URL
        pdf_url = f"https://legislation.nysenate.gov/pdf/bills/{session_year}/{bill_id}"
        
        markdown_lines = [
            f"# {title}",
            "",
            f"**Bill ID:** {bill_id}",
            f"**Session:** {session_year or 'Unknown'}",
            f"**Sponsor:** {sponsor_name}",
            f"**Status:** {status_desc}",
            f"**PDF:** [{bill_id} PDF]({pdf_url})",
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
        
        # Get the bill file path (flat structure: 2023/BillID.md)
        # Note: bill_dir is no longer used, but kept for compatibility
        
        # Save the markdown file
        markdown_path = self.save_bill_as_markdown(bill_id, markdown_content, session_year, bill_dir)
        
        # Return the markdown path
        return markdown_path
    
    def process_bill_versions_with_git(
        self,
        bill_id: str,
        session_year: Optional[int] = None,
        use_html: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """
        Process all bill versions in chronological order and commit each to Git.
        
        For each version:
        1. Fetch the text for that specific version
        2. Overwrite the existing bill.md file with this version's text (includes PDF link in metadata)
        3. Stage the file: git add bill.md
        4. Commit the change: git commit -m "Amendment [Suffix] for [BillID]"
        
        Commits happen in chronological order (Original -> A -> B) so the Git history
        reflects the real-world timeline.
        
        Args:
            bill_id: The base bill identifier (e.g., 'S04609')
            session_year: The legislative session year (e.g., 2023)
            use_html: If True, prefer HTML version; if False, use plain text
            
        Returns:
            Tuple[bool, Optional[str]]: (success, error_message) - True if all versions were processed successfully, False with error message otherwise
        """
        if session_year is None:
            from datetime import datetime
            session_year = datetime.now().year
        
        # Get all versions in chronological order
        version_suffixes, full_bill_ids = self.get_bill_versions(bill_id, session_year)
        
        if not version_suffixes:
            error_msg = f"No versions found for bill {bill_id} - bill may not exist or API returned no amendments"
            print(error_msg)
            return False, error_msg
        
        # Get bill file path (flat structure: 2023/BillID.md)
        markdown_file = self.get_bill_file_path(bill_id, session_year)
        markdown_file.parent.mkdir(exist_ok=True)
        
        # Fetch bill metadata once (same for all versions)
        bill_data = self.fetch_bill(bill_id, session_year)
        if not bill_data:
            error_msg = f"Failed to fetch bill data for {bill_id} - API request failed or bill not found"
            print(error_msg)
            return False, error_msg
        
        result = bill_data.get('result')
        if not result or not isinstance(result, dict):
            error_msg = f"Invalid API response for {bill_id} - 'result' field is missing or invalid"
            print(error_msg)
            return False, error_msg
        
        title = result.get('title', f'Bill {bill_id}')
        summary = result.get('summary', '')
        sponsor = result.get('sponsor')
        sponsor_name = 'Unknown'
        if sponsor and isinstance(sponsor, dict):
            member = sponsor.get('member')
            if member and isinstance(member, dict):
                sponsor_name = member.get('fullName', 'Unknown')
        
        status = result.get('status')
        status_desc = 'Unknown'
        if status and isinstance(status, dict):
            status_desc = status.get('statusDesc', 'Unknown')
        
        success_count = 0
        
        # Process each version in chronological order
        for i, (suffix, full_bill_id) in enumerate(zip(version_suffixes, full_bill_ids)):
            print(f"\n{'='*60}")
            print(f"Processing version {i+1}/{len(version_suffixes)}: {full_bill_id}")
            print(f"{'='*60}")
            
            # Check if this version has already been processed
            if self.progress_tracker.is_processed(bill_id, suffix):
                print(f"Skipping {full_bill_id} - already processed (found in progress.txt)")
                success_count += 1
                continue
            
            # Fetch the text for this specific version
            full_text = self.get_full_text(bill_id, session_year, version_suffix=suffix)
            
            if not full_text:
                print(f"Warning: Failed to fetch text for version {full_bill_id}, skipping...")
                continue
            
            # Build markdown content with metadata
            # Construct PDF URL
            pdf_url = f"https://legislation.nysenate.gov/pdf/bills/{session_year}/{full_bill_id}"
            
            markdown_lines = [
                f"# {title}",
                "",
                f"**Bill ID:** {full_bill_id}",
                f"**Session:** {session_year or 'Unknown'}",
                f"**Sponsor:** {sponsor_name}",
                f"**Status:** {status_desc}",
                f"**PDF:** [{full_bill_id} PDF]({pdf_url})",
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
            
            # Stage the markdown file with git add
            git_add_success = False
            try:
                import os
                repo_root = Path.cwd()
                
                # Get relative path using os.path.relpath which handles Windows paths better
                markdown_abs = markdown_file.resolve()
                repo_abs = repo_root.resolve()
                markdown_relative = os.path.relpath(markdown_abs, repo_abs)
                
                result = subprocess.run(
                    ['git', 'add', markdown_relative],
                    capture_output=True,
                    text=True,
                    check=False,
                    cwd=str(repo_root)
                )
                if result.returncode != 0:
                    print(f"Warning: git add failed for markdown: {result.stderr}")
                    print(f"  Skipping commit for {full_bill_id}")
                else:
                    print(f"Staged file: {markdown_relative}")
                    git_add_success = True
            except Exception as e:
                print(f"Error staging file: {e}")
                print(f"  Skipping commit for {full_bill_id}")
                continue
            
            # Commit the change (only if git add succeeded)
            if git_add_success:
                try:
                    # Get amendment date for this version
                    amendment_date = self.get_amendment_date(bill_id, session_year, version_suffix=suffix)
                    
                    # Get sponsorMemo for this version to use as commit body
                    sponsor_memo = self.get_sponsor_memo_first_paragraph(bill_id, session_year, version_suffix=suffix)
                    
                    # Create commit message in format: 'Bill [ID] version [Suffix] - [Sponsor Name]'
                    if suffix == '':
                        version_label = 'original'
                    else:
                        version_label = suffix
                    
                    commit_title = f"Bill {bill_id} version {version_label} - {sponsor_name}"
                    
                    # Build commit command with multi-line message
                    commit_args = ['git', 'commit', '-m', commit_title]
                    
                    # Add sponsorMemo as body if available
                    if sponsor_memo:
                        commit_args.extend(['-m', sponsor_memo])
                        print(f"Commit message includes sponsor memo: {sponsor_memo[:100]}...")
                    
                    # Set environment variables for commit date if amendment date is available
                    env = None
                    if amendment_date:
                        # Format date for git: YYYY-MM-DD HH:MM:SS
                        date_str = amendment_date.strftime('%Y-%m-%d %H:%M:%S')
                        env = os.environ.copy()
                        env['GIT_AUTHOR_DATE'] = date_str
                        env['GIT_COMMITTER_DATE'] = date_str
                        print(f"Setting commit date to: {date_str}")
                    else:
                        print(f"Warning: Could not determine amendment date for {full_bill_id}, using current date")
                    
                    result = subprocess.run(
                        commit_args,
                        capture_output=True,
                        text=True,
                        check=False,
                        env=env
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
                        if amendment_date:
                            print(f"  Date: {amendment_date.strftime('%Y-%m-%d')}")
                        success_count += 1
                        
                        # Mark as processed in progress file
                        self.progress_tracker.mark_processed(bill_id, suffix)
                except Exception as e:
                    print(f"Error committing: {e}")
                    continue
        
        print(f"\n{'='*60}")
        print(f"Processing complete: {success_count}/{len(version_suffixes)} versions committed")
        print(f"{'='*60}\n")
        
        success = success_count == len(version_suffixes)
        if not success:
            error_msg = f"Only {success_count}/{len(version_suffixes)} versions were successfully processed for bill {bill_id}"
        else:
            error_msg = None
        return success, error_msg
    
    def process_all_bills_with_git(
        self,
        session_year: int = 2023,
        bill_ids: Optional[List[str]] = None,
        use_html: bool = False
    ) -> Dict[str, Tuple[bool, Optional[str]]]:
        """
        Process all bills from a session year, committing each version with historical dates.
        
        For each bill:
        1. Get all versions (original through latest amendment)
        2. For each version:
           - Fetch the fullText
           - Overwrite bill.md and bill.pdf
           - Commit with message: 'Bill [ID] version [Suffix] - [Sponsor Name]'
           - Set commit date to the actual amendment introduction date
        
        Args:
            session_year: The legislative session year (e.g., 2023)
            bill_ids: Optional list of bill IDs to process. If None, fetches all bills for the session.
            use_html: If True, prefer HTML version; if False, use plain text
            
        Returns:
            Dict[str, Tuple[bool, Optional[str]]]: Dictionary mapping bill_id to (success, error_message) tuple
        """
        # Get bill IDs if not provided
        if bill_ids is None:
            print(f"Fetching all bill IDs for session {session_year}...")
            bill_ids = self.fetch_all_bill_ids(session_year=session_year)
        
        if not bill_ids:
            print(f"No bills found for session {session_year}")
            return {}
        
        print(f"\n{'='*60}")
        print(f"Processing {len(bill_ids)} bills from session {session_year}")
        print(f"{'='*60}\n")
        
        results = {}
        successful_bills = 0
        failed_bills = 0
        
        for i, bill_id in enumerate(bill_ids, 1):
            print(f"\n{'#'*60}")
            print(f"Processing bill {i}/{len(bill_ids)}: {bill_id}")
            print(f"{'#'*60}\n")
            
            try:
                # Process all versions for this bill
                success, error_msg = self.process_bill_versions_with_git(
                    bill_id=bill_id,
                    session_year=session_year,
                    use_html=use_html
                )
                results[bill_id] = (success, error_msg)
                
                if success:
                    successful_bills += 1
                else:
                    failed_bills += 1
                    print(f"Warning: Failed to process bill {bill_id}")
                    if error_msg:
                        print(f"  Reason: {error_msg}")
                    
            except Exception as e:
                error_msg = f"Exception during processing: {str(e)}"
                print(f"Error processing bill {bill_id}: {e}")
                results[bill_id] = (False, error_msg)
                failed_bills += 1
                continue
        
        print(f"\n{'='*60}")
        print(f"Processing complete!")
        print(f"  Total bills: {len(bill_ids)}")
        print(f"  Successful: {successful_bills}")
        print(f"  Failed: {failed_bills}")
        print(f"{'='*60}\n")
        
        return results


if __name__ == "__main__":
    # Process the full 2023 bill archive
    print("="*60)
    print("NY Legislative Git - Processing 2023 Bill Archive")
    print("="*60)
    print("Features:")
    print("  - Rate limiting: 5 requests/second (with 429 error handling)")
    print("  - Progress tracking: progress.txt (resumable)")
    print("  - Historical commit dates from amendment publishDate")
    print("="*60)
    print()
    
    # Initialize fetcher with rate limiting and progress tracking
    # Increased to 10 requests/second (can be adjusted if throttled)
    fetcher = BillFetcher(rate_limit=10.0, progress_file="progress.txt")
    
    # Fetch all bill IDs from 2023 session
    print("Step 1: Fetching all bill IDs from 2023 session...")
    print("(This may take a few minutes due to pagination)")
    print()
    all_bill_ids = fetcher.fetch_all_bill_ids(session_year=2023)
    
    print(f"\nTotal bills found: {len(all_bill_ids)}")
    if all_bill_ids:
        print(f"First 10 bill IDs: {all_bill_ids[:10]}")
        print(f"Last 10 bill IDs: {all_bill_ids[-10:]}")
    
    # Process all bills
    print("\n" + "="*60)
    print("Step 2: Processing all bills with Git commits")
    print("="*60)
    print("Note: This will take a very long time (24,269+ bills)")
    print("Progress is saved to progress.txt - you can resume if interrupted")
    print("="*60)
    print()
    
    results = fetcher.process_all_bills_with_git(
        session_year=2023,
        bill_ids=all_bill_ids,
        use_html=False
    )
    
    print("\n" + "="*60)
    print("Final Results:")
    print("="*60)
    successful = sum(1 for result in results.values() if (isinstance(result, tuple) and result[0]) or (not isinstance(result, tuple) and result))
    failed = len(results) - successful
    print(f"  Total bills processed: {len(results)}")
    print(f"  Successful: {successful}")
    print(f"  Failed: {failed}")
    
    # List failed bills with error messages
    failed_bills = []
    for bill_id, result in results.items():
        if isinstance(result, tuple):
            success, error_msg = result
            if not success:
                failed_bills.append((bill_id, error_msg))
        elif not result:
            failed_bills.append((bill_id, "Unknown error"))
    
    if failed_bills:
        print(f"\nFailed bills ({len(failed_bills)}):")
        for bill_id, error_msg in failed_bills:
            print(f"  - {bill_id}")
            if error_msg:
                print(f"    Reason: {error_msg}")
    
    print("="*60)
    print("\nProgress saved to: progress.txt")
    print("You can review the Git history to see all commits with historical dates.")
