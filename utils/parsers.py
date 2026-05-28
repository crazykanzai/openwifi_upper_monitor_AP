import re
from typing import Dict, List, Optional


STATION_RE = re.compile(r"^Station\s+([0-9a-fA-F:]{17})")
KV_NUM_RE = re.compile(r"^\s*([\w\s\-]+):\s*(-?\d+)")
TX_BITRATE_RE = re.compile(r"^\s*tx bitrate:\s*(.+)$", re.IGNORECASE)
EXPECTED_TP_RE = re.compile(r"^\s*expected throughput:\s*(.+)$", re.IGNORECASE)


def parse_station_dump(output: str) -> List[Dict]:
    stations: List[Dict] = []
    current: Optional[Dict] = None

    for raw_line in output.splitlines():
        line = raw_line.rstrip()
        sta_match = STATION_RE.match(line)
        if sta_match:
            if current:
                stations.append(current)
            current = {
                "station_mac": sta_match.group(1).lower(),
                "rx_packets": 0,
                "rx_bytes": 0,
                "rx_drop_misc": 0,
                "tx_packets": 0,
                "tx_bytes": 0,
                "tx_retries": 0,
                "tx_failed": 0,
                "signal": None,
                "signal_avg": None,
                "tx_bitrate": "",
                "expected_throughput": "",
                "connected_time": 0,
            }
            continue

        if current is None:
            continue

        m_tx = TX_BITRATE_RE.match(line)
        if m_tx:
            current["tx_bitrate"] = m_tx.group(1).strip()
            continue

        m_tp = EXPECTED_TP_RE.match(line)
        if m_tp:
            current["expected_throughput"] = m_tp.group(1).strip()
            continue

        kv = KV_NUM_RE.match(line)
        if not kv:
            continue

        key = kv.group(1).strip().lower().replace(" ", "_")
        val = int(kv.group(2))

        if key in current:
            current[key] = val

    if current:
        stations.append(current)

    return stations


def compute_station_deltas(current_rows: List[Dict], prev_map: Dict[str, Dict]) -> List[Dict]:
    results = []
    for row in current_rows:
        mac = row["station_mac"]
        prev = prev_map.get(mac, {})

        delta_rx_packets = max(0, row.get("rx_packets", 0) - prev.get("rx_packets", 0))
        delta_rx_drop_misc = max(0, row.get("rx_drop_misc", 0) - prev.get("rx_drop_misc", 0))
        delta_tx_packets = max(0, row.get("tx_packets", 0) - prev.get("tx_packets", 0))
        delta_tx_retries = max(0, row.get("tx_retries", 0) - prev.get("tx_retries", 0))
        delta_tx_failed = max(0, row.get("tx_failed", 0) - prev.get("tx_failed", 0))

        rx_den = delta_rx_packets + delta_rx_drop_misc
        tx_retry_den = delta_tx_packets
        tx_failed_den = delta_tx_packets + delta_tx_failed

        rx_drop_rate = (delta_rx_drop_misc / rx_den) if rx_den > 0 else 0.0
        tx_retry_rate = (delta_tx_retries / tx_retry_den) if tx_retry_den > 0 else 0.0
        tx_failed_rate = (delta_tx_failed / tx_failed_den) if tx_failed_den > 0 else 0.0

        results.append(
            {
                **row,
                "delta_rx_packets": delta_rx_packets,
                "delta_rx_drop_misc": delta_rx_drop_misc,
                "delta_tx_packets": delta_tx_packets,
                "delta_tx_retries": delta_tx_retries,
                "delta_tx_failed": delta_tx_failed,
                "rx_drop_rate": rx_drop_rate,
                "tx_retry_rate": tx_retry_rate,
                "tx_failed_rate": tx_failed_rate,
            }
        )

    return results
