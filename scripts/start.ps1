[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$NoBrowser,
    [int]$ReadyTimeoutSeconds = 45
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$repoRoot = Split-Path -Parent $scriptRoot
$webRoot = Join-Path $repoRoot "webui"
$distRoot = Join-Path $webRoot "dist"
$backendUrl = "http://127.0.0.1:8080"
$healthUrl = "$backendUrl/api/health"
$testMode = $env:MEDIACRAWLER_LAUNCHER_TEST -eq "1"
$ownedProcesses = [System.Collections.Generic.List[object]]::new()

function Write-Check {
    param(
        [string]$Label,
        [bool]$Success,
        [string]$Detail = ""
    )

    $mark = if ($Success) { "[✓]" } else { "[X]" }
    $color = if ($Success) { "Green" } else { "Red" }
    Write-Host ("{0} {1}{2}" -f $mark, $Label, $(if ($Detail) { " $Detail" } else { "" })) -ForegroundColor $color
}

function Write-WarningLine {
    param([string]$Message)
    Write-Host "[!] $Message" -ForegroundColor Yellow
}

function Get-CommandPath {
    param([string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command -and $command.CommandType -eq "ExternalScript") {
        $companion = Get-Command "$Name.cmd" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($companion) { return $companion.Source }
    }
    if ($command) { return $command.Source }
    return $null
}

function Test-TcpPort {
    param([int]$Port)
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync("127.0.0.1", $Port)
        if (-not $task.Wait(500)) { return $false }
        return $client.Connected
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Invoke-LocalPythonCheck {
    param(
        [string]$Command,
        [string[]]$PrefixArgs
    )

    $probe = "import sys; assert sys.version_info >= (3, 11); import fastapi, uvicorn, playwright; print(sys.version.split()[0])"
    try {
        $output = & $Command @PrefixArgs -c $probe 2>$null
        if ($LASTEXITCODE -eq 0) {
            return [pscustomobject]@{
                Command = $Command
                PrefixArgs = $PrefixArgs
                Version = ($output | Select-Object -Last 1)
            }
        }
    } catch {
        return $null
    }
    return $null
}

function Resolve-PythonRuntime {
    $uv = Get-CommandPath "uv"
    if ($uv) {
        $uvRuntime = Invoke-LocalPythonCheck -Command $uv -PrefixArgs @("run", "--no-sync", "python")
        if ($uvRuntime) {
            return [pscustomobject]@{
                FilePath = $uv
                Arguments = @("run", "--no-sync", "uvicorn")
                Display = "uv ($($uvRuntime.Version))"
                DependenciesAvailable = $true
            }
        }
    }

    foreach ($candidate in @("python", "py")) {
        $path = Get-CommandPath $candidate
        if (-not $path) { continue }
        $prefix = if ($candidate -eq "py") { @("-3") } else { @() }
        $runtime = Invoke-LocalPythonCheck -Command $path -PrefixArgs $prefix
        if ($runtime) {
            return [pscustomobject]@{
                FilePath = $path
                Arguments = $prefix + @("-m", "uvicorn")
                Display = "$candidate ($($runtime.Version))"
                DependenciesAvailable = $true
            }
        }
    }

    $pythonExists = (Get-CommandPath "python") -or (Get-CommandPath "py") -or $uv
    if ($pythonExists) {
        return [pscustomobject]@{
            FilePath = $null
            Arguments = @()
            Display = ""
            DependenciesAvailable = $false
        }
    }
    return $null
}

function Get-HealthResponse {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -TimeoutSec 3
        if ($response.StatusCode -ne 200) { return $null }
        $payload = $response.Content | ConvertFrom-Json
        if ($payload.status -ne "ok" -or $payload.backend_available -ne $true) { return $null }
        return $payload
    } catch {
        return $null
    }
}

function Wait-BackendReady {
    param([System.Diagnostics.Process]$Process)
    $deadline = (Get-Date).AddSeconds($ReadyTimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $health = Get-HealthResponse
        if ($health) { return $health }
        if ($Process -and $Process.HasExited) { throw "Backend 进程已提前退出" }
        Start-Sleep -Milliseconds 500
    }
    throw "Backend 在 $ReadyTimeoutSeconds 秒内未通过 $healthUrl ready check"
}

function Start-OwnedProcess {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$Name
    )
    $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -WorkingDirectory $repoRoot -PassThru -WindowStyle Normal
    $ownedProcesses.Add([pscustomobject]@{ Name = $Name; Process = $process })
    return $process
}

function Stop-OwnedProcesses {
    foreach ($owned in ($ownedProcesses | Sort-Object Name -Descending)) {
        $process = $owned.Process
        try {
            if ($process -and -not $process.HasExited) {
                Write-Host "正在关闭本次启动的 $($owned.Name)..." -ForegroundColor DarkGray
                & taskkill.exe /PID $process.Id /T /F *> $null
            }
        } catch {
            Write-WarningLine "无法自动关闭 $($owned.Name)，请检查 PID $($process.Id)"
        }
    }
}

function Wait-ForUser {
    if ($DryRun) { return }
    Write-Host ""
    Write-Host "按 Ctrl+C 关闭本次启动的服务。" -ForegroundColor DarkGray
    while ($true) {
        Start-Sleep -Seconds 1
        foreach ($owned in $ownedProcesses) {
            if ($owned.Process.HasExited) {
                Write-WarningLine "$($owned.Name) 已退出，启动器将结束。"
                return
            }
        }
    }
}

$exitCode = 0
try {
    Write-Host "MediaCrawler" -ForegroundColor Cyan
    Write-Host ""

    if (-not (Test-Path $webRoot -PathType Container)) {
        throw "未找到 webui 目录，请从仓库中的 MediaCrawler.bat 启动"
    }

    $python = Resolve-PythonRuntime
    if (-not $python) {
        Write-Check "Python" $false
        throw "未找到 Python 环境，请安装 Python 3.11+ 后重试"
    }
    if (-not $python.DependenciesAvailable) {
        Write-Check "Python" $true
        Write-Check "Python dependencies" $false
        $uvPath = Get-CommandPath "uv"
        if ($uvPath) {
            Write-Host "请先执行：uv sync --no-dev" -ForegroundColor Yellow
        } elseif (Get-CommandPath "python") {
            Write-Host "请先执行：python -m pip install -r requirements.txt" -ForegroundColor Yellow
        } else {
            Write-Host "请先执行：py -3 -m pip install -r requirements.txt" -ForegroundColor Yellow
        }
        Write-Host "不会在每次启动时自动重装 Python 依赖。" -ForegroundColor Yellow
        throw "Python 依赖未就绪"
    }
    Write-Check "Python" $true "($($python.Display))"
    Write-Check "Python dependencies" $true

    $indexPath = Join-Path $distRoot "index.html"
    if (-not (Test-Path $indexPath -PathType Leaf)) {
        Write-Check "Frontend build" $false
        Write-Host "未找到前端构建文件。" -ForegroundColor Yellow
        Write-Host "开发者请执行：" -ForegroundColor Yellow
        Write-Host "  cd webui" -ForegroundColor Yellow
        Write-Host "  npm ci" -ForegroundColor Yellow
        Write-Host "  npm run build" -ForegroundColor Yellow
        throw "webui/dist/index.html 不存在"
    }
    Write-Check "Frontend build" $true

    if ($DryRun) {
        Write-Host ""
        Write-Host "Dry run：不会启动进程或打开浏览器。" -ForegroundColor Cyan
    }

    $backendHealth = Get-HealthResponse
    if ($backendHealth) {
        Write-Check "Backend" $true "$backendUrl（已运行，复用）"
    } elseif (Test-TcpPort 8080) {
        Write-Check "Backend" $false "$backendUrl 已被其他程序占用"
        throw "8080 端口被占用，且不是当前 MediaCrawler backend；不会终止其他程序"
    } elseif (-not $DryRun) {
        $backendArgs = $python.Arguments + @("api.main:app", "--host", "127.0.0.1", "--port", "8080")
        $backendProcess = Start-OwnedProcess -FilePath $python.FilePath -Arguments $backendArgs -Name "backend"
        $backendHealth = Wait-BackendReady -Process $backendProcess
        Write-Check "Backend" $true "$backendUrl"
    } else {
        Write-Check "Backend" $true "$backendUrl（端口空闲，将启动）"
    }

    if ($backendHealth -and $backendHealth.browser_available -eq $false) {
        Write-Check "Browser" $false "API 检测不可用"
        Write-WarningLine "环境存在警告，可继续使用；请在页面中查看详细状态。"
    } elseif ($backendHealth) {
        Write-Check "Browser" $true
    } else {
        Write-WarningLine "Dry run：浏览器状态将在 backend ready 后由 /api/health 检查。"
    }

    if (-not $DryRun) {
        Write-Host ""
        Write-Host "MediaCrawler 已启动。" -ForegroundColor Green
        if ($backendHealth -and $backendHealth.environment_status -eq "degraded") {
            Write-WarningLine "服务已启动，但环境存在警告，请在页面中查看详细状态。"
        }
        if (-not $NoBrowser -and -not $testMode) {
            Start-Process $backendUrl
            Write-Host "已在浏览器中打开 $backendUrl" -ForegroundColor Green
        }
        if (-not $testMode) {
            Wait-ForUser
        }
    }
} catch {
    $exitCode = 1
    Write-Host "[X] $($_.Exception.Message)" -ForegroundColor Red
} finally {
    Stop-OwnedProcesses
}

exit $exitCode
