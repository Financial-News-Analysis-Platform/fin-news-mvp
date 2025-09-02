# 增量索引构建 - Incremental Index Build

## 📋 概述

增量索引构建功能允许我们扩展现有的FAISS索引，而无需重新构建整个索引。这对于处理新文档和保持索引最新状态非常有用。

## 🎯 功能特性

### 核心功能
- **智能时间戳检测**: 自动从现有chunks元数据中确定`since_ts`
- **增量文档获取**: 只获取比现有索引更新的文档
- **无缝合并**: 将新文档与现有索引合并
- **版本化管理**: 创建新的版本化索引文件
- **原子更新**: 通过`latest.json`指针实现原子切换

### 性能优化
- **候选过滤**: 使用时间窗口限制DynamoDB扫描成本
- **分页处理**: 支持大量文档的分页处理
- **内存效率**: 流式处理，避免内存溢出
- **并行嵌入**: 批量嵌入新文档

## 🚀 使用方法

### 基本用法

```bash
# 增量构建（推荐）
python scripts/build_index_incremental.py --limit 1000

# 干运行模式（查看会添加什么）
python scripts/build_index_incremental.py --dry-run true --limit 100

# 带时间窗口限制（控制成本）
python scripts/build_index_incremental.py --window-days 7 --limit 500
```

### 命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--dry-run` | `false` | 干运行模式，不实际创建索引 |
| `--limit` | `2000` | 最大处理的新文档数量 |
| `--region` | `us-east-2` | AWS区域 |
| `--bucket` | `fin-news-raw-yz` | S3存储桶名称 |
| `--table` | `news_documents` | DynamoDB表名 |
| `--prefix` | `polygon/` | S3前缀 |
| `--window-days` | `None` | 时间窗口天数（限制扫描成本） |
| `--min-body-chars` | `400` | 最小正文长度 |

### 使用示例

#### 1. 日常增量更新
```bash
# 处理最近的新文档
python scripts/build_index_incremental.py --limit 500 --window-days 3
```

#### 2. 大批量更新
```bash
# 处理大量新文档
python scripts/build_index_incremental.py --limit 5000
```

#### 3. 测试和验证
```bash
# 干运行查看会添加什么
python scripts/build_index_incremental.py --dry-run true --limit 100

# 运行测试套件
python scripts/test_incremental_build.py
```

## 🔧 技术实现

### 工作流程

1. **获取当前版本**
   - 下载`latest.json`指针
   - 获取当前manifest信息
   - 确定现有索引状态

2. **确定时间戳**
   - 从现有chunks元数据中提取时间戳
   - 选择`published_utc`和`fetched_at`的最大值
   - 作为`since_ts`用于过滤新文档

3. **获取新文档**
   - 扫描DynamoDB表
   - 过滤条件：`published_utc > since_ts OR fetched_at > since_ts`
   - 支持时间窗口限制

4. **处理新文档**
   - 正文选择：优先使用`body`字段，否则从S3获取
   - 正文清理：使用`clean_body()`函数
   - 文本分块：使用`TextChunker`（360/460/40/200参数）
   - 文本嵌入：使用`TextEmbedder`（MiniLM，normalize=True）

5. **合并索引**
   - 加载现有embeddings矩阵
   - 追加新embeddings
   - 合并chunks元数据
   - 重新分配row_index

6. **构建新索引**
   - 创建新的`IndexFlatIP`
   - 添加所有embeddings
   - 验证索引完整性

7. **版本化管理**
   - 生成新版本号（YYYYMMDD_HHMMSS格式）
   - 写入版本化文件到本地
   - 上传到S3
   - 更新`latest.json`指针

### 数据结构

#### 输入数据（DynamoDB）
```json
{
  "doc_id": "string",
  "title": "string", 
  "body": "string",
  "source": "polygon",
  "published_utc": "2025-08-21T10:00:00Z",
  "fetched_at": "2025-08-21T10:05:00Z",
  "tickers": ["NVDA", "AAPL"],
  "url": "https://example.com/news",
  "s3_key": "polygon/news_123.txt"
}
```

#### 输出数据（S3）
```
s3://fin-news-raw-yz/faiss/{version}/
├── index.faiss          # FAISS索引文件
├── chunks.parquet       # 元数据（Parquet格式）
├── chunks.csv           # 元数据（CSV格式，fallback）
├── embeddings.npy       # 嵌入矩阵
└── manifest.json        # 清单文件
```

