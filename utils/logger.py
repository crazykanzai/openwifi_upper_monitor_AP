import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List


def setup_logger(name: str = "openwifi_upper_monitor", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


CSV_FIELDS = [
    "timestamp",
    "cwmin_exp",
    "cwmax_exp",
    "sta_mac",
    "tx_packets",
    "tx_retries",
    "tx_failed",
    "delta_tx_packets",
    "delta_tx_retries",
    "delta_tx_failed",
    "retry_rate",
    "failed_rate",
    "throughput_mbps",
    "jitter_ms",
    "loss_percent",
]


def ensure_csv(csv_path: str) -> None:
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()


def append_csv_rows(csv_path: str, rows: List[Dict]) -> None:
    ensure_csv(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        for row in rows:
            normalized = {k: row.get(k, None) for k in CSV_FIELDS}
            if not normalized.get("timestamp"):
                normalized["timestamp"] = datetime.now().isoformat()
            writer.writerow(normalized)
