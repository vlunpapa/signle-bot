"""检查信号Bot日志"""
import sys
from pathlib import Path

# 设置输出编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

log_file = Path("logs/bot.log")

print("=" * 60)
print("信号Bot日志检查")
print("=" * 60)
print()

if log_file.exists():
    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    
    print(f"日志总行数: {len(lines)}")
    print()
    print("最后30行日志:")
    print("-" * 60)
    print(''.join(lines[-30:]))
    print("-" * 60)
    
    # 检查关键信息
    token_detected = [line for line in lines if '检测到Token' in line]
    strategy_executed = [line for line in lines if '执行策略' in line or '策略分析' in line]
    
    print()
    print("关键信息统计:")
    print(f"  - Token检测次数: {len(token_detected)}")
    print(f"  - 策略执行次数: {len(strategy_executed)}")
    
    if token_detected:
        print()
        print("最近的Token检测:")
        for line in token_detected[-5:]:
            print(f"  {line.strip()}")
else:
    print("❌ 日志文件不存在")
