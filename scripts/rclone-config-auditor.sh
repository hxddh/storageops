#!/usr/bin/env bash
# ============================================================================
# StorageOps — rclone 配置审计工具
# ============================================================================
# 用法: ./scripts/rclone-config-auditor.sh [config-file]
# 默认读取 rclone config show 输出或指定的配置文件
#
# 检测常见配置反模式:
#   1. 缺少 region 配置 (SigV4 必需)
#   2. list_version=2 但 provider 不支持
#   3. copy_cutoff 过小导致不必要多次拷贝
#   4. chunk_size 与 max_upload_parts 乘积可能不够大
#   5. disable_checksum 可能隐藏数据损坏
#   6. force_path_style 与 endpoint URL 格式不一致
# ============================================================================

CONFIG="${1:-}"

if [ -z "$CONFIG" ]; then
  # Try to get rclone config
  if command -v rclone &>/dev/null; then
    CONFIG=$(rclone config show 2>/dev/null)
  fi
  if [ -z "$CONFIG" ]; then
    echo "WARNING: No rclone config found. Specify path: $0 <config-file>" >&2
    exit 0
  fi
elif [ -f "$CONFIG" ]; then
  CONFIG=$(cat "$CONFIG")
fi

WARNINGS=0

echo "=== rclone 配置审计报告 ==="
echo ""

# 1. Check region
if ! echo "$CONFIG" | grep -q "^region = "; then
  echo "⚠️  [MISSING] region 未配置 — SigV4 签名必需。"
  echo "   建议: region = your-region"
  WARNINGS=$((WARNINGS + 1))
fi

# 2. Check list_version
if echo "$CONFIG" | grep -q "^list_version = 2$"; then
  provider=$(echo "$CONFIG" | grep "^provider = " | awk '{print $3}')
  case "$provider" in
    Alibaba|OSS|alibaba|oss)
      echo "⚠️  [COMPAT] list_version=2 但 provider=OSS — OSS 可能不支持 V2。"
      echo "   建议: list_version = 1"
      WARNINGS=$((WARNINGS + 1))
      ;;
  esac
fi

# 3. Check copy_cutoff
copy_cutoff=$(echo "$CONFIG" | grep "^copy_cutoff = " | awk '{print $3}')
if [ -n "$copy_cutoff" ]; then
  cutoff_bytes=$(echo "$copy_cutoff" | sed 's/G/*1024*1024*1024/;s/M/*1024*1024/;s/K/*1024/' | bc 2>/dev/null)
  if [ -n "$cutoff_bytes" ] && [ "$cutoff_bytes" -lt 524288000 ] 2>/dev/null; then
    echo "⚠️  [PERF] copy_cutoff < 500MB — 小文件触发 multipart copy 增加请求成本。"
    WARNINGS=$((WARNINGS + 1))
  fi
fi

# 4. Check chunk_size × max_upload_parts
chunk_size=$(echo "$CONFIG" | grep "^chunk_size = " | awk '{print $3}')
max_parts=$(echo "$CONFIG" | grep "^max_upload_parts = " | awk '{print $3}')
max_filesize_gb=$(echo "$chunk_size" | sed 's/M/ * /;s/G/ * 1024 * /;s/K/ * 0.001 * /' | xargs -I{} echo "scale=1; {} * ${max_parts:-10000} / 1024" | bc 2>/dev/null)
if [ -n "$max_filesize_gb" ] && [ "$(echo "$max_filesize_gb < 5000" | bc 2>/dev/null)" = "1" ]; then
  echo "⚠️  [LIMIT] chunk_size × max_upload_parts = ${max_filesize_gb}GB — 无法上传超大文件。"
  echo "   当前: chunk_size=$chunk_size max_upload_parts=${max_parts:-10000}"
  WARNINGS=$((WARNINGS + 1))
fi

# 5. Check disable_checksum
if echo "$CONFIG" | grep -q "^disable_checksum = true$"; then
  echo "⚠️  [INTEGRITY] disable_checksum=true — 禁用校验和可能隐藏数据损坏。"
  WARNINGS=$((WARNINGS + 1))
fi

# 6. Check force_path_style vs endpoint
force=$(echo "$CONFIG" | grep "^force_path_style = " | awk '{print $3}')
endpoint=$(echo "$CONFIG" | grep "^endpoint = " | awk '{print $3}')
if [ "$force" = "false" ] && echo "$endpoint" | grep -qv "\.amazonaws\.com"; then
  echo "⚠️  [CONFIG] force_path_style=false 但 endpoint 非 AWS — 可能需改为 true。"
  WARNINGS=$((WARNINGS + 1))
fi

echo ""
if [ "$WARNINGS" -eq 0 ]; then
  echo "✅ 未检测到常见配置问题。"
else
  echo "📋 共发现 $WARNINGS 个配置建议。"
fi
