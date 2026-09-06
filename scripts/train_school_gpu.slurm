#!/usr/bin/env bash
#SBATCH --job-name=rhinocoder-lora-v1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=08:00:00
#SBATCH --output=rhinocoder-lora-%j.out

set -euo pipefail

PROJECT_DIR="${SLURM_SUBMIT_DIR:?Submit this job from the RhinoCoder repository root}"
TRAINING_VENV="${RHINOCODER_TRAINING_VENV:?Set RHINOCODER_TRAINING_VENV to the prepared virtual environment}"
MODEL_CACHE="${RHINOCODER_MODEL_CACHE:?Set RHINOCODER_MODEL_CACHE to school-approved storage}"

cd "$PROJECT_DIR"
source "$TRAINING_VENV/bin/activate"
export HF_HOME="$MODEL_CACHE"
export TOKENIZERS_PARALLELISM=false

python tools/run_training.py audit
accelerate launch --num_processes 1 tools/run_training.py train --resume auto
