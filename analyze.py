#!/usr/bin/env python3
"""
Polymarket BTC Prediction Market Analysis Tool

Analyzes CSV files containing BTC prediction market data with time,price columns.
Detects cycles based on price resets and provides detailed statistics.
"""

import argparse
import glob
import os
import re
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import pandas as pd


class CycleAnalyzer:
    """Analyzes prediction market cycles from CSV data."""
    
    # Cycle detection parameters
    RESET_PRICE_MIN = 0.45
    RESET_PRICE_MAX = 0.55
    YES_THRESHOLD = 0.90
    NO_THRESHOLD = 0.10
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.file_name = os.path.basename(file_path)
        self.df = None
        self.cycles = []
        
    def load_data(self) -> bool:
        """Load CSV file and handle edge cases."""
        try:
            # Read CSV file
            self.df = pd.read_csv(self.file_path)
            
            # Check required columns
            if 'time' not in self.df.columns or 'price' not in self.df.columns:
                print(f"Error: CSV must have 'time' and 'price' columns")
                return False
            
            # Handle 'none' values in price column
            self.df['price'] = pd.to_numeric(self.df['price'], errors='coerce')
            
            # Remove rows with NaN prices
            initial_count = len(self.df)
            self.df = self.df.dropna(subset=['price'])
            removed_count = initial_count - len(self.df)
            
            if removed_count > 0:
                print(f"  Note: Removed {removed_count} rows with invalid price values")
            
            # Convert time to datetime
            self.df['time'] = pd.to_datetime(self.df['time'], errors='coerce')
            self.df = self.df.dropna(subset=['time'])
            
            # Sort by time
            self.df = self.df.sort_values('time').reset_index(drop=True)
            
            return len(self.df) > 0
            
        except Exception as e:
            print(f"Error loading file: {e}")
            return False
    
    def detect_cycles(self):
        """Detect cycles based on price resets near 0.50."""
        if self.df is None or len(self.df) == 0:
            return
        
        cycles = []
        current_cycle_start = 0
        
        for i in range(1, len(self.df)):
            prev_price = self.df.loc[i-1, 'price']
            curr_price = self.df.loc[i, 'price']
            
            # Detect cycle reset: price moves back to ~0.50 range
            # This happens when previous price was far from 0.50 and current is near 0.50
            is_prev_extreme = (prev_price < self.RESET_PRICE_MIN or 
                             prev_price > self.RESET_PRICE_MAX)
            is_curr_reset = (self.RESET_PRICE_MIN <= curr_price <= self.RESET_PRICE_MAX)
            
            if is_prev_extreme and is_curr_reset:
                # End previous cycle
                if i - current_cycle_start > 1:  # Must have at least 2 points
                    cycle = self._create_cycle_data(current_cycle_start, i - 1)
                    if cycle:
                        cycles.append(cycle)
                
                # Start new cycle
                current_cycle_start = i
        
        # Add final cycle if it has enough points
        if len(self.df) - current_cycle_start > 1:
            cycle = self._create_cycle_data(current_cycle_start, len(self.df) - 1)
            if cycle:
                cycles.append(cycle)
        
        self.cycles = cycles
    
    def _create_cycle_data(self, start_idx: int, end_idx: int) -> Optional[Dict]:
        """Create cycle data dictionary from start and end indices."""
        try:
            cycle_df = self.df.loc[start_idx:end_idx]
            
            if len(cycle_df) == 0:
                return None
            
            start_time = cycle_df.iloc[0]['time']
            end_time = cycle_df.iloc[-1]['time']
            start_price = cycle_df.iloc[0]['price']
            end_price = cycle_df.iloc[-1]['price']
            max_price = cycle_df['price'].max()
            min_price = cycle_df['price'].min()
            num_points = len(cycle_df)
            
            # Determine outcome
            if end_price >= self.YES_THRESHOLD:
                outcome = "YES"
            elif end_price <= self.NO_THRESHOLD:
                outcome = "NO"
            else:
                outcome = "UNDETERMINED"
            
            duration = (end_time - start_time).total_seconds()
            
            return {
                'start_time': start_time,
                'end_time': end_time,
                'start_price': start_price,
                'end_price': end_price,
                'outcome': outcome,
                'max_price': max_price,
                'min_price': min_price,
                'num_points': num_points,
                'duration': duration
            }
        except Exception as e:
            print(f"  Warning: Error creating cycle data: {e}")
            return None
    
    def print_analysis(self):
        """Print detailed analysis to terminal."""
        if self.df is None or len(self.df) == 0:
            print(f"\n{'='*80}")
            print(f"File: {self.file_name}")
            print(f"Error: No valid data to analyze")
            print(f"{'='*80}\n")
            return
        
        # Extract date from filename
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', self.file_name)
        date_str = date_match.group(1) if date_match else "Unknown"
        
        print(f"\n{'='*80}")
        print(f"FILE ANALYSIS: {self.file_name}")
        print(f"Date: {date_str}")
        print(f"{'='*80}")
        
        # Basic statistics
        print(f"\nBASIC STATISTICS:")
        print(f"  Total data points: {len(self.df)}")
        print(f"  Time range: {self.df['time'].min()} to {self.df['time'].max()}")
        print(f"  Complete cycles detected: {len(self.cycles)}")
        
        # Cycle details
        if len(self.cycles) > 0:
            print(f"\n{'-'*80}")
            print(f"CYCLE DETAILS:")
            print(f"{'-'*80}")
            
            for idx, cycle in enumerate(self.cycles, 1):
                print(f"\nCycle {idx}:")
                print(f"  Start time: {cycle['start_time']}")
                print(f"  End time: {cycle['end_time']}")
                print(f"  Duration: {cycle['duration']:.1f} seconds")
                print(f"  Starting price: {cycle['start_price']:.4f}")
                print(f"  Ending price: {cycle['end_price']:.4f}")
                print(f"  Outcome: {cycle['outcome']}")
                print(f"  Price range: {cycle['min_price']:.4f} to {cycle['max_price']:.4f}")
                print(f"  Data points: {cycle['num_points']}")
        
        # Summary statistics
        if len(self.cycles) > 0:
            print(f"\n{'-'*80}")
            print(f"SUMMARY STATISTICS:")
            print(f"{'-'*80}")
            
            yes_count = sum(1 for c in self.cycles if c['outcome'] == 'YES')
            no_count = sum(1 for c in self.cycles if c['outcome'] == 'NO')
            undetermined_count = sum(1 for c in self.cycles if c['outcome'] == 'UNDETERMINED')
            
            print(f"  Total YES outcomes: {yes_count}")
            print(f"  Total NO outcomes: {no_count}")
            print(f"  Total UNDETERMINED outcomes: {undetermined_count}")
            
            # Win rates (only count determined outcomes)
            determined_count = yes_count + no_count
            if determined_count > 0:
                yes_win_rate = (yes_count / determined_count) * 100
                no_win_rate = (no_count / determined_count) * 100
                print(f"  Win rate if always bet YES: {yes_win_rate:.2f}%")
                print(f"  Win rate if always bet NO: {no_win_rate:.2f}%")
            
            # Average statistics
            avg_duration = sum(c['duration'] for c in self.cycles) / len(self.cycles)
            avg_points = sum(c['num_points'] for c in self.cycles) / len(self.cycles)
            
            print(f"  Average cycle duration: {avg_duration:.1f} seconds ({avg_duration/60:.2f} minutes)")
            print(f"  Average data points per cycle: {avg_points:.1f}")
        
        print(f"\n{'='*80}\n")


