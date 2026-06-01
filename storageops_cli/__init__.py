#!/usr/bin/env python3
"""
StorageOps CLI — 一行安装，开箱即用。

用法:
    storageops install         一键安装（首次执行）
    storageops install --merge 合并安装到已有 Pi 配置中
    storageops [pi args]       启动 StorageOps 诊断

安装后目录（独立模式）:
    ~/.storageops/             Pi 主目录
    ├── .pi/settings.json      Pi 配置
    ├── agent/extensions/      storageops.ts
    └── skills/                15 个技能包
"""

import subprocess
import sys
import os
import json
import shutil
from pathlib import Path
from importlib import resources


PI_HOME = Path.home() / ".storageops"
PI_EXISTING_HOME = Path.home() / ".pi"
MIN_PI_VERSION = "0.78.0"
REQUIRED_API_KEYS = ["ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"]

SETTINGS = {
    "skills": ["../skills"],
    "enableSkillCommands": True,
}
SETTINGS_JSON = json.dumps(SETTINGS, indent=2)

# StorageOps 特有的 settings key，merge 时不会覆盖用户已有配置
STORAGEOPS_KEYS = {"skills", "enableSkillCommands"}


def find_pi() -> str:
    """定位 pi 二进制文件."""
    found = shutil.which("pi")
    if found:
        return found
    candidates = [
        str(PI_HOME / "bin" / "pi"),
        str(Path.home() / ".pi" / "bin" / "pi"),
        "/usr/local/bin/pi",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return "pi"


def check_pi_version(exe: str) -> tuple[bool, str]:
    """检查 pi 版本是否 ≥ MIN_PI_VERSION。返回 (ok, version_str)."""
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True)
        raw = (r.stdout + r.stderr).strip()
        ver = raw.strip() if raw else "0.0.0"
    except Exception:
        return False, "无法检测"

    def _parse(v: str) -> tuple:
        try:
            parts = v.split(".")[:3]
            return tuple(int(p) for p in parts)
        except Exception:
            return (0, 0, 0)

    return _parse(ver) >= _parse(MIN_PI_VERSION), ver


def is_installed(home: Path | None = None) -> bool:
    """检查 StorageOps 是否已配置."""
    h = home or PI_HOME
    return (
        (h / ".pi" / "settings.json").exists()
        and (h / "agent" / "extensions" / "storageops.ts").exists()
        and (h / "skills").is_dir()
    )


def detect_existing_pi() -> bool:
    """检测用户是否已有 Pi Coding Agent 配置."""
    return (PI_EXISTING_HOME / "settings.json").exists()


def detect_api_keys() -> list[str]:
    """检测环境变量中已设置的 API key."""
    found = []
    for key in REQUIRED_API_KEYS:
        if os.environ.get(key):
            found.append(key)
    return found


def _package_data_dir() -> Path:
    """定位包内数据目录（skills + extensions）."""
    try:
        ref = resources.files("storageops_cli")
        if isinstance(ref, Path):
            if (ref / "skills").is_dir():
                return ref
            if hasattr(ref, "joinpath"):
                p = Path(str(ref))
                if (p / "skills").is_dir():
                    return p
    except Exception:
        pass
    this_dir = Path(__file__).resolve().parent
    if (this_dir / "skills").is_dir():
        return this_dir
    raise FileNotFoundError(
        "找不到 StorageOps 数据目录。请 pip install --force-reinstall storageops"
    )


def _copy_extension(data: Path, dst_home: Path) -> None:
    """复制 extension 到目标 Pi 主目录."""
    ext_src = data / "extensions" / "storageops.ts"
    if not ext_src.is_file():
        ext_src = data.parent / ".pi" / "extensions" / "storageops.ts"
    ext_dst = dst_home / "agent" / "extensions" / "storageops.ts"
    ext_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ext_src, ext_dst)
    print(f"  ✅ storageops.ts  → {ext_dst}")


def _copy_skills(data: Path, dst_home: Path) -> None:
    """复制 skills 到目标 skills 目录."""
    skills_src = data / "skills"
    if not skills_src.is_dir():
        print(f"  ⚠️  技能目录未找到: {skills_src}")
        return

    skills_dst = dst_home / "skills"
    skills_dst.mkdir(parents=True, exist_ok=True)
    for skill_dir in sorted(skills_src.iterdir()):
        if skill_dir.is_dir() and skill_dir.name.startswith("storageops-"):
            dst = skills_dst / skill_dir.name
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(skill_dir, dst)
    count = sum(
        1 for d in skills_dst.iterdir()
        if d.is_dir() and d.name.startswith("storageops-")
    )
    print(f"  ✅ skills ({count}个) → {skills_dst}")


