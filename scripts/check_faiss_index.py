#!/usr/bin/env python3
"""
FAISS索引检查脚本 - 检查本地和S3索引状态
"""
import os
import sys
import pickle
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

def check_faiss_index():
    """检查FAISS索引状态"""
    print("🔍 FAISS索引状态检查")
    print("=" * 50)
    
    # 检查本地索引文件
    index_dir = Path("data/faiss_index")
    index_file = index_dir / "faiss.index"
    metadata_file = index_dir / "metadata.pkl"
    
    print(f"📁 本地索引目录: {index_dir}")
    print(f"📄 本地索引文件: {index_file}")
    print(f"📋 本地元数据文件: {metadata_file}")
    print()
    
    # 检查本地文件是否存在
    if index_file.exists() and metadata_file.exists():
        print(f"✅ 本地FAISS索引文件存在")
        print(f"   索引大小: {index_file.stat().st_size / 1024:.1f} KB")
        print(f"   元数据大小: {metadata_file.stat().st_size / 1024:.1f} KB")
        print(f"   修改时间: {index_file.stat().sttime}")
        
        # 尝试加载本地索引
        try:
            from apps.index.faiss_store import FAISSStore
            
            print("🔄 尝试加载本地FAISS索引...")
            store = FAISSStore()
            
            # 获取索引信息
            print(f"✅ 本地索引加载成功!")
            print(f"   向量维度: {store.dimension}")
            print(f"   索引类型: {type(store.index).__name__}")
            
            # 检查索引大小
            if hasattr(store.index, 'ntotal'):
                print(f"   向量数量: {store.index.ntotal}")
            else:
                print(f"   向量数量: 未知")
            
            print()
            
            # 尝试搜索
            print("🔍 测试本地搜索功能...")
            import numpy as np
            
            # 创建一个测试查询向量
            test_query = np.random.rand(1, store.dimension).astype('float32')
            
            # 执行搜索
            distances, indices = store.search(test_query, k=5)
            
            print(f"✅ 本地搜索测试成功!")
            print(f"   查询向量维度: {test_query.shape}")
            print(f"   返回结果数量: {len(indices[0])}")
            print(f"   最近距离: {distances[0][0]:.4f}")
            
        except Exception as e:
            print(f"❌ 本地索引加载失败: {e}")
            
    else:
        print("ℹ️  本地索引文件不存在")
        print("   这是正常的，因为生产系统使用S3存储")
        print()
    
    # 检查S3索引状态
    print("☁️  S3索引状态检查")
    print("-" * 30)
    
    try:
        import boto3
        
        # 检查AWS凭证
        try:
            s3_client = boto3.client('s3', region_name='us-east-2')
            s3_client.head_bucket(Bucket='fin-news-raw-yz')
            print("✅ AWS凭证配置正常")
            print("✅ S3存储桶 'fin-news-raw-yz' 可访问")
            
            # 检查latest.json指针
            try:
                response = s3_client.get_object(Bucket='fin-news-raw-yz', Key='faiss/latest.json')
                latest_info = response['Body'].read().decode('utf-8')
                print(f"✅ 找到S3索引指针: {latest_info[:100]}...")
                
                # 检查索引构建器是否可用
                try:
                    from apps.index.build_index_aws import IndexBuilder
                    print("✅ 生产级索引构建器可用")
                    print("   使用命令: python -m apps.index.build_index_aws --help")
                except ImportError as e:
                    print(f"❌ 索引构建器导入失败: {e}")
                    
            except Exception as e:
                print(f"ℹ️  S3索引指针不存在: {e}")
                print("   可能需要先运行索引构建器")
                
        except Exception as e:
            print(f"❌ AWS访问失败: {e}")
            print("   请检查AWS凭证和权限配置")
            
    except ImportError:
        print("ℹ️  boto3未安装，无法检查S3状态")
        print("   安装命令: pip install boto3")
    
    print()
    print("📋 建议操作:")
    if not (index_file.exists() and metadata_file.exists()):
        print("   1. 如需本地测试，运行: python -m apps.index.build_index_aws --limit 100")
        print("   2. 或直接使用S3索引: python -m apps.service.search_api")
    else:
        print("   1. 本地索引正常，可以用于开发和测试")
        print("   2. 生产环境建议使用S3索引")
    
    print()
    print("🎉 FAISS索引检查完成！")

if __name__ == "__main__":
    check_faiss_index() 