def find_csv_files(date: Optional[str] = None) -> List[str]:
    """
    Find CSV files matching Polymarket BTC patterns.
    
    Args:
        date: Optional date filter in YYYY-MM-DD format
    
    Returns:
        List of matching file paths
    """
    patterns = [
        'BTC5MIN_*.csv',
        'BTC_*.csv',
        'BTC1MIN_*.csv',
        'BTC10MIN_*.csv',
        'BTC30MIN_*.csv',
        # Add more patterns as needed
    ]
    
    all_files = []
    for pattern in patterns:
        files = glob.glob(pattern)
        all_files.extend(files)
    
    # Remove duplicates and sort
    all_files = sorted(set(all_files))
    
    # Filter by date if specified
    if date:
        all_files = [f for f in all_files if date in f]
    
    return all_files


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Analyze Polymarket BTC prediction market CSV data'
    )
    parser.add_argument(
        '--date',
        type=str,
        help='Filter files by date (YYYY-MM-DD format)'
    )
    parser.add_argument(
        '--file',
        type=str,
        help='Analyze a specific file'
    )
    
    args = parser.parse_args()
    
    # Determine which files to analyze
    if args.file:
        if not os.path.exists(args.file):
            print(f"Error: File '{args.file}' not found")
            return 1
        files_to_analyze = [args.file]
    else:
        files_to_analyze = find_csv_files(args.date)
    
    if not files_to_analyze:
        if args.date:
            print(f"No CSV files found matching date: {args.date}")
        else:
            print("No CSV files found matching expected patterns (BTC5MIN_*.csv, BTC_*.csv, etc.)")
        print("\nExpected file patterns:")
        print("  - BTC5MIN_YYYY-MM-DD.csv")
        print("  - BTC_YYYY-MM-DD.csv")
        print("  - BTC1MIN_YYYY-MM-DD.csv")
        print("  - BTC10MIN_YYYY-MM-DD.csv")
        print("  - BTC30MIN_YYYY-MM-DD.csv")
        return 1
    
    print(f"\nFound {len(files_to_analyze)} file(s) to analyze:")
    for f in files_to_analyze:
        print(f"  - {f}")
    
    # Analyze each file
    for file_path in files_to_analyze:
        analyzer = CycleAnalyzer(file_path)
        if analyzer.load_data():
            analyzer.detect_cycles()
            analyzer.print_analysis()
        else:
            print(f"\nSkipping {file_path} due to errors\n")
    
    return 0


if __name__ == '__main__':
    exit(main())
