import requests
# import psutil # No longer needed if using API metrics
import csv
import time
import argparse
from datetime import datetime

def collect(node_urls, output_file, interval=5):
    """
    Collects metrics from specified node APIs, writing to a CSV file.

    Args:
        node_urls (list[str]): List of base URLs for the node /stats APIs.
        output_file (str): Path to the output CSV file.
        interval (int): Collection interval in seconds.
    """
    print(f"Starting metrics collection. URLs: {node_urls}")
    print(f"Writing data to: {output_file}")
    print(f"Collection interval: {interval} seconds")

    # Prepare CSV header (Adjust based on metrics you want from /stats)
    header = [
        'timestamp', 'node_index', 'api_url',
        'height', 'mempool_size', 'total_transactions', 'last_block_timestamp',
        'api_cpu_percent', 'api_memory_percent', 'api_disk_percent', 'node_port',
        'avg_block_time_s', 'estimated_tps'
    ]
    try:
        with open(output_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(header)

        # Main collection loop
        while True:
            timestamp = datetime.now().isoformat()
            rows_to_write = []

            for i, url in enumerate(node_urls):
                node_index = i
                stats_data = {} # To store data from /stats
                perf_data = {} # Optionally store data from /performance

                # --- Get data from /stats ---
                try:
                    stats_url = f"{url}/stats"
                    response = requests.get(stats_url, timeout=5)
                    response.raise_for_status() # Raise HTTPError for bad responses
                    stats_data = response.json()
                except requests.exceptions.RequestException as e:
                    print(f"Warning: Failed to get /stats from {url}: {e}")
                except Exception as e:
                     print(f"Warning: Error processing /stats from {url}: {e}")

                # --- Optionally get data from /performance ---
                try:
                    perf_url = f"{url}/performance"
                    response = requests.get(perf_url, timeout=5)
                    response.raise_for_status()
                    perf_data = response.json()
                except requests.exceptions.RequestException as e:
                    print(f"Warning: Failed to get /performance from {url}: {e}")
                except Exception as e:
                     print(f"Warning: Error processing /performance from {url}: {e}")


                # Extract data safely using .get() with defaults
                row = [
                    timestamp, node_index, url,
                    stats_data.get('blockchain_height'),
                    stats_data.get('mempool_size'),
                    stats_data.get('total_transactions'),
                    stats_data.get('last_block_timestamp'),
                    stats_data.get('cpu_percent'),
                    stats_data.get('memory_percent'),
                    stats_data.get('disk_percent'),
                    stats_data.get('node_port'),
                    perf_data.get('average_block_time'),
                    perf_data.get('estimated_tps'),
                    # Add values from perf_data if collected, e.g., perf_data.get('average_block_time')
                ]
                rows_to_write.append(row)

            # Write collected data for this interval
            with open(output_file, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerows(rows_to_write)

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\nStopping metrics collection.")
    except Exception as e:
        print(f"\nAn error occurred: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Blockchain Metrics Collector")
    # Removed --pids as we rely on API now
    parser.add_argument('--urls', type=str, nargs='+', required=True, help='List of node API base URLs (e.g., http://localhost:5001)')
    parser.add_argument('--output', type=str, required=True, help='Output CSV file path')
    parser.add_argument('--interval', type=int, default=5, help='Collection interval in seconds')

    args = parser.parse_args()
    # Pass only urls, output, interval
    collect(args.urls, args.output, args.interval)