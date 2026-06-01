# POSIX Semantics vs Object Storage

Object storage (S3) is NOT a POSIX filesystem. Mounting it as one creates
semantic mismatches that tools relying on POSIX semantics will encounter.

## Object Storage Properties

- **Objects are immutable once written.** "Modify" = delete + re-create.
- **No partial updates.** Cannot write to middle of object without full re-upload.
- **No locks.** No POSIX file locking (flock, fcntl).
- **No atomic rename across "directories".** Rename = copy + delete.
- **Eventual consistency (some providers).** Overwrite may not be immediately visible.
- **No hard links, no symlinks (limited support in some mount tools).**
- **No sparse files, no truncate.**
- **Directories are virtual.** Created by convention (zero-byte key ending in `/`).

## POSIX Operations That Fail or Degrade on Object Storage

| POSIX Operation | S3 Translation | Performance | Semantic Issue |
|---|---|---|---|
| `stat()` | HeadObject | ~RTT | High latency |
| `open(O_RDONLY)` | GetObject (range request possibly) | ~RTT | Must fetch object |
| `open(O_WRONLY)` | Start buffering writes | ~RTT on close/fsync | Data not on server until close |
| `open(O_RDWR)` | GetObject + buffer | ~2×RTT | Full object read required |
| `read()` at offset | Range request (possibly cached) | ~RTT if uncached | Seek-heavy reads expensive |
| `write()` at offset | Buffer locally | Fast locally | Entire object re-uploaded on close |
| `rename()` | CopyObject + DeleteObject | ~2×RTT | Not atomic |
| `truncate()` | GetObject + truncate + PutObject | ~2×RTT | Full object transfer |
| `fsync()` | Flush buffer → PutObject | ~RTT | Forces full object upload |
| `link()` | Not supported | N/A | Fails |
| `symlink()` | Object with custom metadata (if supported) | ~RTT | Not universally supported |
| `mmap()` | Not feasible | N/A | Object not in page cache |
| `flock()` / `fcntl()` | Not supported | N/A | Fails or silently no-ops |

## Tools That Expect POSIX Semantics

These tools are NOT designed for object-storage-backed filesystems:

### Git
- Uses rename() for atomic ref updates.
- Heavy stat() for index and working tree comparison.
- Expects fast random reads (pack files).
- `git gc` uses mmap and rename.
- Expects file locking for concurrent operations.

### npm / pip
- Creates thousands of small files.
- Uses rename() for atomic install.
- Expects fast stat for dependency resolution.
- Uses symlinks (npm link, pip -e).

### IDEs (VS Code, IntelliJ, etc.)
- Use file watchers (inotify/FSEvents) — not supported on FUSE.
- Frequent stat() for file change detection.
- Random reads for language server indexing.
- Write temp files, then rename to target.

### Databases (SQLite, LevelDB)
- Require byte-range locking.
- Use mmap for performance.
- Write-ahead logging (WAL) requires atomic rename.
- **Do not store databases on object storage mounts.**

## Mitigation

1. **Metadata caching:** Increase stat cache TTL.
2. **Write cache:** Buffer writes locally, flush async.
3. **Read cache:** Cache recently read objects on local disk.
4. **Avoid random writes:** Use write-to-temp-then-rename pattern.
5. **Accept limitations:** Some POSIX operations will never be fast on object storage.