def _merge_settings_json(dst_home: Path, settings: dict) -> None:
    """合并 StorageOps 配置到已有 settings.json，自动备份.

    只更新 StorageOps 特有的 key，保留用户其他配置不变。
    """
    dst = dst_home / ".pi" / "settings.json"
    dst.parent.mkdir(parents=True, exist_ok=True)

    if dst.exists():
        # 备份原始配置
        backup = dst.with_suffix(".json.storageops-backup")
        shutil.copy2(dst, backup)
        print(f"  💾 已备份原配置 → {backup}")
        try:
            existing = json.loads(dst.read_text())
        except Exception:
            existing = {}
    else:
        existing = {}

    # 合并：StorageOps key 覆盖，其余保留
    merged = {**existing}
    for key in STORAGEOPS_KEYS:
        if key in settings:
            merged[key] = settings[key]

    dst.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n")
    print(f"  ✅ settings.json  → {dst} (合并完成)")


def _write_settings(dst_home: Path, settings: dict) -> None:
    """写入全新 settings.json."""
    dst = dst_home / ".pi" / "settings.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(settings, indent=2) + "\n")
    print(f"  ✅ settings.json  → {dst}")


def _print_api_key_hint(keys: list[str]) -> None:
    """提示 API key 配置."""
    if keys:
        print(f"  ✅ 检测到 API key: {', '.join(keys)}")
    else:
        print("  💡 未检测到 API key，请配置后使用:")
        print("       export ANTHROPIC_API_KEY=sk-xxx")
        print("       或运行时传入 --api-key sk-xxx")


