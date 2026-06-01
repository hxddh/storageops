# storageops-lifecycle-cost Scripts

Future scripts for this domain (not yet implemented in v0.1):

## Planned Scripts

### `lifecycle_rule_parser.py`
Parse lifecycle XML configuration and extract:
- Transition rules (prefix, days, target class).
- Expiration rules (prefix, days).
- Abort incomplete multipart upload rules.
- Check for overlapping or conflicting rules.
- Check for rules that may cause unexpected cost (e.g., transition to IA with objects < 128KB).

### `storage_class_cost_estimator.py`
Given an inventory CSV and pricing parameters:
- Compute per-class storage cost.
- Estimate minimum billable size penalty for IA classes.
- Compute per-prefix cost breakdown.
- Flag prefixes with disproportionate costs.

### `cost_attribution_report.py`
Given inventory data and optional access logs:
- Produce a prefix-level cost attribution table.
- Identify top-N cost drivers.
- Estimate cost impact of lifecycle changes.
- Generate recommendations.

### `small_object_analyzer.py`
Given inventory data, identify:
- Objects below minimum billable size thresholds.
- Cost multiplier due to minimum billable size.
- Recommendation: aggregate/tar small files or move to Standard.

## Principles

- All analysis is based on offline inventory data.
- Pricing data is input as parameters (not hardcoded) since rates change.
- Cost estimates are labeled as estimates, not actual billing.
- All lifecycle change recommendations require manual review.
