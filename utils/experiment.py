from datetime import datetime
from pathlib import Path
from typing import Dict, List

import csv


CSV_FIELDS = [
    "timestamp",
    "experiment_name",
    "cwmin_exp",
    "cwmax_exp",
    "cwmin_real",
    "cwmax_real",
    "station_mac",
    "rx_packets",
    "rx_bytes",
    "rx_drop_misc",
    "tx_packets",
    "tx_bytes",
    "tx_retries",
    "tx_failed",
    "signal",
    "signal_avg",
    "tx_bitrate",
    "expected_throughput",
    "delta_rx_packets",
    "delta_rx_bytes",
    "delta_rx_drop_misc",
    "delta_tx_packets",
    "delta_tx_bytes",
    "delta_tx_retries",
    "delta_tx_failed",
    "rx_throughput_mbps",
    "tx_throughput_mbps",
    "expected_throughput_mbps",
    "tx_bitrate_mbps",
    "rx_drop_rate",
    "tx_retry_rate",
    "tx_failed_rate",
    "notes",
]


def default_experiment_name() -> str:
    return datetime.now().strftime("exp_%Y%m%d_%H%M%S")


def ensure_experiment_dir(base_dir: str, experiment_name: str) -> Path:
    p = Path(base_dir) / experiment_name
    p.mkdir(parents=True, exist_ok=True)
    return p


def append_station_rows(csv_path: Path, rows: List[Dict]) -> None:
    need_header = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if need_header:
            writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, None) for k in CSV_FIELDS})
