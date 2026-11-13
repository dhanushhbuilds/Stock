#!/bin/sh
# Final training: tree/linear models and LSTM/GRU run in SEPARATE processes (torch deadlocks after the tree
# libraries have run in the same process on macOS), sharing one run id; a third process selects + registers.
set -e
cd "$(dirname "$0")/backend"
for P in swing intraday; do
  RID="$(date +%Y%m%d-%H%M%S)-final-$P"
  .venv/bin/python -m app.engines.ml.cli train --pipeline $P --models logreg,random_forest,xgboost,lightgbm --run-id $RID --no-finalize > ../data/logs/train_${P}_trees.log 2>&1
  AQ_ML_MODE=torch .venv/bin/python -m app.engines.ml.cli train --pipeline $P --models lstm,gru --run-id $RID --no-finalize > ../data/logs/train_${P}_dl.log 2>&1
  .venv/bin/python -m app.engines.ml.cli finalize --pipeline $P --run-id $RID > ../data/logs/train_${P}_finalize.log 2>&1
  echo "$P done: $RID"; grep '"report"' ../data/logs/train_${P}_finalize.log
done
