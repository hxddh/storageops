# Validation: Mixed 403 + Throttling

真实场景：用户同时遇到权限问题和限流，日志混杂。
awscli debug 输出里既有 403 又有 429，还有超时。
