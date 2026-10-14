# LLM-AutoTest 使用说明

LLM-AutoTest 是一个基于大语言模型和 Docker 的 C 程序自动化测试工具。

当前主要完成以下流程：

```text
读取需求文档
    ↓
读取 C 源代码
    ↓
调用大模型生成测试用例和测试代码
    ↓
拉起 Docker 沙箱编译并执行
    ↓
返回测试状态、日志和 HTML 报告
```

## 1. 运行准备

进入项目目录：

```powershell
cd "E:\vscode projects\testcase\LLM-AutoTest"
```

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

在 `.env` 中配置 ModelScope：

```dotenv
LLM_BASE_URL=https://api-inference.modelscope.cn/v1
LLM_API_KEY=填写你的ModelScope密钥
LLM_MODEL=Qwen/Qwen3.5-27B
```

启动 Docker Desktop：

```powershell
Start-Process "D:\Docker Desktop\Docker Desktop.exe"
```

如果终端无法识别 `docker`：

```powershell
$env:Path = "D:\Docker Desktop\resources\bin;$env:Path"
```

首次运行时构建沙箱镜像：

```powershell
docker build -t llm-autotest-runner:latest .\docker
```

检查运行环境：

```powershell
python .\main.py --check-env
```

正常结果应包含：

```json
{
  "docker_service": true,
  "runner_image": true,
  "llm_api_key": true
}
```

## 2. 读取需求文档和 C 源码

下面的命令导入一个 Codeflaws 项目，但不调用大模型：

```powershell
python .\generate_codeflaws.py `
  --dataset-root "E:\vscode projects\c_information\codeflaws" `
  --offset 0 `
  --limit 1 `
  --dry-run
```

该步骤会：

- 从项目目录读取 `problem-description-en.json`；
- 将需求内容保存为 `requirements.md`；
- 找出项目目录中的所有 `.c` 文件；
- 按文件名排序并选择第一个 `.c` 文件；
- 生成项目配置文件 `project.yaml`；
- 将导入结果保存到 `inputs/codeflaws/<项目ID>/`。

当前程序不能自动判断两个 `.c` 文件中哪个是缺陷版本，因此默认使用排序后的第一个文件。

## 3. 调用大模型生成测试

删除 `--dry-run`，调用 ModelScope 生成测试：

```powershell
python .\generate_codeflaws.py `
  --dataset-root "E:\vscode projects\c_information\codeflaws" `
  --offset 0 `
  --limit 1
```

这一命令会读取需求和被测源码，然后让大模型生成：

```text
testcases.json       结构化测试用例
test_generated.c     CMocka 测试代码
summary.json         本批生成状态
```

生成文件位于：

```text
workspace/codeflaws-generation/<时间戳>/
```

保存最新生成批次路径：

```powershell
$generationBatch = Get-ChildItem .\workspace\codeflaws-generation -Directory |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

$generationBatch.FullName
Get-Content "$($generationBatch.FullName)\summary.json"
```

`summary.json` 中项目状态为 `GENERATED`，表示测试生成成功。

## 4. 拉起 Docker 沙箱执行

执行刚刚生成的测试：

```powershell
python .\main.py `
  --reuse-generated $generationBatch.FullName `
  --workers 1
```

该步骤会：

- 创建受限 Docker 容器；
- 编译被测 C 源码；
- 将被测程序的 `main` 重命名为 `codeflaws_main`；
- 编译并链接大模型生成的 CMocka 测试代码；
- 在沙箱中执行测试；
- 保存执行结果和日志；
- 执行结束后自动删除容器。

`--reuse-generated` 表示复用已有测试，不会再次调用大模型。

## 5. 查看返回结果

保存最新执行结果目录：

```powershell
$executionBatch = Get-ChildItem .\results -Directory |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

$executionBatch.FullName
```

查看 JSON 汇总：

```powershell
Get-Content "$($executionBatch.FullName)\summary.json"
```

打开 HTML 报告：

```powershell
Start-Process "$($executionBatch.FullName)\summary.html"
```

每个项目的结果目录中包含：

```text
result.json          总体测试状态
test-results.xml     CMocka 测试结果
build.log            编译日志
execution.log        程序执行日志
report.html          单项目报告
```

可能出现的状态：

- `PASSED`：所有测试通过；
- `FAILED`：至少一个测试失败；
- `BUILD_FAILED`：C 代码编译失败；
- `TIMEOUT`：测试执行超时；
- `CRASHED`：测试程序崩溃；
- `GENERATION_FAILED`：大模型生成失败；
- `INFRA_ERROR`：Docker 或文件环境异常。

Codeflaws 中的程序可能本身就包含缺陷，因此出现 `FAILED` 或 `CRASHED` 不一定是测试系统故障，也可能表示测试成功发现了程序问题。

## 6. 完整操作命令

下面是一次完整的单项目测试流程：

```powershell
cd "E:\vscode projects\testcase\LLM-AutoTest"

# 1. 检查 Docker、镜像和大模型配置
python .\main.py --check-env

# 2. 读取需求与源码，并调用大模型生成测试
python .\generate_codeflaws.py `
  --dataset-root "E:\vscode projects\c_information\codeflaws" `
  --offset 0 `
  --limit 1

# 3. 获取刚生成的批次
$generationBatch = Get-ChildItem .\workspace\codeflaws-generation -Directory |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

# 4. 拉起沙箱执行测试
python .\main.py `
  --reuse-generated $generationBatch.FullName `
  --workers 1

# 5. 获取并打开测试结果
$executionBatch = Get-ChildItem .\results -Directory |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

Get-Content "$($executionBatch.FullName)\summary.json"
Start-Process "$($executionBatch.FullName)\summary.html"
```

以上流程中，只有 `generate_codeflaws.py` 未使用 `--dry-run` 时会消耗 ModelScope 额度；使用 `--reuse-generated` 重复执行测试不会再次调用大模型。
