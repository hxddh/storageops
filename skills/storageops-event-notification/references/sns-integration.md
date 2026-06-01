# SNS Integration

## When to read
Use when SNS topics do not publish object events or subscriptions do not receive them.

## Checks
- Topic policy allows publish from the bucket service principal.
- Subscription confirmation and filter policies are valid.
- KMS topic encryption allows the service principal.
- Region/account constraints match provider requirements.
