#!/usr/bin/env python3
"""文件功能：在 Docker 执行镜像内编译并运行一个隔离的 CMocka 任务。"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

INPUT = Path("/task/input")
OUTPUT = Path("/task/output")
BUILD = Path("/task/build")


def write_json(data: dict) -> None:
    """将机器可读的任务结果写入宿主机挂载的输出目录。"""
    (OUTPUT / "result.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


def empty_junit(message: str) -> None:
    """当 CMocka 未生成结果时，创建一个有效的 JUnit 文件。"""
    suite = ET.Element("testsuite", name="cmocka", tests="0", failures="0", errors="1")
    case = ET.SubElement(suite, "testcase", name="infrastructure")
    ET.SubElement(case, "error", message=message)
    ET.ElementTree(suite).write(OUTPUT / "test-results.xml", encoding="utf-8", xml_declaration=True)


def main() -> int:
    """按选定调用模式编译、运行并导出全部结果文件。"""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    config = json.loads((INPUT / "task.json").read_text(encoding="utf-8"))
    executable = BUILD / "tests"
    common = ["gcc", f"-std={config['compiler']['standard']}", *config["compiler"]["flags"]]
    for include_dir in config["include_dirs"]:
        common.extend(["-I", str(INPUT / include_dir)])
    sources = [str(INPUT / source) for source in config["source_files"]]
    link_flags = config["compiler"].get("link_flags", [])
    commands = []
    test_style = config.get("test_style", "function")
    if test_style == "console":
        program = BUILD / "program_under_test"
        commands.append([*common, *sources, *link_flags, "-o", str(program)])
        commands.append([*common, "-include", "/opt/runner/cmocka_compat.h",
                         str(INPUT / "test_generated.c"), "-lcmocka", "-o", str(executable)])
    elif test_style == "direct_main":
        # 只重命名被测源码编译单元中的 main；生成的测试代码保留自己的
        # main()，并直接调用链接后的 codeflaws_main() 符号。
        objects = []
        for index, source in enumerate(sources):
            object_file = BUILD / f"subject_{index}.o"
            commands.append([*common, "-Dmain=codeflaws_main", "-c", source,
                             "-o", str(object_file)])
            objects.append(str(object_file))
        commands.append([*common, "-D_GNU_SOURCE", "-include", "/opt/runner/cmocka_compat.h",
                         str(INPUT / "test_generated.c"), *objects, *link_flags,
                         "-lcmocka", "-o", str(executable)])
    else:
        commands.append([*common, *sources, str(INPUT / "test_generated.c"), *link_flags,
                         "-lcmocka", "-o", str(executable)])
    build_parts = []
    built = None
    for command in commands:
        built = subprocess.run(command, capture_output=True, text=True, check=False)
        build_parts.append(f"$ {' '.join(command)}\n{built.stdout}{built.stderr}")
        if built.returncode:
            break
    assert built is not None
    build_log = "\n".join(build_parts)
    (OUTPUT / "build.log").write_text(build_log, encoding="utf-8")
    if built.returncode:
        (OUTPUT / "execution.log").write_text("Test was not executed because compilation failed.\n", encoding="utf-8")
        empty_junit("compilation failed")
        write_json({"status": "BUILD_FAILED", "build_returncode": built.returncode,
                    "execution_returncode": None, "duration_seconds": time.monotonic() - started})
        return 0

    # CMocka 将 XML 直接写入宿主机挂载的输出目录，同时单独保留标准输出
    # 和标准错误，方便定位问题。
    env = os.environ.copy()
    env["CMOCKA_MESSAGE_OUTPUT"] = "XML"
    env["CMOCKA_XML_FILE"] = str(OUTPUT / "test-results.xml")
    if test_style == "console":
        env["PROGRAM_UNDER_TEST"] = str(BUILD / "program_under_test")
    timeout = float(config.get("test_timeout_seconds", 5))
    try:
        ran = subprocess.run([str(executable)], capture_output=True, text=True, check=False,
                             timeout=timeout, env=env, start_new_session=True)
        (OUTPUT / "execution.log").write_text(ran.stdout + ran.stderr, encoding="utf-8")
        if ran.returncode == 0:
            status = "PASSED"
        elif ran.returncode < 0 or ran.returncode in (128 + signal.SIGSEGV, 128 + signal.SIGABRT):
            status = "CRASHED"
        else:
            status = "FAILED"
        if not (OUTPUT / "test-results.xml").exists():
            empty_junit(f"test exited with code {ran.returncode}")
        write_json({"status": status, "build_returncode": 0,
                    "execution_returncode": ran.returncode, "duration_seconds": time.monotonic() - started})
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or b"") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        error = (exc.stderr or b"") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        if isinstance(output, bytes): output = output.decode(errors="replace")
        if isinstance(error, bytes): error = error.decode(errors="replace")
        (OUTPUT / "execution.log").write_text(output + error + f"\nTimed out after {timeout}s.\n", encoding="utf-8")
        empty_junit("test process timed out")
        write_json({"status": "TIMEOUT", "build_returncode": 0,
                    "execution_returncode": None, "duration_seconds": time.monotonic() - started})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

