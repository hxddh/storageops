# Summary
Category: network_endpoint_access
Route: storageops-network-endpoint-access
Confidence: 0.80
Root Cause Type: vpc_endpoint_route_missing
Evidence Quality: sufficient
Primary Diagnosis: root_cause_type=vpc_endpoint_route_missing, affected_layer=routing

From a private subnet the S3 endpoint resolves to a public address with no route, so
the request never reaches the service — a VPC endpoint / route-table gap.

# Key Evidence
- DNS resolves the endpoint to a public S3 address (e.g. 52.216.x.x; PrivateDnsEnabled off), but the private subnet has no
  route to it (no NAT and no gateway VPC endpoint).
- Adding the gateway VPC endpoint changes the effective route for the prefix.

# Remediation
- Create/attach the S3 gateway VPC endpoint and add its prefix-list entry to the
  subnet route table; verify the route, then re-test.