def cmd_install(force: bool = False, merge: bool = False):
    """一键安装 StorageOps."""
    target_home = PI_HOME

    # --- Step 0: 版本检查 ---
    pi_exe = find_pi()
    ok, ver = check_pi_version(pi_exe)
    if not ok:
        print(f"⚠️  pi 版本 {ver} < {MIN_PI_VERSION}，可能不支持 Extension API。")
        print(f"   建议升级: npm update -g @earendil-works/pi-coding-agent")
        print()
    else:
        print(f"✅ pi ({ver}) → {pi_exe}")

    # --- Step 1: 检测已有 pi 配置 ---
    has_existing = detect_existing_pi()

    if merge:
        # 显式 merge 模式
        if not has_existing:
            print("⚠️  未检测到已有 Pi 配置 (~/.pi/settings.json)，使用独立安装。")
            print()
            merge = False
        else:
            target_home = PI_EXISTING_HOME
            if is_installed(target_home) and not force:
                print("StorageOps 已合并安装到现有 Pi 配置中。")
                print(f"  配置目录: {target_home}")
                print(f"  如需重装: storageops install --merge --force")
                return

    elif has_existing:
        # 检测到已有 pi，询问用户
        if is_installed() and not force:
            print("StorageOps 已安装，无需重复执行。")
            print(f"  配置目录: {PI_HOME}")
            print(f"  如需重装: storageops install --force")
            return

        print()
        print("━" * 60)
        print("检测到你已经在使用 Pi Coding Agent (~/.pi/)。")
        print()
        print("StorageOps 支持两种安装模式:")
        print()
        print("  1. 独立安装 (推荐) — 安装到 ~/.storageops/")
        print("     不影响你已有的 Pi 配置，两个环境互不干扰。")
        print()
        print("  2. 合并安装 — 安装到 ~/.pi/")
        print("     将 StorageOps 的 skills 和 extension 融入你现有的 Pi。")
        print("     你的 settings.json 会被自动备份。")
        print("━" * 60)
        print()
        try:
            choice = input("选择安装模式 [回车=独立安装 / m=合并安装]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            choice = ""
        print()
        if choice == "m":
            target_home = PI_EXISTING_HOME
            if is_installed(target_home) and not force:
                print("StorageOps 已合并安装，无需重复。")
                print("  如需重装: storageops install --merge --force")
                return
        # else: 默认独立安装

    # --- Step 2: 安装 ---
    data = _package_data_dir()
    api_keys = detect_api_keys()

    print(f"📦 安装数据源: {data}")
    print(f"🏠 Pi 主目录:   {target_home}")
    print()

    # 创建 .pi 目录
    (target_home / ".pi").mkdir(parents=True, exist_ok=True)

    # settings.json
    if merge and target_home == PI_EXISTING_HOME:
        _merge_settings_json(target_home, SETTINGS)
    else:
        _write_settings(target_home, SETTINGS)

    # extension + skills
    _copy_extension(data, target_home)
    _copy_skills(data, target_home)

    _print_api_key_hint(api_keys)

    print()
    print("🎉 StorageOps 安装完成！")
    print()
    if not api_keys:
        print("━━━ ⚠️  还差一步：配置 API key ━━━")
        print()
        print("  StorageOps 需要 AI 模型的 API key 才能工作。")
        print()
        print("  任选一种方式:")
        print()
        print("    方式A (推荐)  设置环境变量，一劳永逸:")
        print("      export ANTHROPIC_API_KEY=sk-xxx   # Claude")
        print("      或 export DEEPSEEK_API_KEY=sk-xxx  # DeepSeek")
        print("      或 export OPENAI_API_KEY=sk-xxx    # OpenAI")
        print()
        print("    方式B  每次诊断时传入:")
        print("      storageops --print --provider deepseek --api-key sk-xxx '诊断问题'")
        print()
        print("    方式C  启动后登录 (Pi 原生):")
        print("      storageops  → 进入 TUI → /login")
        print()
        print("  获取 key: https://console.anthropic.com")
        print("        或: https://platform.deepseek.com")
        print()
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    else:
        print(f"  检测到 API key ({', '.join(api_keys)})，可以直接使用:")
        print()
        print(f"  storageops --print 's5cmd 报 429，帮我诊断'")
        print()
        print("  或进入交互模式: storageops")
    print()
    if merge:
        print("💡 你已选择合并安装。原 Pi 配置已备份，使用 pi 命令即可调用 StorageOps。")
    else:
        print(f"💡 使用 storageops 命令即可启动诊断。你的原 Pi 配置 (~/.pi/) 未受影响。")


def cmd_version():
    """显示版本号."""
    try:
        from importlib.metadata import version
        v = version("storageops")
    except Exception:
        v = "unknown"
    ok, ver = check_pi_version(find_pi())
    independent = is_installed(PI_HOME)
    merged = is_installed(PI_EXISTING_HOME)
    print(f"StorageOps v{v}  (pi: {ver})")
    print(f"  独立安装: {'是' if independent else '否'}  ({PI_HOME})")
    print(f"  合并安装: {'是' if merged else '否'}  ({PI_EXISTING_HOME})")


def cmd_help():
    """显示帮助."""
    print("🧰 StorageOps — S3 兼容对象存储 AI 诊断工具")
    print()
    print("  安装只需两步:")
    print("    pip install storageops")
    print("    storageops install")
    print()
    print("  然后开始诊断:")
    print("    storageops 's5cmd 报 429 SlowDown 错误'")
    print()
    print("  安装相关:")
    print("    storageops install                 独立安装（默认）")
    print("    storageops install --merge         合并到已有 Pi 配置")
    print("    storageops install --force         强制重装")
    print()
    print("  其他命令:")
    print("    storageops --version               版本与安装状态")
    print()
    print("  配置 API key (三选一):")
    print("    export ANTHROPIC_API_KEY=sk-xxx")
    print("    storageops --api-key sk-xxx ...")
    print("    pi /login")


def main():
    args = sys.argv[1:]

    if len(args) >= 1 and args[0] == "install":
        force = "--force" in args or "-f" in args
        merge = "--merge" in args or "-m" in args
        cmd_install(force=force, merge=merge)
        return

    if len(args) >= 1 and args[0] in ("--version", "-V"):
        cmd_version()
        return

    if len(args) >= 1 and args[0] in ("--help", "-h"):
        cmd_help()
        return

    # 普通运行：检查是否已安装
    if not (is_installed(PI_HOME) or is_installed(PI_EXISTING_HOME)):
        print("⚠️  StorageOps 尚未安装。")
        print()
        print("  请先运行: storageops install")
        sys.exit(1)

    # 选择 Pi home（独立优先，降级到合并）
    pi_home = PI_HOME if is_installed(PI_HOME) else PI_EXISTING_HOME

    pi = find_pi()

    # 轻量提示：交互模式下未检测到 API key 环境变量
    has_pi_args = len(args) > 0
    if not has_pi_args:
        found = detect_api_keys()
        if not found:
            print("💡 未设置 API key（支持 ANTHROPIC / DEEPSEEK / OPENAI）。")
            print("   进入 TUI 后运行 /login，或 export ANTHROPIC_API_KEY=sk-xxx")
            print()

    if "PI_HOME" not in os.environ:
        os.environ["PI_HOME"] = str(pi_home)
    os.execvp(pi, [pi] + args)
