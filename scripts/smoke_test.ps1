# Test de fumée de l'API après `docker compose up -d` (PowerShell, depuis la racine du projet).
# Usage : .\scripts\smoke_test.ps1
$ErrorActionPreference = "Stop"
$apiKey = (Get-Content .env | Where-Object { $_ -match '^API_KEY=' }) -replace '^API_KEY=', ''
$headers = @{ "X-API-Key" = $apiKey }
$base = "http://localhost:8000"

Write-Host "1) Santé de l'API"
Invoke-RestMethod "$base/health" | Format-List

Write-Host "2) Actifs suivis"
Invoke-RestMethod "$base/v1/assets" -Headers $headers | Format-Table

Write-Host "3) Risque AAPL sur 5 jours"
Invoke-RestMethod "$base/v1/risk/aapl.us?days=5" -Headers $headers | Format-Table

Write-Host "4) Score de fraude d'une transaction"
$body = @{ time_offset_s = 3600; amount = 120.5; v = @(0.0) * 28 } | ConvertTo-Json
Invoke-RestMethod "$base/v1/fraud/score" -Method Post -Headers $headers -ContentType "application/json" -Body $body | Format-List

Write-Host "5) Sans clé API -> doit renvoyer 401"
try { Invoke-RestMethod "$base/v1/assets"; Write-Host "ERREUR : accès sans clé accepté" }
catch { Write-Host "OK :" $_.Exception.Response.StatusCode }
