#!/usr/bin/env python3
"""
StorageOps CLI — 一行安装，开箱即用。

用法:
    storageops install      一键安装（首次执行）
    storageops [pi args]    启动 StorageOps 诊断

安装后目录:
    ~/.storageops/           Pi 主目录
    ├── .pi/settings.json    Pi 配置
    ├── agent/extensions/    storageops.ts
    └── skills/              15 个技能包
"""

import subprocess
import sys
import os
import json
import shutil
from pathlib import Path
from importlib import resources


PI_HOME = Path.home() / ".storageops"
SETTINGS = {
    "skills": ["../skills"],
    "enableSkillCommands": True,
}

SETTINGS_JSON = json.dumps(SETTINGS, indent=2)


def find_pi() -> str:
    """定位 pi 二进制文件."""
    # PATH 优先（npm global install）
    found = shutil.which("pi")
    if found:
        return found
    candidates = [
        str(PI_HOME / "bin" / "pi"),
        os.path.expanduser("~/.pi/bin/pi"),
        "/usr/local/bin/pi",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return "pi"


def is_installed() -> bool:
    """检查 StorageOps 是否已配置."""
    return (
        (PI_HOME / ".pi" / "settings.json").exists()
        and (PI_HOME / "agent" / "extensions" / "storageops.ts").exists()
        and (PI_HOME / "skills").is_dir()
    )


def _package_data_dir() -> Path:
    """定位包内数据目录（skills + extensions）.

    优先级:
    1. importlib.resources（pip install 安装）
    2. __file__ parent（pip install -e . 开发模式）
    """
    # pip install: skills/ 在 storageops_cli 包内
    try:
        ref = resources.files("storageops_cli")
        if isinstance(ref, Path):
            if (ref / "skills").is_dir():
                return ref
            # 某些安装方式产生 MultiplexedPath
            if hasattr(ref, "joinpath"):
                p = Path(str(ref))
                if (p / "skills").is_dir():
                    return p
    except Exception:
        pass
    # editable install: 数据在包目录旁边
    this_dir = Path(__file__).resolve().parent
    if (this_dir / "skills").is_dir():
        return this_dir
    raise FileNotFoundError(
        "找不到 StorageOps 数据目录。请 pip install --force-reinstall storageops"
    )


def cmd_install(force: bool = False):
    """一键安装 StorageOps."""
    if is_installed() and not force:
        print("StorageOps 已安装，无需重复执行。")
        print(f"  配置目录: {PI_HOME}")
        print(f"  如需重装: storageops install --force")
        return

    data = _package_data_dir()
    print(f"📦 安装数据源: {data}")
    print(f"🏠 Pi 主目录:   {PI_HOME}")
    print()

    # 1. 创建目录结构
    for d in [
        PI_HOME / ".pi",
        PI_HOME / "agent" / "extensions",
        PI_HOME / "skills",
    ]:
        d.mkdir(parents=True, exist_ok=True)

    # 2. 写入 settings.json
    settings_path = PI_HOME / ".pi" / "settings.json"
    settings_path.write_text(SETTINGS_JSON)
    print(f"  ✅ settings.json  → {settings_path}")

    # 3. 复制 extension
    ext_src = data / "extensions" / "storageops.ts"
    if not ext_src.is_file():
        # fallback: .pi/extensions/storageops.ts at repo root (editable install)
        ext_src = data.parent / ".pi" / "extensions" / "storageops.ts"
    ext_dst = PI_HOME / "agent" / "extensions" / "storageops.ts"
    shutil.copy2(ext_src, ext_dst)
    print(f"  ✅ storageops.ts  → {ext_dst}")

    # 4. 复制 skills
    skills_src = data / "skills"
    if skills_src.is_dir():
        for skill_dir in sorted(skills_src.iterdir()):
            if skill_dir.is_dir() and skill_dir.name.startswith("storageops-"):
                dst = PI_HOME / "skills" / skill_dir.name
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(skill_dir, dst)
        count = sum(
            1 for d in (PI_HOME / "skills").iterdir()
            if d.is_dir() and d.name.startswith("storageops-")
        )
        print(f"  ✅ skills ({count}个) → {PI_HOME / 'skills'}")
    else:
        print(f"  ⚠️  技能目录未找到: {skills_src}")

    # 5. 验证 pi
    pi = find_pi()
    try:
        result = subprocess.run([pi, "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            ver = (result.stdout + result.stderr).strip()
            if ver:
                print(f"  ✅ pi ({ver})  → {pi}")
            else:
                print(f"  ✅ pi  → {pi}")
        else:
            print(f"  ⚠️  pi 不可用: {pi}")
    except FileNotFoundError:
        print(f"  ⚠️  pi 未找到，请先安装:")
        print(f"     npm install -g @earendil-works/pi-coding-agent")

    print()
    print("🎉 StorageOps 安装完成！")
    print()
    print("快速测试:")
    print(f"  storageops --print --api-key sk-xxx 's5cmd 报 429，帮我诊断'")
    print()
    print("配置 API key (可选，也可每次命令行传 --api-key):")
    print(f"  export ANTHROPIC_API_KEY=sk-xxx")


def cmd_version():
    """显示版本号."""
    try:
        from importlib.metadata import version
        v = version("storageops")
    except Exception:
        v = "unknown"
    pi = find_pi()
    pi_ver = "unknown"
    try:
        r = subprocess.run([pi, "--version"], capture_output=True, text=True)
        pi_ver = r.stdout.strip()
    except Exception:
        pass
    print(f"StorageOps v{v}  (pi: {pi_ver})")
    print(f"  installed: {is_installed()}")
    print(f"  home: {PI_HOME}")


def main():
    # 子命令处理
    args = sys.argv[1:]

    if len(args) >= 1 and args[0] == "install":
        force = "--force" in args or "-f" in args
        cmd_install(force=force)
        return

    if len(args) >= 1 and args[0] in ("--version", "-V"):
        cmd_version()
        return

    if len(args) >= 1 and args[0] in ("--help", "-h"):
        print("🧰 StorageOps — S3 兼容对象存储 AI 诊断工具")
        print()
        print("  安装只需两步:")
        print("    pip install storageops")
        print("    storageops install")
        print()
        print("  然后开始诊断:")
        print("    storageops 's5cmd 报 429 SlowDown 错误'")
        print()
        print("  其他命令:")
        print("    storageops install --force   强制重装")
        print("    storageops --version          版本信息")
        print()
        print("  配置 API key (三选一):")
        print("    export ANTHROPIC_API_KEY=sk-xxx")
        print("    storageops --api-key sk-xxx ...")
        print("    pi /login")
        return

    # 普通运行：检查是否已安装
    if not is_installed():
        print("⚠️  StorageOps 尚未安装。")
        print()
        print("  请先运行: storageops install")
        sys.exit(1)

    # 转发到 pi
    pi = find_pi()
    # 自动设置 PI_HOME（end-user 无需手动设置）
    if "PI_HOME" not in os.environ:
        os.environ["PI_HOME"] = str(PI_HOME)
    os.execvp(pi, [pi] + args)
