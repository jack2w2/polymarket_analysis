# polymarket_analysis

Analysis tool for Polymarket BTC prediction market data.

## Overview

This repository provides a Python script to analyze daily CSV files containing Polymarket BTC prediction market data. The script groups data into fixed 5/15-minute cycles, validates data quality, and estimates strategy price levels.

## Features

- **Auto-detection** of CSV files matching patterns: `BTC5MIN_*.csv`, `BTC_*.csv`, etc.
- **Fixed 5/15-minute cycle grouping** and data validity checks
- **Strategy price estimation** for levels A-K
- **Chinese output** summarizing cycle quality and strategy stats
- **Edge case handling**:
  - `none` values in price column (counted as invalid)
  - Missing per-second data within a cycle (invalid if >5%)

## Installation

1. Clone this repository:
```bash
git clone https://github.com/jack2w2/polymarket_analysis.git
cd polymarket_analysis
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Analyze all CSV files in current directory (default 5-minute cycles):
```bash
python analyze.py
```

### Analyze files for a specific date:
```bash
python analyze.py --date 2026-02-14
```

### Analyze a specific file (15-minute cycles):
```bash
python analyze.py --file BTC5MIN_2026-02-14.csv --interval 15
```

### Get help:
```bash
python analyze.py --help
```

## Data Format

CSV files should have the following format:
```csv
time,price
2026-02-14 08:00:00,0.50
2026-02-14 08:00:02,0.52
2026-02-14 08:00:04,0.55
...
```

- **time**: Timestamp in UTC+8 timezone
- **price**: Market probability between 0.01 and 0.99 (invalid entries may be `none`)

## Expected File Patterns

The script looks for files matching these patterns:
- `BTC5MIN_YYYY-MM-DD.csv` — 5-minute cycle data
- `BTC_YYYY-MM-DD.csv` — 15-minute cycle data
- `BTC1MIN_YYYY-MM-DD.csv` — 1-minute cycle data
- `BTC10MIN_YYYY-MM-DD.csv` — 10-minute cycle data
- `BTC30MIN_YYYY-MM-DD.csv` — 30-minute cycle data

## Output Example

```
Found 1 file(s) to analyze:
  - BTC5MIN_2026-02-14.csv

================================================================================
FILE ANALYSIS: BTC5MIN_2026-02-14.csv
Date: 2026-02-14
================================================================================

BASIC STATISTICS:
  Total data points: 26
  Time range: 2026-02-14 08:00:00 to 2026-02-14 08:15:10
  Complete cycles detected: 4

--------------------------------------------------------------------------------
CYCLE DETAILS:
--------------------------------------------------------------------------------

Cycle 1:
  Start time: 2026-02-14 08:00:00
  End time: 2026-02-14 08:00:12
  Duration: 12.0 seconds
  Starting price: 0.5000
  Ending price: 0.9500
  Outcome: YES
  Price range: 0.5000 to 0.9500
  Data points: 7

...

--------------------------------------------------------------------------------
SUMMARY STATISTICS:
--------------------------------------------------------------------------------
  Total YES outcomes: 2
  Total NO outcomes: 2
  Total UNDETERMINED outcomes: 0
  Win rate if always bet YES: 50.00%
  Win rate if always bet NO: 50.00%
  Average cycle duration: 11.0 seconds (0.18 minutes)
  Average data points per cycle: 6.5

================================================================================
```

## License

MIT
