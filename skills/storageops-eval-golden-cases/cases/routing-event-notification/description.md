# Case: Routing Event Notification

## Scenario
Objects upload successfully, but Lambda is not invoked.

## What It Tests
- Routes missing bucket event delivery to event notification.
- Separates notification config from general write success.

## Expected Diagnosis
Route to `storageops-event-notification`.

## Difficulty
easy

## Domains Tested
- event_notification
