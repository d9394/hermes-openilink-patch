#!/usr/bin/env python3

import os
import re
import sys
import shutil
from pathlib import Path
from datetime import datetime

def backup_file(path):
    time_stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = path.parent / f"{path.name}.{time_stamp}.bak"
    shutil.copy2(path, bak)
    print(f"[BACKUP] {bak}")

def parse_diff(diff_text):
    files = []
    pattern = re.compile(
        r'^diff --git a/(.*?) b/(.*?)\n(.*?)(?=^diff --git |\Z)',
        re.M | re.S
    )
    for old_file, new_file, body in pattern.findall(diff_text):
        files.append({
            "old": old_file,
            "new": new_file,
            "body": body
        })
    return files

def apply_new_file(root, relpath, body):
    lines = []
    for line in body.splitlines():
        if line.startswith('+++'):
            continue
        if line.startswith('@@'):
            continue
        if line.startswith('+'):
            lines.append(line[1:])
    target = root / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        print(f"[SKIP] exists: {relpath}")
        return
    target.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8"
    )
    print(f"[ADD ] {relpath}")


def patch_existing_file(root, relpath, body):
    """
    纯 Python 实现：带上下文模糊搜索的 Git Unified Diff 应用器。
    能够容忍目标文件行号偏移。
    """
    target = root / relpath
    if not target.exists():
        print(f"[MISS] {relpath}")
        return

    # 1. 备份目标文件
    backup_file(target)
    
    # 2. 读取原始文件内容并拆分为行（保留换行符）
    original_lines = target.read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True)
    
    # 3. 提取 Hunk 头部信息和内容
    hunk_pattern = re.compile(r'@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@.*?\n(.*?)(?=\n@@ |\Z)', re.S)
    hunks = hunk_pattern.findall(body)
    
    if not hunks:
        print(f"[SKIP ] no valid hunks: {relpath}")
        return

    changed = False
    
    # 4. 遍历并应用每个 Hunk
    for old_start, old_count, new_start, new_count, hunk_body in hunks:
        # 解析 hunk 中的具体行
        expected_context = []  # 期望在目标文件中存在的上下文
        new_lines = []         # 替换进去的新内容
        
        for line in hunk_body.split('\n'):
            if line.startswith('+'):
                new_lines.append(line[1:] + '\n')
            elif line.startswith('-'):
                expected_context.append(line[1:] + '\n')
            elif line.startswith(' '):
                expected_context.append(line[1:] + '\n')
                new_lines.append(line[1:] + '\n')
            elif line == '':
                continue  # 忽略末尾空行

        context_len = len(expected_context)
        if context_len == 0:
            continue

        # 【核心修复：滑动窗口模糊搜索】
        # 不再死板地使用 old_start，而是在整个文件中搜索匹配的上下文
        found_idx = -1
        for i in range(len(original_lines) - context_len + 1):
            if original_lines[i : i + context_len] == expected_context:
                found_idx = i
                break  # 找到第一个匹配项即停止

        # 如果在整个文件中都找不到匹配的上下文
        if found_idx == -1:
            print(f"[WARN] Context not found anywhere in {relpath}, skipping hunk.")
            continue

        # 上下文完全匹配，执行安全的切片替换
        original_lines[found_idx : found_idx + context_len] = new_lines
        changed = True
        print(f"[INFO] Hunk applied successfully at line {found_idx + 1} (Original expected: {old_start})")

    # 5. 写回文件
    if changed:
        target.write_text("".join(original_lines), encoding="utf-8")
        print(f"[PATCH] {relpath}")
    else:
        print(f"[SKIP ] no match: {relpath}")

def main():
    if len(sys.argv) != 3:
        print(
            "Usage:\n"
            "python patch.py /path/to/hermes-agent 9038.diff"
        )
        sys.exit(1)
    root = Path(sys.argv[1])
    diff_file = Path(sys.argv[2])
    diff_text = diff_file.read_text(
        encoding="utf-8",
        errors="ignore"
    )
    files = parse_diff(diff_text)
    for item in files:
        relpath = item["new"]
        body = item["body"]
        print(f"Processing {relpath} ...")
        if "new file mode" in body:
            apply_new_file(
                root,
                relpath,
                body
            )
        else:
            patch_existing_file(
                root,
                relpath,
                body
            )
        print("\n")
    print("\nDone.")

if __name__  == "__main__":
    main()
