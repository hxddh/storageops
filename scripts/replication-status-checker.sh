#!/usr/bin/env bash
# ============================================================================
# StorageOps — 复制状态检查器
# ============================================================================
# 用法: ./scripts/replication-status-checker.sh <source-bucket> <dest-bucket> <key>
#
# 对比 source 和 replica 端对象的状态:
#   - 是否存在
#   - Size 是否一致
#   - ETag 是否一致  
#   - ReplicationStatus
#   - LastModified 差异 (复制延迟)
#
# 前置条件: 凭证已通过 credential-loader.sh 注入环境变量
# ============================================================================

SOURCE_BUCKET="${1:?Usage: $0 <source-bucket> <dest-bucket> <key>}"
DEST_BUCKET="${2:?}"
KEY="${3:?}"

echo "=== 复制状态检查 ==="
echo "Source: s3://$SOURCE_BUCKET/$KEY"
echo "Replica: s3://$DEST_BUCKET/$KEY"
echo ""

# Source object
echo "--- Source Object ---"
aws s3api head-object --bucket "$SOURCE_BUCKET" --key "$KEY" \
  --query '{Size: ContentLength, ETag: ETag, LastModified: LastModified}' \
  --output table 2>/dev/null || echo "  ❌ NOT FOUND or ACCESS DENIED"

echo ""

# Replica object
echo "--- Replica Object ---"
REPLICA_INFO=$(aws s3api head-object --bucket "$DEST_BUCKET" --key "$KEY" \
  --query '{Size: ContentLength, ETag: ETag, LastModified: LastModified, ReplicationStatus: ReplicationStatus}' \
  --output json 2>/dev/null)

if [ -n "$REPLICA_INFO" ]; then
  echo "$REPLICA_INFO" | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(f'  Size:     {data.get(\"Size\", \"N/A\")}')
print(f'  ETag:     {data.get(\"ETag\", \"N/A\")}')
print(f'  Modified: {data.get(\"LastModified\", \"N/A\")}')
print(f'  Status:   {data.get(\"ReplicationStatus\", \"NOT SET\")}')
"
else
  echo "  ❌ NOT FOUND or ACCESS DENIED"
fi

echo ""
echo "--- Version Count ---"
echo "Source:"
aws s3api list-object-versions --bucket "$SOURCE_BUCKET" --prefix "$KEY" --max-items 5 \
  --query 'length(Versions)' --output text 2>/dev/null || echo "N/A"
echo "Replica:"
aws s3api list-object-versions --bucket "$DEST_BUCKET" --prefix "$KEY" --max-items 5 \
  --query 'length(Versions)' --output text 2>/dev/null || echo "N/A"

echo ""
echo "Done. 所有命令均为 read-only。"
