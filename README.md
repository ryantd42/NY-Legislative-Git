# NY Legislative Git

A civic tech project for fetching and analyzing New York State legislative bills and their associated lobbyist data.

## Features

- Fetch bill full text from NYS Senate Open Legislation API
- Convert HTML bill text to Markdown
- Query Open NY (Socrata) API for lobbyist bi-monthly reports
- Match bills with lobbyist activity
- Generate markdown reports with bill text and lobbyist influence data

## Setup

### Prerequisites

- Python 3.8+
- API keys for:
  - NYS Senate Open Legislation API
  - Open NY (Socrata) API

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd Civic
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv .venv
   .venv\Scripts\Activate.ps1  # Windows PowerShell
   # or
   source .venv/bin/activate   # macOS/Linux
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   # Copy the example file
   cp .env.example .env
   
   # Edit .env and add your API keys
   # NEVER commit .env to version control!
   ```

### Environment Variables

Create a `.env` file with the following variables:

```env
# NYS Senate Open Legislation API
NYS_SENATE_API_KEY=your_senate_api_key_here
NYS_SENATE_API_BASE_URL=https://legislation.nysenate.gov/api/3

# Open NY (Socrata) API
SOCRATA_APP_TOKEN=your_socrata_app_token_here
SOCRATA_APP_SECRET=your_socrata_app_secret_here
SOCRATA_BASE_URL=https://data.ny.gov
```

**⚠️ Security Warning**: Never commit your `.env` file to version control. It is already excluded in `.gitignore`.

## Usage

### Fetch a Bill

```python
from fetch_bill import BillFetcher

fetcher = BillFetcher()
full_text = fetcher.get_full_text('S04609', session_year=2023)

if full_text:
    print(f"Fetched {len(full_text)} characters of bill text")
```

### Run Security Checks

Before committing code, always run:

```bash
python check_secrets.py
```

This will verify that no secrets are accidentally committed.

## Security

This project takes security seriously. Please read [SECURITY.md](SECURITY.md) for:
- How to report vulnerabilities
- Security best practices
- How to handle accidentally committed secrets

### Quick Security Checklist

- ✅ `.env` file is in `.gitignore`
- ✅ No API keys hardcoded in source code
- ✅ Run `check_secrets.py` before committing
- ✅ Review PRs for accidentally committed secrets

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run security checks: `python check_secrets.py`
5. Submit a pull request

**Important**: Before submitting a PR, ensure:
- No secrets are in the code
- All tests pass
- Security checks pass

## License

[Your License Here]

## Acknowledgments

- NYS Senate Open Legislation API
- Open NY (Socrata) for lobbyist data
