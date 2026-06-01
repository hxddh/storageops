# Case: Event Notification Prefix Filter

## Scenario
Object uploads succeed, but SQS events do not arrive because the notification prefix does not match the keys.

## What It Tests
- Event notification filter matching and destination policy diagnosis.
- Avoids blaming the upload path when object writes succeeded.

## Expected Diagnosis
Identify a prefix filter mismatch and recommend updating or adding a matching notification rule.

## Difficulty
easy

## Domains Tested
- event_notification
