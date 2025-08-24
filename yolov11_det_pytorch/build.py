#!/usr/bin/env python3
"""
一键流程：
1. 复制源代码目录（src）到构建工作目录（build/pkg）。
2. 使用 Cython 将 Python 源代码编译为共享对象文件（.so 文件），仅针对一级包。
3. 清理构建目录中的 Python 源文件（.py）和 Cython 中间文件（.c），但保留初始化文件（__init__.py）。
4. 将编译后的文件移动到混淆目录（build/obf/{package_name,...}）。
5. 使用 uv 工具进行最终构建，生成分发包（wheel 文件），例如：dist/{package_name}-0.1.0-*.whl。
"""
import os, toml, setuptools
import shutil, subprocess, sys
from pathlib import Path

# 定义源代码目录、工作目录、混淆目录和构建目录
SRC  = Path("src")           # 源代码目录
WORK = Path("build/pkg")     # 工作目录，用于临时存放编译过程中的文件
OBF  = Path("build/obf")     # 混淆目录，用于存放编译后的文件
BUILD = Path("build")        # 构建目录，用于存放构建过程中的文件
DIST = BUILD.parent / "dist" # 输出目录，最终存放生成的whl文件和二进制文件

# ---------- 工具函数 ----------

def clean():
    """
    清理构建目录和临时文件。
    删除 build、dist 和 *.egg-info 目录，以及源代码目录中的 __pycache__ 和 .pyc 文件。
    """
    for p in ("build", "dist", "*.egg-info"):
        shutil.rmtree(p, ignore_errors=True)

    for path in SRC.rglob("*"):
        if path.is_dir() and path.name == "__pycache__":
            shutil.rmtree(path, ignore_errors=True)
        elif path.is_file() and path.suffix == ".pyc":
            path.unlink()

def copy_source():
    """
    将源代码从 src 复制到 build/pkg 目录。
    """
    shutil.rmtree(WORK, ignore_errors=True)
    shutil.copytree(SRC, WORK)

