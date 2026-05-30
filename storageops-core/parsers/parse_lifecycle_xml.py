"""
Parse S3 Lifecycle Configuration XML into structured rule list.

Extracts transition rules, expiration rules, abort incomplete multipart rules,
and their filters (prefix, tags, days).

Usage:
    cat lifecycle.xml | python -m storageops-core.parsers.parse_lifecycle_xml
    python -m storageops-core.parsers.parse_lifecycle_xml lifecycle.xml
"""
import re
import sys
import json
from pathlib import Path


def parse(text: str) -> dict:
    """Parse lifecycle XML configuration."""
    rules = []
    warnings = []

    # Split into <Rule> blocks
    rule_blocks = re.findall(
        r'<Rule>.*?</Rule>', text, re.DOTALL | re.IGNORECASE
    )

    for block in rule_blocks:
        rule = {}

        # ID
        id_m = re.search(r'<ID>([^<]+)</ID>', block)
        rule['id'] = id_m.group(1) if id_m else 'unnamed'

        # Status
        status_m = re.search(r'<Status>(\w+)</Status>', block)
        rule['enabled'] = (status_m.group(1).lower() == 'enabled') if status_m else False

        # Filter — prefix
        prefix_m = re.search(r'<Prefix>([^<]*)</Prefix>', block)
        rule['filter_prefix'] = prefix_m.group(1) if prefix_m else ''

        # Filter — tags
        tag_matches = re.findall(
            r'<Tag>\s*<Key>([^<]+)</Key>\s*<Value>([^<]+)</Value>\s*</Tag>',
            block, re.DOTALL
        )
        rule['filter_tags'] = {k: v for k, v in tag_matches} if tag_matches else {}

        # Transitions
        transitions = []
        for tm in re.finditer(
            r'<Transition>(.*?)</Transition>', block, re.DOTALL | re.IGNORECASE
        ):
            t_block = tm.group(1)
            days_m = re.search(r'<Days>(\d+)</Days>', t_block)
            date_m = re.search(r'<Date>([^<]+)</Date>', t_block)
            class_m = re.search(r'<StorageClass>(\w+)</StorageClass>', t_block)

            t = {}
            if days_m:
                t['days'] = int(days_m.group(1))
            if date_m:
                t['date'] = date_m.group(1)
            if class_m:
                t['storage_class'] = class_m.group(1)
            if t:
                transitions.append(t)
        rule['transitions'] = transitions

        # Noncurrent version transitions
        ncv_transitions = []
        for ntm in re.finditer(
            r'<NoncurrentVersionTransition>(.*?)</NoncurrentVersionTransition>',
            block, re.DOTALL | re.IGNORECASE
        ):
            nt_block = ntm.group(1)
            ndays_m = re.search(r'<NoncurrentDays>(\d+)</NoncurrentDays>', nt_block)
            nver_m = re.search(r'<NewerNoncurrentVersions>(\d+)</NewerNoncurrentVersions>', nt_block)
            class_m = re.search(r'<StorageClass>(\w+)</StorageClass>', nt_block)
            nt = {}
            if ndays_m:
                nt['noncurrent_days'] = int(ndays_m.group(1))
            if nver_m:
                nt['newer_noncurrent_versions'] = int(nver_m.group(1))
            if class_m:
                nt['storage_class'] = class_m.group(1)
            if nt:
                ncv_transitions.append(nt)
        rule['noncurrent_version_transitions'] = ncv_transitions

        # Expiration
        exp_match = re.search(r'<Expiration>(.*?)</Expiration>', block, re.DOTALL)
        if exp_match:
            exp_block = exp_match.group(1)
            days_m = re.search(r'<Days>(\d+)</Days>', exp_block)
            date_m = re.search(r'<Date>([^<]+)</Date>', exp_block)
            marker_m = re.search(
                r'<ExpiredObjectDeleteMarker>(\w+)</ExpiredObjectDeleteMarker>', exp_block
            )
            rule['expiration'] = {}
            if days_m:
                rule['expiration']['days'] = int(days_m.group(1))
            if date_m:
                rule['expiration']['date'] = date_m.group(1)
            if marker_m:
                rule['expiration']['expired_object_delete_marker'] = \
                    marker_m.group(1).lower() == 'true'

        # Noncurrent version expiration
        nce_match = re.search(
            r'<NoncurrentVersionExpiration>(.*?)</NoncurrentVersionExpiration>',
            block, re.DOTALL
        )
        if nce_match:
            nce_block = nce_match.group(1)
            ndays_m = re.search(r'<NoncurrentDays>(\d+)</NoncurrentDays>', nce_block)
            nver_m = re.search(r'<NewerNoncurrentVersions>(\d+)</NewerNoncurrentVersions>', nce_block)
            rule['noncurrent_version_expiration'] = {}
            if ndays_m:
                rule['noncurrent_version_expiration']['noncurrent_days'] = int(ndays_m.group(1))
            if nver_m:
                rule['noncurrent_version_expiration']['newer_noncurrent_versions'] = int(nver_m.group(1))

        # Abort incomplete multipart upload
        abort_match = re.search(
            r'<AbortIncompleteMultipartUpload>(.*?)</AbortIncompleteMultipartUpload>',
            block, re.DOTALL
        )
        if abort_match:
            abort_block = abort_match.group(1)
            days_m = re.search(r'<DaysAfterInitiation>(\d+)</DaysAfterInitiation>', abort_block)
            if days_m:
                rule['abort_incomplete_multipart'] = {
                    'days_after_initiation': int(days_m.group(1)),
                }

        rules.append(rule)

    # Analysis
    enabled_rules = [r for r in rules if r['enabled']]
    disabled_rules = [r for r in rules if not r['enabled']]

    # Check for overlapping prefixes
    prefixes = [r['filter_prefix'] for r in rules if r['filter_prefix']]
    overlapping = len(prefixes) != len(set(prefixes))

    # Warnings
    if overlapping:
        warnings.append("Multiple rules target the same prefix. Shorter-period rules take precedence.")

    for r in rules:
        # Check for IA transition without small object filter
        for t in r.get('transitions', []):
            if t.get('storage_class', '').upper() == 'STANDARD_IA':
                warnings.append(
                    f"Rule '{r['id']}' transitions to STANDARD_IA without a size filter. "
                    "Objects < 128KB will be billed at 128KB minimum. "
                    "Add a filter to exclude small objects."
                )
                break

        # Check for missing abort incomplete multipart
        if not r.get('abort_incomplete_multipart') and r.get('filter_prefix'):
            pass  # Not always needed — only warn if multipart uploads are used

    return {
        "rules": rules,
        "summary": {
            "total_rules": len(rules),
            "enabled_rules": len(enabled_rules),
            "disabled_rules": len(disabled_rules),
            "overlapping_prefixes": overlapping,
        },
        "transitions_summary": [
            {
                "rule_id": r['id'],
                "prefix": r['filter_prefix'],
                "from_class": "STANDARD",
                "to_classes": [t.get('storage_class', '') for t in r.get('transitions', [])],
                "transition_days": [t.get('days') for t in r.get('transitions', []) if 'days' in t],
                "expiration_days": r.get('expiration', {}).get('days'),
            }
            for r in enabled_rules
        ],
        "warnings": warnings,
    }


def main():
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        text = path.read_text(encoding='utf-8', errors='replace')
    else:
        text = sys.stdin.read()

    result = parse(text)
    result["ok"] = True
    result["module"] = "parse_lifecycle_xml"
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
