[CmdletBinding()]
param(
    [switch]$SkipTests,
    [string]$PythonPath
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

function Invoke-Checked {
    param([string]$Command, [string[]]$Arguments)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command failed with exit code $LASTEXITCODE"
    }
}

$pythonPrefix = @()
$pythonCommand = $null
if ($PythonPath) {
    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
        throw "未找到指定的 Python 构建环境: $PythonPath"
    }
    $pythonCommand = (Resolve-Path -LiteralPath $PythonPath).Path
} else {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        $python = Get-Command py -ErrorAction SilentlyContinue
    }
    if (-not $python) { throw "未找到 Python 3.11+ 构建环境" }
    $pythonCommand = $python.Source
    if ($python.Name -eq "py.exe") { $pythonPrefix = @("-3") }
}

if (-not $SkipTests) {
    Push-Location (Join-Path $repoRoot "webui")
    try {
        Invoke-Checked npm @("ci")
        Invoke-Checked npm @("run", "test:search")
        Invoke-Checked npm @("run", "build")
    } finally {
        Pop-Location
    }

    Invoke-Checked $pythonCommand ($pythonPrefix + @("-m", "pytest", "-q"))
}

Invoke-Checked $pythonCommand ($pythonPrefix + @("-m", "PyInstaller", "--clean", "--noconfirm", "MediaCrawler.spec"))

$distribution = Join-Path $repoRoot "dist\MediaCrawler"
$extensionTarget = Join-Path $distribution "browser_extension"
if (Test-Path $extensionTarget) {
    Remove-Item -LiteralPath $extensionTarget -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path $repoRoot "browser_extension") -Destination $extensionTarget -Recurse
Copy-Item -LiteralPath (Join-Path $repoRoot "LICENSE") -Destination (Join-Path $distribution "LICENSE") -Force
Copy-Item -LiteralPath (Join-Path $repoRoot "README.md") -Destination (Join-Path $distribution "README.md") -Force

$baseVersion = & $pythonCommand @pythonPrefix -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])"
if ($LASTEXITCODE -ne 0) { throw "无法读取 pyproject.toml 版本" }
$releaseVersion = $baseVersion.Trim()
if ($env:GITHUB_REF_TYPE -eq "tag" -and $env:GITHUB_REF_NAME) {
    $tagVersion = $env:GITHUB_REF_NAME -replace '^v', ''
    if ($tagVersion -ne $releaseVersion) {
        throw "Git tag $($env:GITHUB_REF_NAME) 与 pyproject.toml 版本 $releaseVersion 不一致"
    }
}
$versionFile = Join-Path $distribution "RELEASE_VERSION"
Set-Content -LiteralPath $versionFile -Value $releaseVersion -Encoding ascii

Invoke-Checked $pythonCommand ($pythonPrefix + @("scripts/package_exe.py", "--distribution", "dist/MediaCrawler", "--output", "dist"))
Write-Host "EXE distribution ready: dist/MediaCrawler/MediaCrawler.exe" -ForegroundColor Green
