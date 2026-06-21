# Summary
Category: performance_throughput
Route: storageops-performance-diagnosis
Confidence: 0.82
Root Cause Type: high_rtt_wan_latency
Evidence Quality: sufficient
Primary Diagnosis: root_cause_type=high_rtt_wan_latency, affected_layer=network

Throughput is limited by cross-region WAN latency, not the service. A single-stream
transfer over a high-RTT link is bandwidth-delay-product bound, so each connection
caps out far below the available link.

# Key Evidence
- RTT to the endpoint is high (cross-region), and observed single-stream throughput
  in MiB/s is far below the link capacity.
- Throughput scales with the number of parallel streams, the signature of a
  TCP-window / latency limit rather than a server throttle.

# Remediation
- Use parallel/concurrent transfers (many streams) and multipart uploads so
  aggregate throughput overcomes the per-connection bandwidth-delay-product limit.
- Co-locate the client in the bucket region, or use an in-region relay, to cut RTT.
