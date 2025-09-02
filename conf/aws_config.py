"""
AWS配置文件 - 实际的AWS连接配置

注意：请根据实际情况修改以下配置
"""

# AWS凭证配置
AWS_CREDENTIALS = {
    # 使用环境变量（推荐方式）
    # 在终端中设置：
    # export AWS_ACCESS_KEY_ID=your_access_key
    # export AWS_SECRET_ACCESS_KEY=your_secret_key
    # export AWS_DEFAULT_REGION=us-east-1
    
    # 或者直接配置（不推荐用于生产环境）
    # 'aws_access_key_id': 'your_access_key_here',
    # 'aws_secret_access_key': 'your_secret_key_here',
    # 'region_name': 'us-east-1',
}

# S3配置
S3_CONFIG = {
    'bucket_name': 'fin-news-raw-yz',  # 从图片看到的存储桶名
    'region': 'us-east-2',             # 根据实际情况调整
    'prefix': 'polygon/',              # 数据源前缀
}

# DynamoDB配置
DYNAMODB_CONFIG = {
    'table_name': 'news_documents',  # ⚠️ A需要提供实际的表名
    'region': 'us-east-2',                     # 根据实际情况调整
}

# 数据获取配置
DATA_FETCH_CONFIG = {
    'max_files_per_batch': 50,        # 每批最大文件数
    'local_storage_dir': 'data/raw_data/aws_batch/',  # 本地存储目录
    'supported_sources': [             # 支持的数据源
        'polygon',
        'yahoo_finance', 
        'reuters',
        'sec_edgar'
    ]
}

# 性能配置
PERFORMANCE_CONFIG = {
    'download_concurrency': 5,        # 并发下载数
    'processing_batch_size': 10,      # 处理批大小
    'max_retries': 3,                 # 最大重试次数
    'retry_delay': 1,                 # 重试延迟（秒）
}

# 日志配置
LOGGING_CONFIG = {
    'level': 'INFO',                  # 日志级别
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'file': 'logs/aws_fetcher.log',   # 日志文件路径
}

# 配置函数
def get_aws_config():
    """获取AWS配置"""
    return {
        'credentials': AWS_CREDENTIALS,
        's3': S3_CONFIG,
        'dynamodb': DYNAMODB_CONFIG,
        'data_fetch': DATA_FETCH_CONFIG,
        'performance': PERFORMANCE_CONFIG,
        'logging': LOGGING_CONFIG
    }

def validate_config():
    """验证配置是否完整"""
    required_fields = [
        'bucket_name' in S3_CONFIG,
        'table_name' in DYNAMODB_CONFIG,
        'region' in S3_CONFIG,
        'region' in DYNAMODB_CONFIG
    ]
    
    if all(required_fields):
        print("✅ AWS配置验证通过")
        return True
    else:
        print("❌ AWS配置验证失败，请检查配置")
        return False

# 快速配置函数
def get_s3_config():
    """获取S3配置"""
    return S3_CONFIG

def get_dynamodb_config():
    """获取DynamoDB配置"""
    return DYNAMODB_CONFIG

def get_data_fetch_config():
    """获取数据获取配置"""
    return DATA_FETCH_CONFIG

if __name__ == "__main__":
    # 测试配置
    print("🔧 AWS配置测试")
    print("=" * 50)
    
    config = get_aws_config()
    for section, settings in config.items():
        print(f"\n📋 {section.upper()}:")
        for key, value in settings.items():
            print(f"   {key}: {value}")
    
    print("\n" + "=" * 50)
    validate_config()
    
    print("\n⚠️  需要A提供的信息:")
    print("   1. DynamoDB表名")
    print("   2. 确认AWS区域")
    print("   3. 访问权限配置") 