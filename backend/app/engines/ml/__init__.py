"""ML engine.

Native-library load order matters on macOS: xgboost, torch and lightgbm each ship/use a different OpenMP runtime
(libomp). Verified 2026-11-13 (exit 139 = segfault):
    lightgbm -> torch  : crash        torch -> lightgbm : ok
    torch -> xgboost   : crash        xgboost -> torch  : ok for tree training, but torch TRAINING then segfaults
So two process modes exist:
    default            : xgboost -> torch -> lightgbm (tree/linear training, inference, API)
    AQ_ML_MODE=torch   : torch only; xgboost/lightgbm are never loaded (LSTM/GRU training)
models.py imports xgboost/lightgbm lazily, so torch-mode processes never load them.
"""

import os

if os.environ.get("AQ_ML_MODE") == "torch":
    import torch  # noqa: F401
else:
    import xgboost  # noqa: F401  (1st)
    import torch  # noqa: F401  (2nd)
    import lightgbm  # noqa: F401  (3rd)
