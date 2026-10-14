[CmdletBinding()]
param(
    [ValidateSet('Check', 'Serve', 'Demo', 'Benchmark', 'Mock')]
    [string]$Action = 'Serve',
    [ValidateSet('Native', 'Json')]
    [string]$Guard = 'Native',
    [ValidateRange(1024, 65535)] [int]$ModelPort = 11435,
    [ValidateRange(0, 65535)] [int]$ServicePort = 0,
    [ValidateRange(2048, 8192)] [int]$ContextLength = 4096
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Project Python is missing. Create .venv and install requirements.txt first; see ARCHITECTURE_AND_RUN.md.'
}
if ($ModelPort -eq $ServicePort) { throw 'ModelPort and ServicePort must differ.' }
if ($ServicePort -gt 0 -and $ServicePort -lt 1024) { throw 'Use ServicePort 0 for automatic selection, or a port of at least 1024.' }

# All settings are scoped to this invocation and restored on exit. Existing
# .env files, Ollama desktop settings, and the port 11434 service are untouched.
$profile = @{
    MOCK_LLM = 'false'
    OLLAMA_BASE_URL = "http://127.0.0.1:$ModelPort"
    GUARD_BASE_URL = "http://127.0.0.1:$ModelPort"
    GUARD_BACKEND = 'llama_guard_ollama'
    AGENT_MODEL = 'llama3.2:3b'
    GUARD_MODEL = 'llama3.2:3b'
    LLAMA_GUARD_OLLAMA_MODEL = 'llama-guard3:8b'
    OLLAMA_NUM_CTX = "$ContextLength"
    OLLAMA_KEEP_ALIVE = '5m'
    AGENT_TIMEOUT_MS = '300000'
    GUARD_TIMEOUT_MS = '300000'
    GUARD_LAYERS = 'detector,judge,watch,egress'
    A2A_HOST = '127.0.0.1'
    A2A_PORT = "$ServicePort"
    A2A_PUBLIC_URL = "http://127.0.0.1:$ServicePort/"
    CUDA_VISIBLE_DEVICES = '0'
    OLLAMA_VULKAN = '0'
    GGML_VK_VISIBLE_DEVICES = '-1'
    OLLAMA_HOST = "127.0.0.1:$ModelPort"
    OLLAMA_MAX_LOADED_MODELS = '1'
    OLLAMA_NUM_PARALLEL = '1'
    OLLAMA_CONTEXT_LENGTH = "$ContextLength"
    OLLAMA_FLASH_ATTENTION = '1'
    OLLAMA_KV_CACHE_TYPE = 'q8_0'
    OLLAMA_NO_CLOUD = '1'
}
if ($Guard -eq 'Json') { $profile.GUARD_BACKEND = 'ollama_json' }
if ($Action -eq 'Mock') { $profile.MOCK_LLM = 'true' }
$oldEnvironment = @{}
$ownedOllama = $null
$exitCode = 0
Push-Location -LiteralPath $projectRoot
try {
    foreach ($name in $profile.Keys) {
        $oldEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        [Environment]::SetEnvironmentVariable($name, $profile[$name], 'Process')
    }
    if ($Action -ne 'Mock') {
        if ($Action -in @('Serve', 'Demo')) {
            $serviceListener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $ServicePort)
            try {
                $serviceListener.Start()
                if ($ServicePort -eq 0) {
                    $ServicePort = $serviceListener.LocalEndpoint.Port
                    $profile.A2A_PORT = "$ServicePort"
                    $profile.A2A_PUBLIC_URL = "http://127.0.0.1:$ServicePort/"
                    [Environment]::SetEnvironmentVariable('A2A_PORT', $profile.A2A_PORT, 'Process')
                    [Environment]::SetEnvironmentVariable('A2A_PUBLIC_URL', $profile.A2A_PUBLIC_URL, 'Process')
                }
            }
            catch { throw "Cannot bind workflow port $ServicePort. Use -ServicePort 0 for automatic selection. $($_.Exception.Message)" }
            finally { $serviceListener.Stop() }
        }
        # Check occupancy without communicating with a user's existing server.
        $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $ModelPort)
        try { $listener.Start() }
        catch { throw "Model port $ModelPort is occupied. Choose another -ModelPort; this launcher owns a separate Ollama server." }
        finally { $listener.Stop() }
        $ollamaCommand = Get-Command ollama -ErrorAction SilentlyContinue
        $ollamaPath = if ($ollamaCommand) { $ollamaCommand.Source } else {
            Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
        }
        if (-not (Test-Path -LiteralPath $ollamaPath)) { throw 'Install Ollama for Windows first.' }
        New-Item -ItemType Directory -Path (Join-Path $projectRoot 'results') -Force | Out-Null
        $logPrefix = Join-Path $projectRoot ("results\local_cuda_ollama_" + [Guid]::NewGuid().ToString('N'))
        Write-Host "Starting a private CUDA model service on port $ModelPort (one loaded model at a time)."
        $ownedOllama = Start-Process -FilePath $ollamaPath -ArgumentList 'serve' -PassThru -WindowStyle Hidden `
            -RedirectStandardOutput "$logPrefix.stdout.log" -RedirectStandardError "$logPrefix.stderr.log"
        $ready = $false
        for ($attempt = 0; $attempt -lt 60; $attempt++) {
            if ($ownedOllama.HasExited) { throw "Ollama exited. See $logPrefix.stderr.log" }
            try {
                Invoke-RestMethod -Uri "$($profile.OLLAMA_BASE_URL)/api/version" -TimeoutSec 2 | Out-Null
                $ready = $true
                break
            } catch { Start-Sleep -Milliseconds 500 }
        }
        if (-not $ready) { throw "Ollama did not become ready. See $logPrefix.stderr.log" }
        & $pythonPath -m deployment.local_cuda --action ($Action.ToLowerInvariant()) --runtime-log "$logPrefix.stderr.log"
    } else {
        & $pythonPath -m deployment.local_cuda --action mock
    }
    $exitCode = $LASTEXITCODE
} finally {
    if ($null -ne $ownedOllama -and -not $ownedOllama.HasExited) {
        # Explicitly unload models before terminating the parent. On Windows
        # terminating a parent alone may leave a model runner alive briefly.
        $usedModels = @($profile.AGENT_MODEL, $profile.GUARD_MODEL)
        if ($Guard -eq 'Native') { $usedModels += $profile.LLAMA_GUARD_OLLAMA_MODEL }
        foreach ($model in ($usedModels | Select-Object -Unique)) {
            try {
                $unloadBody = @{ model = $model; keep_alive = 0; stream = $false } | ConvertTo-Json -Compress
                Invoke-RestMethod -Uri "$($profile.OLLAMA_BASE_URL)/api/generate" -Method Post `
                    -ContentType 'application/json' -Body $unloadBody -TimeoutSec 10 | Out-Null
            } catch { Write-Warning "Could not unload $model before shutdown: $($_.Exception.Message)" }
        }
        # Stop only the child process started above, never the desktop service.
        Stop-Process -InputObject $ownedOllama -ErrorAction SilentlyContinue
    }
    foreach ($name in $oldEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $oldEnvironment[$name], 'Process')
    }
    Pop-Location
}
if ($exitCode -ne 0) { throw "Local run failed (exit $exitCode). Inspect the saved report in results." }
