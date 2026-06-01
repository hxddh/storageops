#!/usr/bin/env python3
"""
StorageOps — 元数据放大估算器

用法: python3 scripts/metadata-amplification-estimator.py <operation> <rtt_ms>

估算对象存储 mount 场景下 stat/open/readdir 操作的元数据放大效应。
基于操作类型和 RTT 估算延迟。

当前版本: v0.1
"""

import sys

# Estimated stat/open/readdir call counts for common operations
OPERATION_STATS = {
    'git-status':     {'stat': 10000, 'open': 500, 'readdir': 200, 'desc': 'Git status on moderate repo'},
    'git-clone':      {'stat': 5000,  'open': 2000, 'readdir': 500, 'desc': 'Git clone large repo'},
    'npm-install':    {'stat': 50000, 'open': 20000, 'readdir': 10000, 'desc': 'npm install with many deps'},
    'pip-install':    {'stat': 20000, 'open': 10000, 'readdir': 5000, 'desc': 'pip install in venv'},
    'ls-la':          {'stat': 1000,  'open': 100, 'readdir': 10, 'desc': 'ls -la on directory with 1000 files'},
    'find':           {'stat': 50000, 'open': 5000, 'readdir': 1000, 'desc': 'find across large tree'},
    'ide-startup':    {'stat': 30000, 'open': 5000, 'readdir': 2000, 'desc': 'IDE/workspace startup scan'},
}

# Mapping to S3 API calls
API_MAPPING = {
    'stat':    {'api': 'HeadObject',     'overhead_ms': 5},
    'open':    {'api': 'GetObject',      'overhead_ms': 10},
    'readdir': {'api': 'ListObjectsV2',  'overhead_ms': 20},
}

def estimate(operation: str, rtt_ms: float):
    """Estimate latency for the given operation on object storage mount."""
    stats = OPERATION_STATS.get(operation)
    if not stats:
        print(f"Unknown operation: {operation}")
        print(f"Known: {list(OPERATION_STATS.keys())}")
        sys.exit(1)
    
    print("=" * 60)
    print(f"元数据放大估算: {operation}")
    print(f"场景: {stats['desc']}")
    print(f"RTT: {rtt_ms}ms")
    print("=" * 60)
    
    total_latency = 0
    print(f"\n{'系统调用':<10} {'次数':<10} {'S3 API':<20} {'单次延迟':<12} {'总延迟':<12}")
    print("-" * 65)
    
    for syscall, count in stats.items():
        if syscall == 'desc':
            continue
        api_info = API_MAPPING[syscall]
        per_op = rtt_ms + api_info['overhead_ms']
        subtotal = count * per_op
        total_latency += subtotal
        
        print(f"{syscall:<10} {count:<10,} {api_info['api']:<20} {per_op:.0f}ms{'':<8} {subtotal/1000:,.0f}s")
    
    print("-" * 65)
    print(f"{'TOTAL':>10} {'':>10} {'':>20} {'':>12} {total_latency/1000:,.0f}s ({total_latency/60000:,.1f}min)")
    
    # Local SSD comparison
    local_time = sum(v * 0.0001 for k, v in stats.items() if k != 'desc')  # ~0.1μs per syscall on SSD
    print("\n--- 对比 ---")
    print(f"  Object Storage Mount: {total_latency/1000:,.0f}s ({total_latency/60000:,.1f}min)")
    print(f"  Local SSD:            {local_time:.3f}s")
    print(f"  放大倍数:             {total_latency/1000/local_time:,.0f}x")
    print("")
    print("--- 建议 ---")
    
    if total_latency > 60000:  # > 1 minute
        print("  ❌ 不适合在 object storage mount 上运行此操作 (>1min)")
        print("  建议: 在本地 SSD 上执行后 snapshot 到对象存储")
    elif total_latency > 10000:
        print("  ⚠️  延迟较高 (>10s), 考虑调优 stat cache TTL")
    else:
        print("  ✅ 延迟可接受 (<10s)")
    
    print("")
    print(f"  推荐 stat cache TTL: {max(1, int(rtt_ms / 10))}s (至少可以节省 stat 调用的重复网络往返)")

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python3 metadata-amplification-estimator.py <operation> <rtt_ms>")
        print(f"Operations: {list(OPERATION_STATS.keys())}")
        print("Example: python3 metadata-amplification-estimator.py git-status 50")
        sys.exit(1)
    
    operation = sys.argv[1]
    rtt_ms = float(sys.argv[2])
    estimate(operation, rtt_ms)
