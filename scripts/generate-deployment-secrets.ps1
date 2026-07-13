$ErrorActionPreference = "Stop"

function New-RandomBytes([int] $Length) {
    $bytes = New-Object byte[] $Length
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    }
    finally {
        $generator.Dispose()
    }
    return $bytes
}

function New-HexSecret {
    $bytes = New-RandomBytes 32
    return ([System.BitConverter]::ToString($bytes) -replace "-", "").ToLowerInvariant()
}

function New-FernetKey {
    $base64 = [System.Convert]::ToBase64String((New-RandomBytes 32))
    return $base64.Replace("+", "-").Replace("/", "_")
}

Write-Output "Copy these values into a password manager. Do not commit them."
Write-Output "SECRET_KEY=$(New-HexSecret)"
Write-Output "JWT_SECRET_KEY=$(New-HexSecret)"
Write-Output "DOCUMENT_ENCRYPTION_KEY=$(New-FernetKey)"
Write-Output "METRICS_SECRET_KEY=$(New-HexSecret)"
Write-Output "BLOCKCHAIN_REFERENCE_SECRET=$(New-HexSecret)"
