#!/usr/bin/env python3
"""
StorageOps — SigV4 签名错误对比工具

用法: python3 scripts/sigv4-error-diff.py <error-response.xml>

从 SignatureDoesNotMatch 错误响应中提取 StringToSign 和 CanonicalRequest，
与客户端期望值对比，定位差异来源。

当前版本: v0.1 — 解析 XML 中的签名信息，输出结构化对比报告。
"""

import xml.etree.ElementTree as ET
import sys

def parse_sigv4_error(xml_content: str) -> dict:
    """Parse SignatureDoesNotMatch XML response."""
    root = ET.fromstring(xml_content)
    
    # Extract namespace
    ns = ''
    if '}' in root.tag:
        ns = root.tag.split('}')[0] + '}'
    
    result = {}
    
    code = root.find(f'{ns}Code')
    message = root.find(f'{ns}Message')
    string_to_sign = root.find(f'{ns}StringToSign')
    canonical_request = root.find(f'{ns}CanonicalRequest')
    string_to_sign_bytes = root.find(f'{ns}StringToSignBytes')
    request_id = root.find(f'{ns}RequestId')
    host_id = root.find(f'{ns}HostId')
    
    result['error_code'] = code.text if code is not None else 'UNKNOWN'
    result['message'] = message.text[:120] if message is not None else 'N/A'
    result['string_to_sign'] = string_to_sign.text.strip() if string_to_sign is not None else None
    result['canonical_request'] = canonical_request.text.strip() if canonical_request is not None else None
    result['string_to_sign_bytes'] = string_to_sign_bytes.text.strip() if string_to_sign_bytes is not None else None
    result['request_id'] = request_id.text if request_id is not None else 'N/A'
    result['host_id'] = host_id.text if host_id is not None else 'N/A'
    
    return result

def analyze_string_to_sign(sts: str) -> dict:
    """Break down StringToSign into components."""
    lines = sts.split('\n')
    analysis = {}
    
    if len(lines) >= 1:
        analysis['algorithm'] = lines[0]
    if len(lines) >= 2:
        analysis['timestamp'] = lines[1]
    if len(lines) >= 3:
        analysis['scope'] = lines[2]
        # Parse scope: YYYYMMDD/region/service/aws4_request
        parts = lines[2].split('/')
        if len(parts) >= 1:
            analysis['scope_date'] = parts[0]
        if len(parts) >= 2:
            analysis['scope_region'] = parts[1]
        if len(parts) >= 3:
            analysis['scope_service'] = parts[2]
    
    return analysis

def analyze_canonical_request(cr: str) -> dict:
    """Break down CanonicalRequest into components."""
    lines = cr.split('\n')
    analysis = {}
    
    if len(lines) >= 1:
        analysis['http_method'] = lines[0]
    if len(lines) >= 2:
        analysis['canonical_uri'] = lines[1]
    if len(lines) >= 3:
        analysis['canonical_query_string'] = lines[2]
    
    # Find signed headers section (last line before payload hash is signed headers)
    if len(lines) >= 2:
        analysis['payload_hash'] = lines[-1]
        analysis['signed_headers_list'] = lines[-2] if len(lines) >= 2 else None
    
    # Find host header
    for line in lines:
        if line.lower().startswith('host:'):
            analysis['host'] = line.split(':', 1)[1].strip()
            break
    
    return analysis

def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r') as f:
            xml_content = f.read()
    else:
        xml_content = sys.stdin.read()
    
    parsed = parse_sigv4_error(xml_content)
    
    print("=" * 60)
    print("SigV4 SignatureDoesNotMatch — 签名错误分析")
    print("=" * 60)
    print(f"\nError: {parsed['error_code']}")
    print(f"Message: {parsed['message']}")
    print(f"Request ID: {parsed['request_id']}")
    
    if parsed['string_to_sign']:
        sts_analysis = analyze_string_to_sign(parsed['string_to_sign'])
        print("\n--- StringToSign 解析 ---")
        print(f"  Algorithm:  {sts_analysis.get('algorithm', 'N/A')}")
        print(f"  Timestamp:  {sts_analysis.get('timestamp', 'N/A')}")
        print(f"  Region:     {sts_analysis.get('scope_region', 'N/A')}")
        print(f"  Service:    {sts_analysis.get('scope_service', 'N/A')}")
        print(f"  Date:       {sts_analysis.get('scope_date', 'N/A')}")
    
    if parsed['canonical_request']:
        cr_analysis = analyze_canonical_request(parsed['canonical_request'])
        print("\n--- CanonicalRequest 解析 ---")
        print(f"  Method:     {cr_analysis.get('http_method', 'N/A')}")
        print(f"  URI:        {cr_analysis.get('canonical_uri', 'N/A')}")
        print(f"  Query:      {cr_analysis.get('canonical_query_string', 'N/A')}")
        print(f"  Host:       {cr_analysis.get('host', 'N/A')}")
        print(f"  Payload:    {cr_analysis.get('payload_hash', 'N/A')}")
    
    # Diagnostic hints
    print("\n--- 诊断提示 ---")
    
    if parsed['string_to_sign']:
        sts = parsed['string_to_sign']
        cr = parsed['canonical_request'] or ''
        
        # Check clock skew
        import datetime
        timestamp_str = sts.split('\n')[1] if '\n' in sts else ''
        if timestamp_str:
            try:
                ts = datetime.datetime.strptime(timestamp_str[:8], '%Y%m%d')
                now = datetime.datetime.utcnow()
                diff_hours = abs((now - ts).total_seconds()) / 3600
                if diff_hours > 0.25:  # 15 minutes
                    print(f"  ⚠️  请求时间距当前 {diff_hours:.1f} 小时 — 可能是时钟偏移!")
            except Exception:
                pass
        
        # Check UNSIGNED-PAYLOAD consistency
        if 'UNSIGNED-PAYLOAD' in cr:
            print("  💡 使用了 UNSIGNED-PAYLOAD — 确保 x-amz-content-sha256 header 一致")
        
        # Check host header
        if cr_analysis.get('host'):
            print(f"  💡 Host header: {cr_analysis['host']} — 确保 endpoint URL 与此一致")
    
    print("\n--- 需要对比的信息 ---")
    print("  1. Client 使用的 endpoint/region 与 StringToSign 中的一致?")
    print("  2. Client 时钟与服务器时间差 < 15 分钟?")
    print("  3. path-style vs virtual-hosted-style 一致?")
    print("  4. 签名算法 (AWS4-HMAC-SHA256) 被 provider 支持?")
    print("  5. 参考: agents/skills/storageops-s3-protocol-compatibility/references/provider-quirks/")

if __name__ == '__main__':
    main()