def compile_so():
    """
    使用 Cython 将 Python 文件编译为 .so 文件。
    1. 查找 WORK 目录下的一级包。
    2. 生成临时的 setup_cython.py 文件，用于 Cython 编译。
    3. 调用 Cython 编译命令，生成 .so 文件。
    4. 删除临时的 setup_cython.py 文件。
    """
    packages = [p for p in WORK.iterdir()
                if p.is_dir() and (p / "__init__.py").exists()]
    if not packages:
        raise RuntimeError("src 下未找到任何一级包")

    nthreads: int = max(1, (os.cpu_count() or 1) // 2)
    patterns = [f"{pkg.name}/**/*.py" for pkg in packages]
    setup_py = WORK / "setup_cython.py"
    setup_py.write_text(f"""
from setuptools import setup
from Cython.Build import cythonize
setup(
    ext_modules=cythonize(
        {patterns!r},
        language_level=3,
        nthreads={nthreads}
    )
)
""")
    subprocess.check_call([sys.executable, setup_py.name, "build_ext", "--inplace"], cwd=WORK)
    setup_py.unlink(missing_ok=True)

def move_to_obf():
    """
    将编译后的文件从 WORK 目录移动到 OBF 目录。
    """
    shutil.rmtree(OBF, ignore_errors=True)
    OBF.mkdir(parents=True, exist_ok=True)
    for pkg in WORK.iterdir():
        if not pkg.is_dir():
            continue
        dest = OBF / pkg.name
        shutil.copytree(pkg, dest, dirs_exist_ok=True)

def trim_obf():
    """
    清理 OBF 目录中的文件。
    删除所有 .py 和 .c 文件，但保留 __init__.py 文件。
    """
    for ext in ("*.py", "*.c"):
        for f in OBF.rglob(ext):
            if f.name == "__init__.py":
                continue
            f.unlink(missing_ok=True)

def cleanup_egginfo():
    """
    删除 WORK 和 OBF 目录中的 *.egg-info 文件。
    """
    for p in (WORK, OBF):
        for egg in p.rglob("*.egg-info"):
            shutil.rmtree(egg, ignore_errors=True)

def purge_build_artifacts():
    """
    清理构建过程中产生的临时文件。
    删除 OBF 目录中的 build 目录、.c 和 .o 文件。
    删除 WORK 目录。
    """
    build_dir = OBF / "build"
    shutil.rmtree(build_dir, ignore_errors=True)
    for ext in ("*.c", "*.o"):
        for f in OBF.rglob(ext):
            f.unlink(missing_ok=True)

    shutil.rmtree(WORK, ignore_errors=True)

def write_obf_pyproject():
    """
    生成 OBF 目录中的 pyproject.toml 文件。
    1. 拷贝外部的 pyproject.toml 文件到构建目录。
    2. 读取拷贝后的 pyproject.toml 文件内容。
    3. 使用 setuptools.find_namespace_packages() 自动发现包。
    4. 动态生成 package-data，匹配所有 .so 文件。
    5. 将修改后的内容写回到目标 pyproject.toml 文件。
    """
    # 拷贝外部的 pyproject.toml 文件到构建目录
    shutil.copy("pyproject.toml", BUILD / "pyproject.toml")
    shutil.copy("README.md", BUILD / "README.md")

    # 读取拷贝后的 pyproject.toml 文件内容
    with open(BUILD / "pyproject.toml", "r") as f:
        pyproject_data = toml.load(f)

    # 使用 setuptools.find_namespace_packages() 自动发现包
    packages = setuptools.find_namespace_packages(where=str(OBF))
    package_dir = {pkg: f"obf/{pkg.replace('.', '/')}" for pkg in packages}
    package_data = {}

    # 动态生成 package-data，匹配所有 .so 文件
    for pkg in packages:
        # 构建包的路径
        pkg_path = OBF / pkg.replace('.', '/')
        # 匹配所有 .so 文件
        so_files = list(pkg_path.glob("*.so"))
        # 将匹配到的文件路径转换为相对路径
        relative_so_files = [str(so.relative_to(pkg_path)) for so in so_files]
        package_data[pkg] = relative_so_files

    # 添加 [tool.setuptools] 部分
    pyproject_data.setdefault("tool", {}).setdefault("setuptools", {})["packages"] = packages

    # 添加 [tool.setuptools.package-dir] 部分
    pyproject_data.setdefault("tool", {}).setdefault("setuptools", {}).setdefault("package-dir", package_dir)

    # 添加 [tool.setuptools.package-data] 部分
    pyproject_data.setdefault("tool", {}).setdefault("setuptools", {}).setdefault("package-data", package_data)

    # 将修改后的内容写回到目标 pyproject.toml 文件
    with open(BUILD / "pyproject.toml", "w") as f:
        toml.dump(pyproject_data, f)

def uv_build():
    """
    等价于：
        cd build
        uv build --out-dir ../dist
    这样 wheel 会出现在 build 的同级目录 dist/ 中
    """
    subprocess.check_call(
        ["uv", "build", "--out-dir", DIST.absolute()],
        cwd=BUILD.absolute()
    )

# ---------- 主流程 ----------

def main():
    clean()                 # 清理构建目录和临时文件
    copy_source()           # 复制源代码到工作目录
    compile_so()            # 使用 Cython 编译 Python 文件为 .so 文件
    move_to_obf()           # 将编译后的文件移动到混淆目录
    trim_obf()              # 清理混淆目录中的 .py 和 .c 文件
    cleanup_egginfo()       # 删除 *.egg-info 文件
    purge_build_artifacts() # 清理构建过程中产生的临时文件
    write_obf_pyproject()   # 生成 OBF 目录中的 pyproject.toml 文件
    uv_build()              # 生成 whl 文件

    print("\n✅ 一键流程结束")
    print(f"   编译结果：{OBF.resolve()}")
    print(f"   分发包：  {DIST.resolve()}")
    print("\n安装示例：")
    print(f"   uv add {next(DIST.glob('*.whl'), '（未找到 wheel）')}")

if __name__ == "__main__":
    main()