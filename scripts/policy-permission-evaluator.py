#!/usr/bin/env python3
"""
StorageOps — IAM/Bucket Policy 权限评估模拟器

用法: python3 scripts/policy-permission-evaluator.py <policy.json> <action> <resource>

模拟 AWS IAM policy evaluation logic:
  Explicit Deny → 无论 Allow 如何都是 DENY
  Allow → 允许
  无匹配 Allow → 隐式 Deny

当前版本: v0.1 — 简化版, 不处理 condition keys 和 NotAction/NotResource
"""

import json
import sys

def evaluate_policy(policy: dict, action: str, resource: str) -> dict:
    """Evaluate a single IAM or bucket policy against an action/resource."""
    statements = policy.get('Statement', [])
    if isinstance(statements, dict):
        statements = [statements]
    
    result = {
        'action': action,
        'resource': resource,
        'explicit_deny': [],
        'explicit_allow': [],
        'verdict': 'IMPLICIT_DENY',
        'explanation': ''
    }
    
    for i, stmt in enumerate(statements):
        effect = stmt.get('Effect', 'Unknown')
        actions = stmt.get('Action', [])
        resources = stmt.get('Resource', [])
        condition = stmt.get('Condition', {})
        
        if isinstance(actions, str):
            actions = [actions]
        if isinstance(resources, str):
            resources = [resources]
        
        # Check action match
        action_match = any(
            a == action or 
            a.endswith('*') and action.startswith(a[:-1]) or
            a == 's3:*'
            for a in actions
        )
        
        # Check resource match (simplified)
        resource_match = any(
            r == resource or
            r.endswith('*') and resource.startswith(r[:-1]) or
            r == '*'
            for r in resources
        )
        
        if action_match and resource_match:
            sid = stmt.get('Sid', f'Statement-{i+1}')
            if effect == 'Deny':
                result['explicit_deny'].append(sid)
            elif effect == 'Allow':
                result['explicit_allow'].append(sid)
    
    # AWS evaluation: Explicit Deny wins
    if result['explicit_deny']:
        result['verdict'] = 'EXPLICIT_DENY'
        result['explanation'] = f"Explicit Deny found in: {', '.join(result['explicit_deny'])}"
    elif result['explicit_allow']:
        result['verdict'] = 'ALLOW'
        result['explanation'] = f"Allowed by: {', '.join(result['explicit_allow'])}"
    else:
        result['verdict'] = 'IMPLICIT_DENY'
        result['explanation'] = 'No matching Allow statement found — default is Deny.'
    
    return result

def main():
    if len(sys.argv) < 4:
        print("Usage: python3 policy-permission-evaluator.py <policy.json> <action> <resource>")
        print("Example: python3 policy-permission-evaluator.py bucket-policy.json s3:GetObject arn:aws:s3:::my-bucket/*")
        sys.exit(1)
    
    with open(sys.argv[1], 'r') as f:
        policy = json.load(f)
    
    action = sys.argv[2]
    resource = sys.argv[3]
    
    result = evaluate_policy(policy, action, resource)
    
    print("=" * 60)
    print("IAM/Bucket Policy — 权限评估")
    print("=" * 60)
    print(f"\nAction:    {result['action']}")
    print(f"Resource:  {result['resource']}")
    print(f"\n--- 评估结果 ---")
    print(f"Verdict:   {result['verdict']}")
    print(f"Reason:    {result['explanation']}")
    
    if result['explicit_allow']:
        print(f"Allow by:  {', '.join(result['explicit_allow'])}")
    if result['explicit_deny']:
        print(f"Deny by:   {', '.join(result['explicit_deny'])}")
    
    # Cross-account check
    policy_json = json.dumps(policy)
    if '"Principal"' in policy_json:
        principal_val = json.dumps(policy.get('Statement', [{}])[0].get('Principal', {}))
        if '*' in principal_val:
            print(f"\n⚠️  SECURITY: Principal 包含 \"*\" — 检查是否为公开访问风险!")
    
    print("")
    print("NOTE: 本工具仅做基本评估，不处理:")
    print("  - Condition keys (SourceIP, SourceVPC, etc.)")
    print("  - NotAction / NotResource")
    print("  - Organizational SCP")
    print("  - ACL 和 Block Public Access 设置")
    print("  - KMS Key Policy")
    print("  完整评估请使用 IAM Policy Simulator 或参考 skill workflow。")

if __name__ == '__main__':
    main()
