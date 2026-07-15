import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db import init_db
from src.services.datasets import scan_datasets

if __name__ == "__main__":
    init_db()
    print(scan_datasets())
