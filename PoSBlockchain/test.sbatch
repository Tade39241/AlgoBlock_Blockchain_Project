#!/bin/bash

# --- Slurm Resource Requests ---
#SBATCH --job-name=blockchain_net  # Name for your job
#SBATCH --partition=cpu-batch     # The partition to use (e.g., cpu-batch)
#SBATCH --nodes=1                 # Run the launcher script on a single node
#SBATCH --ntasks=1                # Run one instance of the launcher script
#SBATCH --account=algoblock
#SBATCH --cpus-per-task=4         # <<< ADJUST: CPUs for launcher + ALL nodes (e.g., 3 nodes + validator + launcher ~ 4-8 CPUs?)
#SBATCH --mem=4G                  # <<< ADJUST: Memory for launcher + ALL nodes (e.g., 4G, 8G?)
#SBATCH --time=01:00:00           # <<< ADJUST: Max runtime (e.g., 1 hour)
#SBATCH --output=logs/network_launcher_%j.out # Log file for stdout (%j = Job ID)
#SBATCH --error=logs/network_launcher_%j.err  # Log file for stderr

# --- Environment Setup ---
echo "--- Slurm Job Started ---"
echo "Job ID: $SLURM_JOB_ID"
echo "Running on node: $(hostname)"
echo "Working directory: $(pwd)" # Should be project root if submitted from there

echo "Setting up environment modules..."
source /etc/profile.d/modules.sh  # Source Kudu environment setups
source /etc/profile.d/conda.sh

echo "Activating Python environment..."
conda activate my_blockchain_env

echo "Python Path: $(which python)"
echo "Python Version: $(python --version)"

# --- Create Logs Directory ---
mkdir -p logs # Ensure the logs directory exists relative to where sbatch runs

# --- Run the Network Launcher ---
echo "--- Starting network_launcher.py ---"

# <<< ADJUST ARGUMENTS AS NEEDED >>>
python network_launcher.py \
    --nodes 3 \
    --sim-volume high \
    # --- DO NOT USE --use-slurm here ---
    # Add other arguments like --base-port if needed

# --- Job Completion ---
echo "--- network_launcher.py finished ---"
echo "--- Slurm Job Ended ---"