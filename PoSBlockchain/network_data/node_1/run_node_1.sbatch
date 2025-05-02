#!/bin/bash
#SBATCH --job-name=node_1_9001
#SBATCH --output=/dcs/project/algoblock/MainCode/PoSBlockchain/network_data/node_1/logs/slurm_node_1_9001-%j.out
#SBATCH --error=/dcs/project/algoblock/MainCode/PoSBlockchain/network_data/node_1/logs/slurm_node_1_9001-%j.err
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:30:00
#SBATCH --partition=cpu-batch
#SBATCH --chdir=/dcs/project/algoblock/MainCode/PoSBlockchain/network_data/node_1

echo '--- Slurm Job Started ---'
echo 'Hostname: $(hostname)'
echo 'Job ID: $SLURM_JOB_ID'
echo 'Working Directory: $(pwd)'
echo 'Activating Python Environment...'
source /etc/profile.d/modules.sh
source /etc/profile.d/conda.sh
conda activate my_blockchain_env
echo 'Python Path: $(which python)'
echo '--- Starting Node Script ---'
#SBATCH --partition=cpu-batch
python start_node.py

echo '--- Node Script Finished ---'
