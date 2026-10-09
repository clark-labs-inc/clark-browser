# Copyright 2026 Clark Labs Inc.
# SPDX-License-Identifier: MIT
# Run after extracting the Windows portable ZIP; ZIPs do not preserve ACLs.
[CmdletBinding()]
param([string]$BrowserDirectory = $PSScriptRoot)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path -LiteralPath $BrowserDirectory).Path
if (-not (Test-Path -LiteralPath (Join-Path $Root "chrome.exe") -PathType Leaf)) {
  throw "No chrome.exe in $Root; select the extracted browser directory."
}
# AppContainer and Less Privileged AppContainer read/execute only.
& icacls.exe $Root /grant '*S-1-15-2-1:(OI)(CI)(RX)' '*S-1-15-2-2:(OI)(CI)(RX)' /T /Q
if ($LASTEXITCODE -ne 0) {
  throw "Failed to set sandbox permissions for $Root (icacls exit $LASTEXITCODE)."
}
Write-Host "Sandbox permissions prepared for $Root"
