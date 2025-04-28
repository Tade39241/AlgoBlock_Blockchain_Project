import pandas as pd
import numpy as np
import argparse
import os
import csv

OUTPUT_FILENAME = "summary_results.csv"


def analyze_metrics(csv_filepath, nodes_val, volume_val, replicate_val):
    """
    Parses timestamped snapshots from blockchain_data.csv, computes metrics,
    and outputs a summary line.

    Args:
        csv_filepath (str): Path to the blockchain_data.csv file.
        nodes_val (int): Number of nodes (for output).
        volume_val (str): Transaction volume description (for output).
        replicate_val (int): Replicate number (for output).
    """

    # Use the globally defined output filename
    output_csv_path = OUTPUT_FILENAME

    try:
        df = pd.read_csv(csv_filepath)
    except FileNotFoundError:
        print(f"Error: File not found at {csv_filepath}")
        return
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        return

    # --- Data Cleaning and Preparation ---
    # Convert timestamp to datetime objects
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    # Convert relevant columns to numeric, coercing errors to NaN
    numeric_cols = ['height', 'mempool_size', 'total_transactions',
                    'last_block_timestamp', 'api_cpu_percent',
                    'api_memory_percent', 'api_disk_percent']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # Sort by timestamp and node_index (important for diff calculations)
    df = df.sort_values(by=['timestamp', 'node_index']).reset_index(drop=True)

    # Drop rows where essential data might be missing after coercion
    df = df.dropna(subset=['timestamp', 'height', 'last_block_timestamp', 'total_transactions'])
    if df.empty:
        print("Error: No valid data rows found after cleaning.")
        return

    # --- Calculate Run Duration ---
    run_start_time = df['timestamp'].min()
    run_end_time = df['timestamp'].max()
    run_duration_seconds = (run_end_time - run_start_time).total_seconds()
    if run_duration_seconds <= 0:
        print("Warning: Run duration is zero or negative. Cannot calculate rates.")
        run_duration_seconds = np.nan # Avoid division by zero

    # --- Block Time Calculation ---
    # Get unique block timestamps associated with height increases
    block_production_times = df.sort_values('last_block_timestamp')['last_block_timestamp'].unique()
    block_production_times = block_production_times[block_production_times > 0] # Exclude potential zeros

    block_times_seconds = np.diff(block_production_times)

    if len(block_times_seconds) > 0:
        avg_block_time = np.mean(block_times_seconds)
        std_block_time = np.std(block_times_seconds)
    else:
        avg_block_time = np.nan
        std_block_time = np.nan

    # --- Throughput Calculation ---
    # Use the max 'total_transactions' seen at the start and end
    # This assumes 'total_transactions' is a cumulative count reported by the node
    start_total_tx = df[df['timestamp'] == run_start_time]['total_transactions'].max()
    end_total_tx = df[df['timestamp'] == run_end_time]['total_transactions'].max()

    total_tx_processed = end_total_tx - start_total_tx
    if pd.isna(total_tx_processed) or total_tx_processed < 0:
        total_tx_processed = 0 # Handle NaN or cases where end < start

    throughput_tx_s = total_tx_processed / run_duration_seconds if run_duration_seconds > 0 else 0

    # --- Mempool Calculation ---
    peak_mempool = df['mempool_size'].max()
    # Sum mempool size across all nodes in the last timestamp
    final_mempool = df[df['timestamp'] == run_end_time]['mempool_size'].sum()

    # --- CPU Calculation ---
    # Calculate interval duration based on collector timestamps
    # Group by timestamp first to handle multiple nodes per timestamp correctly
    df['interval_duration'] = df.groupby('node_index')['timestamp'].diff().dt.total_seconds()
    # Estimate interval for the first entry using the median of subsequent intervals
    median_interval = df['interval_duration'].median()
    if pd.isna(median_interval):
         median_interval = 5 # Fallback if median can't be calculated (e.g., too few points)
    df['interval_duration'] = df['interval_duration'].fillna(median_interval)

    # Calculate CPU seconds per entry: (percent/100) * duration_of_interval
    df['cpu_seconds'] = (df['api_cpu_percent'] / 100.0) * df['interval_duration']
    total_cpu_seconds = df['cpu_seconds'].sum() # Sum across all nodes and intervals

    # --- Memory Calculation ---
    peak_memory_percent = df['api_memory_percent'].max()
    # Note: Cannot calculate peak_memory_mb without knowing total system memory.

    # --- Prepare Output Data ---
    header = [
        "nodes", "volume", "replicate",
        "avg_block_time", "std_block_time",
        "throughput_tx_s",
        "peak_mempool", "final_mempool",
        "total_cpu_seconds", "peak_memory_percent"
    ]

    data_row = [
        nodes_val, volume_val, replicate_val,
        f"{avg_block_time:.2f}" if not pd.isna(avg_block_time) else '',
        f"{std_block_time:.2f}" if not pd.isna(std_block_time) else '',
        f"{throughput_tx_s:.2f}" if not pd.isna(throughput_tx_s) else '',
        f"{peak_mempool:.0f}" if not pd.isna(peak_mempool) else '',
        f"{final_mempool:.0f}" if not pd.isna(final_mempool) else '',
        f"{total_cpu_seconds:.2f}" if not pd.isna(total_cpu_seconds) else '',
        f"{peak_memory_percent:.1f}%" if not pd.isna(peak_memory_percent) else ''
    ]

    # --- Write to CSV ---
    file_exists = os.path.isfile(output_csv_path)
    try:
        with open(output_csv_path, 'a', newline='') as csvfile: # Open in append mode ('a')
            writer = csv.writer(csvfile)
            if not file_exists:
                writer.writerow(header) # Write header only if file is new
            writer.writerow(data_row) # Append the data row
        print(f"Successfully appended data to {output_csv_path}")
    except Exception as e:
        print(f"Error writing to output CSV file {output_csv_path}: {e}")

    # --- Print to Console (Optional but useful) ---
    print(",".join(header))
    print(",".join(map(str, data_row))) # Convert all elements to string for printing



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze blockchain metrics CSV.")
    parser.add_argument("csv_file", help="Path to the blockchain_data.csv file")
    # Arguments for metadata not present in the CSV
    parser.add_argument("-n", "--nodes", type=int, required=True, help="Number of nodes in this run")
    parser.add_argument("-v", "--volume", type=str, required=True, help="Transaction volume description (e.g., '10tps')")
    parser.add_argument("-r", "--replicate", type=int, required=True, help="Replicate number for this run")

    args = parser.parse_args()

    analyze_metrics(args.csv_file, args.nodes, args.volume, args.replicate)