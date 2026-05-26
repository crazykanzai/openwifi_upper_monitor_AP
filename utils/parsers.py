import re
from typing import Dict, List, Optional


STATION_RE = re.compile(r"^Station\s+([0-9a-fA-F:]{17})")
KV_RE = re.compile(r"^\s*([\w\s\-]+):\s*(-?\d+)")


def parse_station_dump(output: str) -> List[Dict]:
    stations = []
    current: Optional[Dict] = None

    for raw_line in output.splitlines():
        line = raw_line.rstrip()
        sta_match = STATION_RE.match(line)
        if sta_match:
            if current:
                stations.append(current)
            current = {
                "sta_mac": sta_match.group(1).lower(),
                "tx_packets": 0,
                "tx_retries": 0,
                "tx_failed": 0,
                "signal": None,
            }
            continue

        if current is None:
            continue

        kv_match = KV_RE.match(line)
        if not kv_match:
            continue

        key = kv_match.group(1).strip().lower().replace(" ", "_")
        val = int(kv_match.group(2))

        if key == "tx_packets":
            current["tx_packets"] = val
        elif key == "tx_retries":
            current["tx_retries"] = val
        elif key == "tx_failed":
            current["tx_failed"] = val
        elif key in ("signal", "signal_avg") and current.get("signal") is None:
            current["signal"] = val

    if current:
        stations.append(current)

    return stations


def compute_deltas_and_rates(current_rows: List[Dict], prev_map: Dict[str, Dict]) -> List[Dict]:
    processed = []
    for row in current_rows:
        mac = row["sta_mac"]
        prev = prev_map.get(mac, {})

        delta_tx_packets = max(0, row.get("tx_packets", 0) - prev.get("tx_packets", 0))
        delta_tx_retries = max(0, row.get("tx_retries", 0) - prev.get("tx_retries", 0))
        delta_tx_failed = max(0, row.get("tx_failed", 0) - prev.get("tx_failed", 0))

        if delta_tx_packets > 0:
            retry_rate = delta_tx_retries / delta_tx_packets
            failed_rate = delta_tx_failed / delta_tx_packets
        else:
            retry_rate = 0.0
            failed_rate = 0.0

        merged = {
            **row,
            "delta_tx_packets": delta_tx_packets,
            "delta_tx_retries": delta_tx_retries,
            "delta_tx_failed": delta_tx_failed,
            "retry_rate": retry_rate,
            "failed_rate": failed_rate,
        }
        processed.append(merged)

    return processed
