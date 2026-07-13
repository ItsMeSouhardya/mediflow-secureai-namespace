$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

docker compose --profile blockchain up -d postgres redis blockchain

Write-Host "Waiting for the local blockchain node and its dependencies..."
$deadline = (Get-Date).AddMinutes(5)
do {
    $containerId = docker compose ps -q blockchain
    $status = if ($containerId) {
        docker inspect --format '{{.State.Health.Status}}' $containerId 2>$null
    }
    if ($status -eq "healthy") { break }
    if ((Get-Date) -ge $deadline) { throw "Blockchain node did not become healthy within five minutes." }
    Start-Sleep -Seconds 3
} while ($true)

docker compose exec -T blockchain npm run deploy:local

$deployment = Get-Content "$root\blockchain\deployments\31337.json" -Raw | ConvertFrom-Json
$env:BLOCKCHAIN_ENABLED = "true"
$env:BLOCKCHAIN_RPC_URL = "http://127.0.0.1:8545"
$env:BLOCKCHAIN_CHAIN_ID = "31337"
$env:BLOCKCHAIN_CONTRACT_ADDRESS = $deployment.address
$env:BLOCKCHAIN_DEVELOPMENT_UNLOCKED_ACCOUNT = "true"

Write-Host "Task 16 backend configuration is ready."
Write-Host "Contract: $($deployment.address)"
Write-Host "Starting the API at http://127.0.0.1:5000 ..."

Set-Location "$root\backend"
Write-Host "Applying database migrations..."
& ".\.venv\Scripts\python.exe" -m flask --app app db upgrade

& ".\.venv\Scripts\python.exe" -m flask --app app run --host 127.0.0.1 --port 5000
