"""
代码体量统计脚本
统计项目代码行数分布
"""
import os
from pathlib import Path
from collections import defaultdict
from typing import Dict, Tuple

# 排除的目录
EXCLUDE_DIRS = {'venv', '__pycache__', '.git', 'logs', 'data', 'node_modules', '.pytest_cache'}

# 排除的文件
EXCLUDE_FILES = {'.db', '.session', '.session-journal', '.log'}

# 文件类型映射
FILE_TYPES = {
    '.py': 'Python',
    '.md': 'Markdown',
    '.yaml': 'YAML',
    '.yml': 'YAML',
    '.json': 'JSON',
    '.txt': 'Text',
    '.ps1': 'PowerShell',
    '.bat': 'Batch',
    '.sh': 'Shell',
    '.dockerfile': 'Dockerfile',
    '.yml': 'Docker Compose',
}


def count_lines(file_path: Path) -> int:
    """统计文件行数"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return len(f.readlines())
    except Exception:
        return 0


def should_exclude(path: Path) -> bool:
    """判断是否应该排除该路径"""
    # 检查目录
    for part in path.parts:
        if part in EXCLUDE_DIRS:
            return True
    
    # 检查文件扩展名
    if path.suffix in EXCLUDE_FILES:
        return True
    
    return False


def get_file_type(file_path: Path) -> str:
    """获取文件类型"""
    ext = file_path.suffix.lower()
    if ext == '' and file_path.name.lower() == 'dockerfile':
        return 'Dockerfile'
    return FILE_TYPES.get(ext, 'Other')


def scan_directory(root_dir: Path) -> Tuple[Dict[str, Dict], Dict[str, Dict]]:
    """扫描目录，统计代码行数"""
    by_type = defaultdict(lambda: {'count': 0, 'lines': 0, 'files': []})
    by_module = defaultdict(lambda: {'count': 0, 'lines': 0, 'files': []})
    
    for file_path in root_dir.rglob('*'):
        if not file_path.is_file():
            continue
        
        if should_exclude(file_path):
            continue
        
        # 按文件类型统计
        file_type = get_file_type(file_path)
        lines = count_lines(file_path)
        
        by_type[file_type]['count'] += 1
        by_type[file_type]['lines'] += lines
        by_type[file_type]['files'].append(str(file_path.relative_to(root_dir)))
        
        # 按模块统计（只统计Python文件）
        if file_path.suffix == '.py':
            # 确定模块路径
            rel_path = file_path.relative_to(root_dir)
            parts = rel_path.parts
            
            if len(parts) > 0:
                if parts[0] == 'src':
                    if len(parts) > 1:
                        module = f"src/{parts[1]}"
                    else:
                        module = 'src'
                elif parts[0] == 'scripts':
                    module = 'scripts'
                elif parts[0] in ['main.py', 'relay_main.py']:
                    module = 'root'
                else:
                    module = 'other'
            else:
                module = 'root'
            
            by_module[module]['count'] += 1
            by_module[module]['lines'] += lines
            by_module[module]['files'].append(str(rel_path))
    
    return dict(by_type), dict(by_module)


def print_statistics(by_type: Dict, by_module: Dict, project_root: Path):
    """打印统计结果"""
    import sys
    import io
    
    # 设置输出编码为UTF-8
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    print("=" * 80)
    print("代码体量统计报告")
    print("=" * 80)
    
    # 按文件类型统计
    print("\n【按文件类型统计】")
    print("-" * 80)
    print(f"{'文件类型':<20} {'文件数':<10} {'代码行数':<15} {'占比':<10}")
    print("-" * 80)
    
    total_lines = sum(stats['lines'] for stats in by_type.values())
    total_files = sum(stats['count'] for stats in by_type.values())
    
    # 按行数排序
    sorted_types = sorted(by_type.items(), key=lambda x: x[1]['lines'], reverse=True)
    
    for file_type, stats in sorted_types:
        percentage = (stats['lines'] / total_lines * 100) if total_lines > 0 else 0
        print(f"{file_type:<20} {stats['count']:<10} {stats['lines']:<15} {percentage:>6.2f}%")
    
    print("-" * 80)
    print(f"{'总计':<20} {total_files:<10} {total_lines:<15} {'100.00%':>10}")
    
    # 按模块统计（Python代码）
    print("\n【按模块统计（Python代码）】")
    print("-" * 80)
    print(f"{'模块':<25} {'文件数':<10} {'代码行数':<15} {'占比':<10}")
    print("-" * 80)
    
    python_total_lines = sum(stats['lines'] for stats in by_module.values())
    python_total_files = sum(stats['count'] for stats in by_module.values())
    
    # 按行数排序
    sorted_modules = sorted(by_module.items(), key=lambda x: x[1]['lines'], reverse=True)
    
    for module, stats in sorted_modules:
        percentage = (stats['lines'] / python_total_lines * 100) if python_total_lines > 0 else 0
        print(f"{module:<25} {stats['count']:<10} {stats['lines']:<15} {percentage:>6.2f}%")
    
    print("-" * 80)
    print(f"{'Python总计':<25} {python_total_files:<10} {python_total_lines:<15} {'100.00%':>10}")
    
    # 主要模块详情
    print("\n【主要模块文件列表（Top 10）】")
    print("-" * 80)
    
    # 收集所有Python文件及其行数
    all_python_files = []
    for module, stats in by_module.items():
        for file_path in stats['files']:
            file_full_path = Path(module.replace('src/', 'src/').replace('scripts', 'scripts')) / file_path.split('/', 1)[-1] if '/' in file_path else Path(file_path)
            if file_full_path.exists():
                lines = count_lines(file_full_path)
                all_python_files.append((file_path, lines, module))
    
    # 按行数排序，取前10
    all_python_files.sort(key=lambda x: x[1], reverse=True)
    
    print(f"{'文件路径':<50} {'行数':<10} {'模块':<15}")
    print("-" * 80)
    for file_path, lines, module in all_python_files[:10]:
        print(f"{file_path:<50} {lines:<10} {module:<15}")
    
    # 模块详细文件列表
    print("\n【各模块详细文件列表】")
    print("-" * 80)
    
    for module, stats in sorted_modules:
        if stats['count'] == 0:
            continue
        
        print(f"\n{module} ({stats['count']} 个文件, {stats['lines']} 行):")
        # 获取该模块的文件列表并按行数排序
        module_files = []
        for file_path_str in stats['files']:
            # 构建完整路径
            file_path = project_root / file_path_str
            
            if file_path.exists():
                lines = count_lines(file_path)
                module_files.append((file_path_str, lines))
        
        module_files.sort(key=lambda x: x[1], reverse=True)
        for file_path_str, lines in module_files:
            print(f"  - {file_path_str:<50} {lines:>5} 行")
    
    print("\n" + "=" * 80)


def main():
    """主函数"""
    # 获取项目根目录
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    print(f"扫描目录: {project_root}")
    print("正在统计...\n")
    
    # 扫描目录
    by_type, by_module = scan_directory(project_root)
    
    # 打印统计结果
    print_statistics(by_type, by_module, project_root)


if __name__ == "__main__":
    main()
