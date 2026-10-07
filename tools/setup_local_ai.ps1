$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot '.runtime'
New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null

function Get-VerifiedFile($Url, $Destination, $Sha256) {
    if ((Test-Path -LiteralPath $Destination) -and
        (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLower() -eq $Sha256) {
        Write-Output "Already verified: $Destination"
        return
    }
    $partial = "$Destination.partial"
    Write-Output "Downloading: $Url"
    Invoke-WebRequest -Uri $Url -OutFile $partial -TimeoutSec 1800
    if ((Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLower() -ne $Sha256) {
        throw "Checksum mismatch: $partial"
    }
    Move-Item -LiteralPath $partial -Destination $Destination -Force
}

$archive = Join-Path $runtimeRoot 'llama-b11461-bin-win-cpu-x64.zip'
Get-VerifiedFile 'https://github.com/ggml-org/llama.cpp/releases/download/b11461/llama-b11461-bin-win-cpu-x64.zip' $archive 'e283199134e74405a3684cfaa3911708ca7d051a8c2a8dcb10b3dfa1678913c3'
Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $runtimeRoot 'llama') -Force
Get-VerifiedFile 'https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf' (Join-Path $runtimeRoot 'Qwen3-4B-Q4_K_M.gguf') '7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5'
Write-Output 'Local AI runtime and model are ready.'
