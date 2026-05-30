# Lifecycle Configuration

## AWS S3 Lifecycle Rule Structure

```xml
<LifecycleConfiguration>
  <Rule>
    <ID>Rule ID</ID>
    <Filter>
      <Prefix>prefix/</Prefix>
      <!-- OR -->
      <And>
        <Prefix>prefix/</Prefix>
        <Tag><Key>env</Key><Value>prod</Value></Tag>
      </And>
    </Filter>
    <Status>Enabled</Status>
    <Transition>
      <Days>30</Days>
      <StorageClass>STANDARD_IA</StorageClass>
    </Transition>
    <Expiration>
      <Days>365</Days>
      <!-- OR -->
      <ExpiredObjectDeleteMarker>true</ExpiredObjectDeleteMarker>
    </Expiration>
    <NoncurrentVersionTransition>
      <NoncurrentDays>7</NoncurrentDays>
      <StorageClass>STANDARD_IA</StorageClass>
    </NoncurrentVersionTransition>
    <NoncurrentVersionExpiration>
      <NoncurrentDays>90</NoncurrentDays>
    </NoncurrentVersionExpiration>
    <AbortIncompleteMultipartUpload>
      <DaysAfterInitiation>7</DaysAfterInitiation>
    </AbortIncompleteMultipartUpload>
  </Rule>
</LifecycleConfiguration>
```

## Common Lifecycle Issues

### 1. Transition Not Triggering
**Possible causes:**
- Rule status is `Disabled`.
- Filter/Prefix doesn't match the objects.
- Minimum object age not met (Days count from object creation).
- Objects already in target storage class.
- Only one transition per day per object.

### 2. Expiration Not Working
**Possible causes:**
- Rule is `Disabled`.
- Filter mismatch.
- Days haven't elapsed.
- Versioning: noncurrent version expiration needs noncurrent version rules.
- Delete markers persist if no `ExpiredObjectDeleteMarker` rule.

### 3. Overlapping Rules
If two rules apply to the same object:
- Actions are applied independently.
- Shorter period rules take precedence for the same action.
- Conflicting transitions may cause unexpected behavior.

### 4. Large-Scale Transition Cost
- Each object transition generates a PUT request (billable).
- Transitioning 1 billion objects = 1 billion billable requests.
- Stagger transitions to avoid burst request costs.

### 5. Abort Incomplete Multipart Upload
- Orphaned multipart uploads consume storage.
- `AbortIncompleteMultipartUpload` with a reasonable `DaysAfterInitiation` (e.g., 7 days) prevents orphan accumulation.
- Not all S3-compatible providers support this.

## Common Lifecycle Patterns

### Infrequent Access Transition
```xml
<Rule>
  <ID>MoveToIA</ID>
  <Filter><Prefix></Prefix></Filter> <!-- All objects -->
  <Status>Enabled</Status>
  <Transition>
    <Days>30</Days>
    <StorageClass>STANDARD_IA</StorageClass>
  </Transition>
</Rule>
```
Objects untouched for 30 days → Standard-IA.

### Archive Old Data
```xml
<Rule>
  <ID>ArchiveAfter90</ID>
  <Filter><Prefix>logs/</Prefix></Filter>
  <Status>Enabled</Status>
  <Transition>
    <Days>30</Days>
    <StorageClass>STANDARD_IA</StorageClass>
  </Transition>
  <Transition>
    <Days>90</Days>
    <StorageClass>GLACIER</StorageClass>
  </Transition>
</Rule>
```
Logs: 30 days Standard → IA, 90 days → Glacier.

### Clean Up Old Versions
```xml
<Rule>
  <ID>CleanupNoncurrent</ID>
  <Filter><Prefix></Prefix></Filter>
  <Status>Enabled</Status>
  <NoncurrentVersionTransition>
    <NoncurrentDays>7</NoncurrentDays>
    <StorageClass>STANDARD_IA</StorageClass>
  </NoncurrentVersionTransition>
  <NoncurrentVersionExpiration>
    <NoncurrentDays>90</NoncurrentDays>
  </NoncurrentVersionExpiration>
</Rule>
```

## S3-Compatible Provider Differences

Lifecycle configuration format varies:
- **AWS S3:** XML-based, action-oriented.
- **BOS:** Similar structure, some different storage class names.
- **OSS:** XML-based, `oss:LifecycleConfiguration`.
- **COS:** XML-based, similar to AWS S3.
- **MinIO:** Supports lifecycle via XML (AWS compatible).

Check provider documentation for:
- Supported actions (some don't support all transition/expiration types).
- Transition time granularity (some only support days, not date-based).
- Tag-based filtering support.
