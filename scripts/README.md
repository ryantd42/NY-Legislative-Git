# NY Legislative Git - Scripts

## Usage

### Fetch Bills for a Session Year

The `fetch_bill.py` script can process bills for any session year. By default it processes 2023, but you can specify any year.

**For 2023 session:**
```bash
cd scripts
python fetch_bill.py
# or explicitly:
python fetch_bill.py 2023
```

**For 2024-2025 session:**
```bash
cd scripts
python fetch_bill.py 2024
```

**For 2025 session:**
```bash
cd scripts
python fetch_bill.py 2025
```

## Features

- **Rate limiting**: 10 requests/second (with automatic 429 error handling)
- **Progress tracking**: Separate `progress_YYYY.txt` file for each session year (resumable)
- **Historical commit dates**: Uses amendment `publishDate` for accurate Git history
- **Flat structure**: Bills saved as `YYYY/BillID.md` (e.g., `2024/S01234.md`)

## Output Structure

```
/ (Root)
├── 2023/
│   ├── A100.md
│   ├── S01234.md
│   └── ...
├── 2024/
│   ├── A100.md
│   ├── S01234.md
│   └── ...
└── scripts/
    ├── fetch_bill.py
    ├── progress_2023.txt
    ├── progress_2024.txt
    └── ...
```

## Notes

- Each session year gets its own progress file (`progress_YYYY.txt`)
- Bills are automatically organized by year in separate folders
- The script can be interrupted and resumed - it will skip already-processed bills
- All bills include PDF links in the metadata (PDFs are not stored, only linked)
