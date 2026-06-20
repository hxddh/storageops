# Object Profile

- Prefix: data/
- Average object size: ~5 MB (well above any minimum billable size, so the
  small-object multiplier is not the issue here).
- Object count: ~2,000,000
- Typical object age at deletion: 60 days (governed by the Expiration rule).

# User Report

Our storage bill for the data/ prefix is higher than expected even though we
delete everything after 60 days and use GLACIER to keep it cheap. We move objects
to GLACIER at 30 days and delete them at 60 days. Why is GLACIER not saving us
what we assumed?
