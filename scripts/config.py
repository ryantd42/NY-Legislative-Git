"""
Configuration module for NY Legislative Git project.

This module handles secure loading of API keys and configuration
from environment variables.
"""

import os
from typing import Optional, Tuple

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv not installed, skip .env loading
    pass


class Config:
    """Configuration class for API keys and settings."""
    
    # NYS Senate Open Legislation API
    # Note: This API may or may not require authentication
    # Check API documentation for requirements
    SENATE_API_KEY: Optional[str] = os.getenv('NYS_SENATE_API_KEY')
    SENATE_API_BASE_URL: str = os.getenv(
        'NYS_SENATE_API_BASE_URL',
        'https://legislation.nysenate.gov/api/3'
    )
    
    # Open NY (Socrata) API
    # Socrata typically uses App Token and optionally App Secret
    SOCRATA_APP_TOKEN: Optional[str] = os.getenv('SOCRATA_APP_TOKEN')
    SOCRATA_APP_SECRET: Optional[str] = os.getenv('SOCRATA_APP_SECRET')
    SOCRATA_BASE_URL: str = os.getenv(
        'SOCRATA_BASE_URL',
        'https://data.ny.gov'
    )
    
    # Dataset identifier for Lobbyist Bi-Monthly Reports
    LOBBYIST_DATASET_ID: str = os.getenv(
        'LOBBYIST_DATASET_ID',
        'your-dataset-id-here'  # Will need to be updated with actual dataset ID
    )
    
    @classmethod
    def validate(cls) -> Tuple[bool, list[str]]:
        """
        Validate that required configuration is present.
        
        Returns:
            tuple[bool, list[str]]: (is_valid, list_of_warnings)
        """
        warnings = []
        
        # Check for API keys in environment (not hardcoded)
        if not cls.SENATE_API_KEY:
            warnings.append("NYS_SENATE_API_KEY is not set. Some features may not work.")
        elif len(cls.SENATE_API_KEY) < 10:
            warnings.append("NYS_SENATE_API_KEY appears to be invalid (too short).")
        
        # Warn if keys look like they might be example/placeholder values
        placeholder_patterns = ['your_', 'example', 'placeholder', 'test', 'demo']
        if cls.SENATE_API_KEY:
            key_lower = cls.SENATE_API_KEY.lower()
            if any(pattern in key_lower for pattern in placeholder_patterns):
                warnings.append("NYS_SENATE_API_KEY appears to be a placeholder value.")
        
        return len(warnings) == 0, warnings
    
    @classmethod
    def check_for_hardcoded_secrets(cls) -> list[str]:
        """
        Check if any secrets appear to be hardcoded in the config.
        This is a safety check for open source projects.
        
        Returns:
            list[str]: List of warnings if any secrets are detected
        """
        warnings = []
        
        # This method is a placeholder for future secret detection
        # Actual secret scanning is done by check_secrets.py script
        # which scans source files directly
        
        return warnings
    
    @classmethod
    def get_senate_headers(cls) -> dict:
        """
        Get headers for NYS Senate API requests.
        
        Returns:
            dict: Headers dictionary for API requests
        """
        headers = {
            'Accept': 'application/json',
            'User-Agent': 'NY-Legislative-Git/1.0'
        }
        
        if cls.SENATE_API_KEY:
            headers['X-API-Key'] = cls.SENATE_API_KEY
        
        return headers
    
    @classmethod
    def get_socrata_headers(cls) -> dict:
        """
        Get headers for Socrata API requests.
        
        Returns:
            dict: Headers dictionary for API requests
        """
        headers = {
            'Accept': 'application/json',
            'X-App-Token': cls.SOCRATA_APP_TOKEN or ''
        }
        
        if cls.SOCRATA_APP_SECRET:
            headers['X-App-Secret'] = cls.SOCRATA_APP_SECRET
        
        return headers
