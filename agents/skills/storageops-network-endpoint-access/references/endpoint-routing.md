# Endpoint Routing

## Endpoint Types

### Public Endpoint
- Accessible from the public internet.
- DNS resolves to public IP addresses.
- Example: `s3.amazonaws.com`, `oss-cn-hangzhou.aliyuncs.com`.

### VPC Endpoint (AWS Gateway Endpoint for S3)
- Accessible only within the VPC.
- Uses AWS PrivateLink technology.
- Route table entry directs S3 traffic to the VPC endpoint.
- DNS within VPC resolves S3 to private IP.
- **No internet gateway required.**
- Example: `vpce-<id>.s3.<region>.vpce.amazonaws.com`.

### VPC Endpoint (AWS Interface Endpoint / PrivateLink)
- Elastic Network Interface (ENI) in the VPC.
- Used for services other than S3/DynamoDB.
- Private DNS can override public DNS resolution.
- Example: `vpce-<id>.<service>.vpce.<region>.vpce.amazonaws.com`.

### Private Endpoint (Provider-Specific)
- Many S3-compatible providers offer private/internal endpoints.
- Accessible only from within the provider's network (VPC, VCN, etc.).
- May not require TLS for data plane (check provider docs).
- Example: `oss-cn-hangzhou-internal.aliyuncs.com`.

### Dedicated Line / Direct Connect
- Physical or virtual direct connection from on-premises to cloud.
- Traffic does NOT traverse public internet.
- Requires route configuration and BGP.
- Endpoint still accessible via public DNS if routes are correct.

## Routing Diagnostics

### Check Which Path is Used
```bash
# Trace the route
# manual-only: traceroute <endpoint-hostname>

# Check DNS resolution
dig <endpoint-hostname>

# Compare to expected IP range (private vs public)
whois <resolved-ip>
```

### If Private Endpoint Expected But Public Route Used
- DNS may be resolving to public IP.
- Check `/etc/hosts` for overrides.
- Check VPC DNS settings.
- Check if VPC endpoint route table entry exists.

### If Traffic Going Over Internet Instead of Direct Connect
- BGP routes may not be advertising the endpoint IP ranges.
- Check route table on the on-premises router.
- Check Direct Connect virtual interface configuration.

## Endpoint Configuration in Tools

### awscli
```
aws s3 ls --endpoint-url https://s3.example.com
aws s3 ls --endpoint-url https://bucket.s3.example.com  # virtual-hosted
```

### rclone
```
endpoint = https://s3.example.com
# Force path-style:
force_path_style = true
```

### s5cmd
```
s5cmd --endpoint-url https://s3.example.com ls s3://bucket/
```

### boto3
```python
s3 = boto3.client('s3',
    endpoint_url='https://s3.example.com',
    config=Config(s3={'addressing_style': 'path'})
)
```

## Common Routing Issues

1. **DNS resolves wrong IP:** Public when private expected, or vice versa.
2. **VPC endpoint route missing:** Traffic goes to internet gateway instead.
3. **Security group / NACL blocking:** Request reaches endpoint but blocked by SG.
4. **Proxy intercepting:** HTTPS_PROXY causing traffic to route through proxy.
5. **Split DNS:** Different DNS resolution inside vs outside VPC.