#### 清单文件格式
```json
{
  "version": "20250901_230211",
  "created_at_utc": "2025-09-01T23:02:11Z",
  "bucket": "fin-news-raw-yz",
  "region": "us-east-2",
  "index_key": "faiss/20250901_230211/index.faiss",
  "chunks_key": "faiss/20250901_230211/chunks.parquet",
  "emb_key": "faiss/20250901_230211/embeddings.npy",
  "ntotal": 527,
  "dim": 384
}
```

## 📊 性能特征

### 处理速度
- **文档扫描**: ~100-500 docs/s（取决于过滤条件）
- **文本分块**: ~50-100 docs/s
- **文本嵌入**: ~20-50 chunks/s
- **索引构建**: ~1000-5000 vectors/s
- **S3上传**: ~10-50 MB/s

### 资源使用
- **内存**: 线性增长，取决于新文档数量
- **CPU**: 主要消耗在嵌入和索引构建
- **网络**: S3上传/下载，DynamoDB扫描

### 典型性能
```
处理1000个新文档:
- 扫描时间: 10-30秒
- 处理时间: 30-60秒  
- 嵌入时间: 20-50秒
- 索引构建: 5-10秒
- 上传时间: 10-30秒
- 总时间: 75-180秒
```

## 🛠️ 错误处理

### 常见错误及解决方案

#### 1. DynamoDB扫描错误
```
Error: Parameter validation failed
Solution: 检查表名和区域配置
```

#### 2. S3下载失败
```
Error: Failed to download latest.json
Solution: 检查S3权限和文件存在性
```

#### 3. 嵌入失败
```
Error: TextEmbedder initialization failed
Solution: 检查模型下载和依赖安装
```

#### 4. 索引构建失败
```
Error: FAISS index creation failed
Solution: 检查embeddings矩阵维度和数据类型
```

### 恢复策略
- **部分失败**: 脚本会记录错误并继续处理
- **完全失败**: 现有索引保持不变，可以重试
- **数据不一致**: 使用`latest.json`回滚到之前版本

## 🔍 监控和调试

### 日志输出
```
INFO:__main__:Current version: 20250828_002747
INFO:__main__:Current index: 511 vectors, 384 dimensions
INFO:__main__:Found since timestamp: 2025-08-26T01:14:00Z
INFO:__main__:Scanned 10 items, found 10 new documents
INFO:__main__:Processed 10 documents into 26 chunks
INFO:__main__:Embedded 26 chunks in 1.24s (21.0 chunks/s)
INFO:__main__:Merged embeddings: (537, 384)
INFO:__main__:Built new index: 537 vectors, 384 dimensions
```

### 统计信息
```
INCREMENTAL BUILD COMPLETED SUCCESSFULLY
Version: 20250901_230211
Old total: 511
New added: 16
New total: 527
Total time: 3.52s
```

### 调试技巧
1. **使用dry-run模式**: 查看会处理哪些文档
2. **限制文档数量**: 使用`--limit`参数进行小规模测试
3. **检查日志**: 关注错误和警告信息
4. **验证结果**: 使用`check_faiss_index.py`验证索引状态

## 🔄 与现有系统的集成

### 搜索服务自动更新
- 搜索服务启动时自动加载最新索引
- 无需手动重启服务
- 支持热更新

### 版本管理
- 每个增量构建创建新版本
- 保留历史版本用于回滚
- 通过`latest.json`实现原子切换

### 监控集成
- 可以集成到CI/CD流水线
- 支持定时任务调度
- 提供详细的执行报告

## 🚀 最佳实践

### 1. 定期增量更新
```bash
# 每日增量更新
0 2 * * * python scripts/build_index_incremental.py --limit 1000 --window-days 1
```

### 2. 成本控制
```bash
# 使用时间窗口限制扫描成本
python scripts/build_index_incremental.py --window-days 7 --limit 500
```

### 3. 测试和验证
```bash
# 先进行干运行
python scripts/build_index_incremental.py --dry-run true --limit 100

# 然后执行实际构建
python scripts/build_index_incremental.py --limit 100
```

### 4. 监控和告警
- 监控构建时间和成功率
- 设置失败告警
- 跟踪索引大小增长

## 📈 未来改进

### 计划功能
1. **增量删除**: 支持删除过时文档
2. **并行处理**: 多进程并行处理文档
3. **智能调度**: 基于文档数量自动调整参数
4. **压缩优化**: 压缩历史版本节省存储
5. **实时更新**: 支持实时文档流处理

### 性能优化
1. **缓存机制**: 缓存常用数据减少重复计算
2. **批量优化**: 优化批量操作性能
3. **内存管理**: 改进内存使用效率
4. **网络优化**: 优化S3传输性能

---

*最后更新: 2025-01-28 - 增量构建功能实现完成*
