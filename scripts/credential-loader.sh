#!/usr/bin/env bash
# ============================================================================
# StorageOps — 通用凭证加载助手
# ============================================================================
# 用法: source scripts/credential-loader.sh [provider] [profile]
#
# 支持 provider: boss (默认), aws, oss
# profile 默认: default
#
# 按优先级把 AK/SK/SESSION_TOKEN 注入当前 shell 环境,
# 供 DuckDB credential_chain(CHAIN 'env')、awscli、rclone 等工具读取。
#
# 设计目标: Agent 永远不需要、也无从在命令行写明文密钥。
# 本脚本不回显、不写文件、不入 shell history。
#
# 优先级树:
#   1. 环境变量已有 (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY)
#   2. ~/.aws/credentials [profile] (awk 解析)
#   3. 对应 provider 的配置文件 (~/.bce/credentials, ~/.ossutilconfig)
#   4. 交互 read -s 输入
#
# ============================================================================
# 安全红线:
#   - 绝不在命令行/SQL 中出现明文 AK/SK
#   - 绝不以任何方式读取/查看凭证文件内容 (cat/head/tail/grep/read 工具)
#   - 正确做法: source 本脚本, 内部用 VAR=$(awk ...) 捕获, 永不打印
# ============================================================================

_provider="${1:-bos}"
_profile="${2:-default}"

# --- 1) 环境变量已有 ---
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-${BOS_ACCESS_KEY:-}}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-${BOS_SECRET_KEY:-}}"

# --- 2) ~/.aws/credentials ---
if [ -z "$AWS_ACCESS_KEY_ID" ] && [ -f "$HOME/.aws/credentials" ]; then
  AWS_ACCESS_KEY_ID=$(awk -v p="[$_profile]" '$0==p{f=1;next}/^\[/{f=0}f&&/aws_access_key_id/{print $3;exit}' "$HOME/.aws/credentials")
  AWS_SECRET_ACCESS_KEY=$(awk -v p="[$_profile]" '$0==p{f=1;next}/^\[/{f=0}f&&/aws_secret_access_key/{print $3;exit}' "$HOME/.aws/credentials")
  _tok=$(awk -v p="[$_profile]" '$0==p{f=1;next}/^\[/{f=0}f&&/aws_session_token/{print $3;exit}' "$HOME/.aws/credentials")
  [ -n "$_tok" ] && export AWS_SESSION_TOKEN="$_tok"
  export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
fi

# --- 3) Provider-specific ---
case "$_provider" in
  bos)
    if [ -z "$AWS_ACCESS_KEY_ID" ] && [ -f "$HOME/.bce/credentials" ]; then
      AWS_ACCESS_KEY_ID=$(awk -F'[=:]' '/^[[:space:]]*ak[[:space:]]*[=:]/{gsub(/[[:space:]"]/,"",$2);print $2;exit}' "$HOME/.bce/credentials")
      AWS_SECRET_ACCESS_KEY=$(awk -F'[=:]' '/^[[:space:]]*sk[[:space:]]*[=:]/{gsub(/[[:space:]"]/,"",$2);print $2;exit}' "$HOME/.bce/credentials")
      export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
    fi
    ;;
  oss)
    if [ -z "$AWS_ACCESS_KEY_ID" ] && [ -f "$HOME/.ossutilconfig" ]; then
      AWS_ACCESS_KEY_ID=$(awk -F'[=:]' '/^[[:space:]]*accessKeyID[[:space:]]*[=:]/{gsub(/[[:space:]"]/,"",$2);print $2;exit}' "$HOME/.ossutilconfig")
      AWS_SECRET_ACCESS_KEY=$(awk -F'[=:]' '/^[[:space:]]*accessKeySecret[[:space:]]*[=:]/{gsub(/[[:space:]"]/,"",$2);print $2;exit}' "$HOME/.ossutilconfig")
      export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
    fi
    ;;
esac

# --- 4) 交互输入 (不回显，不入 history) ---
if [ -z "$AWS_ACCESS_KEY_ID" ]; then
  read -rs -p "Storage AK: " AWS_ACCESS_KEY_ID; echo
  read -rs -p "Storage SK: " AWS_SECRET_ACCESS_KEY; echo
  export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
fi

# --- 校验 ---
if [ -n "$AWS_ACCESS_KEY_ID" ] && [ -n "$AWS_SECRET_ACCESS_KEY" ]; then
  echo "凭证已就绪 (AK 长度 ${#AWS_ACCESS_KEY_ID}${AWS_SESSION_TOKEN:+, 含 SESSION_TOKEN})"
else
  echo "错误: 未获取到存储凭证，无法继续。" >&2
fi

unset _provider _profile _tok
