# 教程

## 场景 1：s5cmd sync 报 429 SlowDown

**输入**：
```
s5cmd sync s3://my-bucket/data/ /local/backup/
ERROR SlowDown (429) for objects bigfile1.dat, bigfile2.dat...
```

**诊断**：

```bash
storageops --print 's5cmd sync 报 429 SlowDown 错误，帮我诊断'
```

**输出示例**：

```
根因: s5cmd 默认并发 256 过高，触发服务端前缀限流
建议: --numworkers 16 --retry-count 10
```

## 场景 2：rclone 报 corrupted on transfer

**输入**：
```
rclone copy s3:bucket/ /local/
ERROR corrupted on transfer: md5 hash mismatch
```

**诊断**：

```bash
storageops --print @rclone-debug.log 'rclone corrupted on transfer，分析原因'
```

**输出示例**：

```
根因: 分块上传中断/网络不稳定导致的校验和不匹配
建议: --checkers 1 --transfers 1 --retries 10
```

## 场景 3：BOS 报 SignatureDoesNotMatch

**输入**：
```
<Error>
  <Code>SignatureDoesNotMatch</Code>
  <Message>The request signature we calculated does not match</Message>
</Error>
```

**诊断**：

```bash
storageops --print 'BOS AccessDenied: SignatureDoesNotMatch 错误，帮我分析'
```

**输出示例**：

```
根因: 客户端时钟偏差或 AK/SK 不匹配
建议: ntpdate 同步时钟；检查 endpoint 和 region
```

## 场景 4：交互式排查

```bash
storageops
```

进入交互模式，可以多轮对话深入排查：

```
你: rclone 挂载 OSS 很慢
Ai: 请提供更多信息：并发参数？对象数量？文件大小分布？
你: --transfers 4，大概 10 万个小文件
Ai: 小文件过多。建议：--transfers 16 --checkers 32，并考虑先 tar 再传...
```

## 场景 5：输出诊断报告

```bash
storageops --print \
  '分析附件中的日志，输出完整的诊断报告' \
  @error.log > diagnosis.md
```

输出格式化的诊断报告，可直接发给客户或归档。
