"""
Analyze timing data to compute throughput efficiency and identify bottlenecks.

Takes timing breakdown (DNS, TCP, TLS, TTFB, Transfer) and object sizes,
compares observed throughput to theoretical maximum.

Usage:
    python -m storageops-core.analyzers.analyze_throughput timing.json
"""
import json
import sys
from pathlib import Path


def analyze(data: dict) -> dict:
    """Analyze throughput from parsed timing data."""
    # Extract inputs
    object_size_mb = data.get('object_size_mb', 0)
    object_count = data.get('object_count', 1)
    rtt_ms = data.get('rtt_ms', 0)
    bandwidth_mbps = data.get('bandwidth_mbps', 0)
    observed_mbps = data.get('observed_throughput_mbps', 0)
    timing = data.get('timing', {})

    total_size_mb = object_size_mb * object_count

    # Theoretical max
    theoretical_mbps = bandwidth_mbps if bandwidth_mbps > 0 else None

    # Efficiency
    efficiency = observed_mbps / theoretical_mbps if theoretical_mbps and observed_mbps else None

    # Bandwidth-delay product
    bdp_mb = (bandwidth_mbps * rtt_ms / 1000) / 8 if bandwidth_mbps and rtt_ms else None

    # Layer analysis
    layers = {}
    if timing:
        timing_total = timing.get('total_seconds', 0) or sum(timing.values())
        for layer, seconds in timing.items():
            if layer == 'total_seconds':
                continue
            layers[layer] = {
                "seconds": seconds,
                "percent": round(seconds / timing_total * 100, 1) if timing_total else 0,
            }

    # Bottleneck identification
    bottleneck = "unknown"
    if efficiency is not None:
        if efficiency < 0.3:
            bottleneck = "severe_inefficiency"
        elif efficiency < 0.7:
            bottleneck = "suboptimal_configuration"
        else:
            bottleneck = "within_expected_range"

    # If timing shows one layer dominating
    if layers:
        dominant = max(layers.items(), key=lambda x: x[1]['percent'])
        if dominant[1]['percent'] > 50:
            bottleneck = f"layer_{dominant[0]}_dominant"

    recommendations = []
    if bottleneck == "severe_inefficiency":
        recommendations.append("Check for misconfiguration: wrong endpoint, region, or tool defaults.")
        recommendations.append("Verify no throttling (429 errors) is occurring.")
        recommendations.append("Check client-side bottleneck: disk I/O, CPU, NIC.")
    elif bottleneck == "suboptimal_configuration":
        recommendations.append("Tune concurrency and part size for current RTT and bandwidth.")
        recommendations.append("Consider increasing connection pool size.")
    elif "tls" in bottleneck:
        recommendations.append("Enable TLS session resumption to reduce handshake overhead.")
    elif "dns" in bottleneck:
        recommendations.append("Check DNS caching. Consider local DNS resolver.")

    return {
        "inputs": {
            "total_size_mb": total_size_mb,
            "rtt_ms": rtt_ms,
            "bandwidth_mbps": bandwidth_mbps,
            "object_count": object_count,
        },
        "observed": {
            "throughput_mbps": observed_mbps,
        },
        "theoretical": {
            "max_throughput_mbps": theoretical_mbps,
            "bandwidth_delay_product_mb": bdp_mb,
        },
        "efficiency": {
            "ratio": round(efficiency, 3) if efficiency is not None else None,
            "bottleneck": bottleneck,
        },
        "layer_breakdown": layers,
        "recommendations": recommendations,
    }


def main():
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        data = json.loads(path.read_text())
    else:
        data = json.loads(sys.stdin.read())

    result = analyze(data)
    result["ok"] = True
    result["module"] = "analyze_throughput"
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
