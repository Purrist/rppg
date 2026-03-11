#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件转换脚本：递归将 .py 和 .vue 文件批量转换为 .md 文件
作者：Qingyan Agent

使用方法：
1. 将此脚本放到目标文件夹
2. 运行脚本：python convert.py
3. 转换后的 .md 文件将保存在 convert-时间戳 文件夹中

排除文件：
在 EXCLUDE_FILES 列表中添加要排除的文件路径（相对于脚本所在目录）
"""

import os
from datetime import datetime
from pathlib import Path


# ============================================================
# 配置区域
# ============================================================

# 脚本自身的文件名（用于排除）
SCRIPT_NAME = "convert.py"

# 要排除的文件列表（相对路径，相对于脚本所在目录）
# 示例：排除特定文件
EXCLUDE_FILES = [
    # "subdir/example.py",      # 排除子目录中的文件
    # "test.vue",               # 排除根目录下的文件
    # "utils/helper.py",        # 排除多层子目录中的文件
]

# ============================================================
EXCLUDE_DIRS = [
    "node_modules",           # 排除 node_modules 文件夹
    "__pycache__",            # 排除 Python 缓存文件夹
    ".git",                   # 排除 git 文件夹
    ".venv",                  # 排除虚拟环境
    "venv",                   # 排除虚拟环境
]


def get_file_language(file_extension: str) -> str:
    """根据文件扩展名获取语言标识"""
    language_map = {
        '.py': 'python',
        '.vue': 'vue',
        '.js': 'javascript',
        '.ts': 'typescript',
        '.html': 'html',
        '.css': 'css',
        '.json': 'json',
    }
    return language_map.get(file_extension.lower(), 'text')


def convert_file_to_md(source_file: Path, source_root: Path, output_dir: Path) -> bool:
    """
    将单个文件转换为 Markdown 格式
    
    Args:
        source_file: 源文件路径
        source_root: 源根目录路径
        output_dir: 输出目录路径
    
    Returns:
        转换是否成功
    """
    try:
        # 读取源文件内容
        with open(source_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 获取文件信息
        file_name = source_file.name
        file_extension = source_file.suffix
        language = get_file_language(file_extension)
        
        # 获取相对路径（用于显示和输出目录结构）
        relative_path = source_file.relative_to(source_root)
        
        # 构建 Markdown 内容
        md_content = f"""# {file_name}

> 源文件路径: `{relative_path}`

---

## 源代码

```{language}
{content}
```

---

*转换时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
        
        # 在输出目录中保持原有的目录结构
        # 例如：subdir/test.py -> output_dir/subdir/test.md
        relative_parent = relative_path.parent
        if relative_parent != Path('.'):
            output_subdir = output_dir / relative_parent
            output_subdir.mkdir(parents=True, exist_ok=True)
        else:
            output_subdir = output_dir
        
        # 生成输出文件名
        md_file_name = source_file.stem + '.md'
        output_file = output_subdir / md_file_name
        
        # 写入 Markdown 文件
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        print(f"[OK] {relative_path} -> {relative_parent / md_file_name}")
        return True
        
    except Exception as e:
        print(f"[FAIL] 转换失败: {source_file.name}, 错误: {e}")
        return False


def should_exclude(file_path: Path, source_root: Path) -> bool:
    """
    检查文件是否应该被排除
    
    Args:
        file_path: 文件路径
        source_root: 源根目录
    
    Returns:
        是否应该排除
    """
    # 排除脚本自身
    if file_path.name == SCRIPT_NAME:
        return True
    
    # 检查是否在排除列表中
    try:
        relative_path = file_path.relative_to(source_root)
        relative_path_str = str(relative_path).replace('\\', '/')  # 统一使用正斜杠
        
        for exclude_path in EXCLUDE_FILES:
            # 统一路径格式进行比较
            exclude_path_normalized = exclude_path.replace('\\', '/')
            if relative_path_str == exclude_path_normalized:
                return True
    except ValueError:
        pass
    
    return False


def batch_convert_recursive(source_dir: str, output_base_dir: str = None) -> dict:
    """
    递归批量转换文件
    
    Args:
        source_dir: 源目录路径
        output_base_dir: 输出基础目录（可选）
    
    Returns:
        转换统计信息
    """
    source_path = Path(source_dir)
    
    # 检查源目录是否存在
    if not source_path.exists():
        print(f"错误: 源目录不存在 - {source_dir}")
        return {'success': 0, 'failed': 0, 'total': 0, 'skipped': 0}
    
    # 创建输出目录（带时间戳）
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir_name = f"convert-{timestamp}"
    
    if output_base_dir:
        output_dir = Path(output_base_dir) / output_dir_name
    else:
        output_dir = source_path / output_dir_name
    
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n输出目录: {output_dir}\n")
    
    # 支持的文件扩展名
    supported_extensions = {'.py', '.vue'}
    
    # 统计信息
    stats = {'success': 0, 'failed': 0, 'total': 0, 'skipped': 0}
    
    # 遍历源目录（递归）
    print("=" * 60)
    print("开始批量转换（递归扫描子目录）...")
    print("=" * 60)
    
    for file_path in source_path.rglob('*'):
        # 检查是否为文件且扩展名匹配
        if file_path.is_file() and file_path.suffix.lower() in supported_extensions:
            # 检查是否应该排除
            if should_exclude(file_path, source_path):
                relative_path = file_path.relative_to(source_path)
                print(f"[SKIP] 排除: {relative_path}")
                stats['skipped'] += 1
                continue
            
            stats['total'] += 1
            if convert_file_to_md(file_path, source_path, output_dir):
                stats['success'] += 1
            else:
                stats['failed'] += 1
    
    # 输出统计信息
    print("\n" + "=" * 60)
    print("转换完成!")
    print("=" * 60)
    print(f"总文件数: {stats['total']}")
    print(f"成功: {stats['success']}")
    print(f"失败: {stats['failed']}")
    print(f"跳过: {stats['skipped']}")
    print(f"输出目录: {output_dir}")
    
    return stats


def main():
    """主函数"""
    # 获取脚本所在目录
    script_dir = Path(__file__).parent.resolve()
    
    # 源目录（脚本所在目录）
    source_dir = script_dir
    
    # 输出目录（脚本所在目录下创建带时间戳的文件夹）
    output_base_dir = script_dir
    
    print(f"\n源目录: {source_dir}")
    print(f"输出基础目录: {output_base_dir}")
    
    # 显示排除列表
    if EXCLUDE_FILES:
        print(f"\n排除文件列表:")
        for exclude_file in EXCLUDE_FILES:
            print(f"  - {exclude_file}")
    
    # 执行批量转换
    batch_convert_recursive(source_dir, output_base_dir)


if __name__ == '__main__':
    main()
