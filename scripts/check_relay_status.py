"""检查中继服务状态"""
import os
import sys
from datetime import datetime
from pathlib import Path

# 设置输出编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

log_file = Path("logs/relay.log")

print("=" * 60)
print("中继服务状态检查")
print("=" * 60)
print()

if log_file.exists():
    mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
    print(f"日志文件最后修改时间: {mtime}")
    print()
    
    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    
    print(f"日志总行数: {len(lines)}")
    print()
    print("最后15行日志:")
    print("-" * 60)
    print(''.join(lines[-15:]))
    print("-" * 60)
else:
    print("❌ 日志文件不存在")

print()
print("当前配置:")
print(f"  API ID: {os.getenv('TELEGRAM_API_ID', '未设置')}")
print(f"  手机号: {os.getenv('TELEGRAM_PHONE_NUMBER', '未设置')}")
print(f"  群组ID: {os.getenv('RELAY_SOURCE_CHAT_ID', '未设置')}")
