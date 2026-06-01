# Private Access (VPC Endpoint, PrivateLink, 专线)

## AWS VPC Endpoint for S3 (Gateway Endpoint)

### Architecture
```
EC2 in VPC → VPC Endpoint (Gateway) → S3
```
No internet gateway. No NAT gateway. No public IP.

### DNS Resolution
Within the VPC, DNS automatically resolves S3 endpoints to the VPC endpoint:
```
s3.<region>.amazonaws.com → VPC endpoint
<bucket>.s3.<region>.amazonaws.com → VPC endpoint
```

### Validation
```bash
# Check if VPC endpoint exists
# manual-only: aws ec2 describe-vpc-endpoints --filters Name=service-name,Values=com.amazonaws.<region>.s3

# Check route table
# manual-only: aws ec2 describe-route-tables --route-table-ids <rtb-id>

# Verify DNS resolution within VPC
dig s3.<region>.amazonaws.com
# Should resolve to VPC endpoint address
```

### Common Issues
- VPC endpoint not created for the region.
- Route table entry missing or incorrect.
- Endpoint policy too restrictive.
- Security group blocking traffic (for interface endpoints; not gateway).

## AWS PrivateLink (Interface Endpoint)

- Used for S3 access from on-premises via Direct Connect.
- Creates an ENI in the VPC with a private IP.
- Private DNS can be enabled to override public DNS.

## Alibaba Cloud VPC Endpoint for OSS

### Internal Endpoint
```
oss-cn-hangzhou-internal.aliyuncs.com  # Only within Alibaba Cloud VPC
oss-cn-hangzhou.aliyuncs.com           # Public internet
```

### Validation
```bash
# Check resolution
dig oss-cn-hangzhou-internal.aliyuncs.com

# Test connectivity from within VPC
curl -I https://oss-cn-hangzhou-internal.aliyuncs.com
```

## Other Provider Private Access

| Provider | Service | Private Endpoint Pattern |
|---|---|---|
| AWS | S3 | `s3.<region>.amazonaws.com` (VPC endpoint) |
| Alibaba | OSS | `oss-<region>-internal.aliyuncs.com` |
| Huawei | OBS | Private DNS or internal endpoint |
| Baidu | BOS | Internal endpoint (consult docs) |
| Tencent | COS | `<bucket>.cos.<region>.myqcloud.com` (internal) |
| MinIO | Self-hosted | Private IP directly |

## Dedicated Line (专线) Configuration

### Common Setup
```
On-premises → 专线 → Cloud VPC → VPC Endpoint/Internal Endpoint → Object Storage
```

### Validation
1. Check physical connectivity of dedicated line.
2. Check BGP status (routes being advertised).
3. Check if object storage endpoint IP prefix is in BGP advertisements.
4. Verify routing within VPC (route tables, VPC endpoint).
5. Test with `traceroute` to confirm path.

## Dedicated Line vs Internet

| | Dedicated Line | Internet |
|---|---|---|
| Latency | Lower, consistent | Higher, variable |
| Bandwidth | Guaranteed | Best effort |
| Security | Private | Public |
| Cost | Higher | Lower (or included) |
| MTU | Typically 1500+ (jumbo possible) | 1500 (often less with tunnels) |

If object storage access should use dedicated line but appears to route over
the internet:
- Check BGP route advertisements.
- Check whether the object storage endpoint's IP range is in the advertised prefixes.
- Some providers do not advertise S3 IP ranges over Direct Connect by default.
