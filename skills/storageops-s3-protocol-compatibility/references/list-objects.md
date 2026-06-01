# ListObjects V1 vs V2

S3 provides two ListObjects APIs with different pagination and behavior.

## ListObjects (V1)

**Endpoint:** `GET /?prefix=&delimiter=&marker=&max-keys=`

**Pagination:**
- Uses `Marker` and `NextMarker`.
- The response `IsTruncated=true` means more results exist.
- Pass `NextMarker` as `marker` in the next request.
- No `ContinuationToken`.

**Response structure:**
```xml
<ListBucketResult>
  <Name>bucket</Name>
  <Prefix>prefix/</Prefix>
  <Marker>last-key</Marker>
  <NextMarker>next-key-after-last</NextMarker>
  <MaxKeys>1000</MaxKeys>
  <IsTruncated>true</IsTruncated>
  <Contents>...</Contents>
  <CommonPrefixes>
    <Prefix>prefix/subdir/</Prefix>
  </CommonPrefixes>
</ListBucketResult>
```

**Known provider differences:**
- Some providers cap MaxKeys lower than 1000.
- Some providers do not support delimiter filtering correctly.
- Marker behavior with deleted objects varies.

## ListObjectsV2

**Endpoint:** `GET /?list-type=2&prefix=&delimiter=&start-after=&continuation-token=&max-keys=`

**Pagination:**
- Uses `ContinuationToken` and `NextContinuationToken`.
- `StartAfter` replaces the V1 `Marker` for initial offset.
- Pass `NextContinuationToken` as `continuation-token` in the next request.
- `IsTruncated=true` means more results exist.

**Response structure:**
```xml
<ListBucketResult>
  <Name>bucket</Name>
  <Prefix>prefix/</Prefix>
  <StartAfter>key-after</StartAfter>
  <MaxKeys>1000</MaxKeys>
  <IsTruncated>true</IsTruncated>
  <NextContinuationToken>token-string</NextContinuationToken>
  <KeyCount>42</KeyCount>
  <Contents>...</Contents>
  <CommonPrefixes>
    <Prefix>prefix/subdir/</Prefix>
  </CommonPrefixes>
</ListBucketResult>
```

## Common Issues

### Missing Objects in Listing
- Objects uploaded during listing may or may not appear (eventual consistency on some providers).
- Deleted objects may still appear briefly.
- Delimiter filtering excludes objects beneath CommonPrefixes.

### Incorrect CommonPrefixes
- Delimiter-based rollup: all keys sharing a common prefix up to the delimiter are grouped.
- Some providers miscalculate CommonPrefixes, especially with Unicode or special characters.

### Pagination Token Fog
- V1 NextMarker may be empty even when IsTruncated (provider bug).
- V2 NextContinuationToken may change format or encoding between providers.
- Some providers always set IsTruncated=false and return all results (ignoring MaxKeys).

### MaxKeys Behavior
- AWS S3 returns up to 1000 keys per page.
- Some providers return fewer or more than requested.
- Setting MaxKeys=0 behavior varies.

## Debugging Checklist

1. Determine V1 or V2 from request (`list-type=2` query param).
2. Verify the pagination mechanism (Marker vs ContinuationToken).
3. Check KeyCount (V2 only) — does it match the actual number of Contents?
4. Verify IsTruncated — does the provider correctly truncate at MaxKeys?
5. Test with delimiter to verify CommonPrefixes correctness.
