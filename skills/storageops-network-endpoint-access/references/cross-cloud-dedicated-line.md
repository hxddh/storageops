# Cross-Cloud and Dedicated Line Access

## Cross-Cloud Scenarios

### Client in Cloud A → Object Storage in Cloud B
```
Cloud A (e.g., Alibaba ECS) → Internet → Cloud B (e.g., AWS S3)
```

**Expected issues:**
- Higher latency (cross-cloud RTT).
- Lower bandwidth (internet best-effort).
- Possible TLS interception or throttling by cloud provider egress.

**Optimization path:**
```
Cloud A → Dedicated Line / Cloud Interconnect → Cloud B → VPC Endpoint → S3
```

### Dedicated Line / Cloud Interconnect
```
阿里云 ← Cloud Enterprise Network (CEN) / 专线 → AWS / 华为云 / 腾讯云
```

**Key considerations:**
- Bandwidth of the interconnect.
- Routing: are S3 endpoint IP prefixes advertised over the interconnect?
- DNS: does DNS resolution within Cloud A return the VPC endpoint IP of Cloud B?

## Diagnostic Approach

### Step 1: Measure Baseline
```bash
# RTT from client to endpoint
ping -c 10 <endpoint-hostname>

# Throughput ceiling
# manual-only: iperf3 -c <test-server> (if available)
```

### Step 2: Determine Actual Route
```bash
# manual-only: traceroute <endpoint-hostname>
# manual-only: mtr -r -c 10 <endpoint-hostname>
```

Analyze the traceroute for:
- Number of hops.
- Where the traffic crosses cloud boundaries.
- Any high-latency hops (congestion points).
- Any AS path changes.

### Step 3: Compare Paths
- Is traffic going over internet or dedicated line?
- Check the source IP of requests arriving at the destination (access logs).
- If source IP is a public IP → going over internet.
- If source IP is private → going over dedicated line/interconnect.

### Step 4: DNS Check
- Does DNS resolution from Cloud A return:
  - Public IP of Cloud B's endpoint? → Internet path.
  - Private IP of Cloud B's VPC endpoint? → Dedicated line path.
  - Internal IP of Cloud B's private endpoint? → Private path.

## Common Cross-Cloud Issues

### 1. Asymmetric Routing
- Request goes over dedicated line, response returns over internet.
- Or request over internet, response over dedicated line.
- Stateful firewalls may drop return traffic.
- **Symptom:** Intermittent connectivity, timeouts.

### 2. Egress Cost
- Some cloud providers charge for egress traffic.
- Cross-cloud traffic may incur egress charges on BOTH sides.
- Dedicated line may reduce egress cost vs internet egress.

### 3. MTU Differences
- Dedicated lines often support jumbo frames (9000 bytes).
- Internet typically 1500 bytes.
- If MTU mismatches between paths, packet fragmentation or "packet too big" errors.

### 4. TLS Inspection
- Some cloud providers inspect outbound TLS traffic.
- May cause certificate errors if inspection is transparent.
- May add latency.

### 5. Rate Limiting by IP
- If all cross-cloud traffic comes from a single source IP (NAT), provider may rate-limit per IP.

## Provider-Specific Cross-Cloud

### Alibaba → AWS S3
```
ECS in 阿里云 → 阿里云公网出口 → Internet → AWS S3 Public Endpoint
# Higher latency, higher egress cost

ECS in 阿里云 → CEN/Express Connect → AWS VPC → S3 VPC Endpoint
# Lower latency, lower egress cost (via interconnect)
```

### Alibaba → Alibaba OSS (different region)
```
ECS in cn-hangzhou → OSS in cn-beijing
# Cross-region, within same cloud
# Use internal endpoint for lower latency
```

## Validation Commands (manual-only)

```bash
# Check route
# manual-only: traceroute -n <endpoint-hostname>

# Check MTU along path
# manual-only: tracepath <endpoint-hostname>

# Test with specific source interface (if multiple paths)
# manual-only: curl --interface <interface> https://<endpoint>
```
