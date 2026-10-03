#requires -Version 5.1
<#
.SYNOPSIS
Connect MiroFish to this computer's existing 9Router balance reader.
.DESCRIPTION
Run this helper yourself only after reviewing it. It reads the existing 9Router
machine-id and auth/cli-secret, derives the same CLI token as 9Router, and saves
that token through the local MiroFish settings API. It never changes 9Router,
prints credentials, copies credentials to the clipboard, or signs in to OpenCode.

The 9Router CLI token grants administrative access to 9Router. MiroFish's balance
reader must restrict its use to the OpenCode account list and selected account's
usage endpoint on the configured local 9Router origin. This is not a scoped,
read-only token. A wallet value is only as recent as 9Router's existing sync.

-WhatIf does not read credential contents or make HTTP requests.
.EXAMPLE
.\deploy\Connect-9RouterBalance.ps1 -WhatIf
.EXAMPLE
.\deploy\Connect-9RouterBalance.ps1
#>
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param(
    [string]$MiroFishBaseUrl = 'http://127.0.0.1:5001',
    [string]$RouterDataDirectory = 'C:\Users\PC\Desktop\9-router\data'
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

function Get-PropertyValue {
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) { return $null }
    return $property.Value
}

function Assert-LocalMiroFishUrl {
    param([string]$Value)
    $parsed = $null
    if (-not [Uri]::TryCreate($Value, [UriKind]::Absolute, [ref]$parsed)) {
        throw 'MiroFish 網址格式不正確。'
    }
    if ($parsed.Scheme -ne 'http' -or
        $parsed.Host -notin @('localhost', '127.0.0.1', '[::1]', '::1') -or
        $parsed.Port -notin @(3000, 3100, 5001) -or
        $parsed.UserInfo -or $parsed.Query -or $parsed.Fragment -or
        $parsed.AbsolutePath -ne '/') {
        throw '此助手只接受本機 MiroFish 網址，連接埠為 3000、3100 或 5001。'
    }
    return $parsed.GetLeftPart([UriPartial]::Authority)
}

function Assert-LocalRouterConfig {
    param($Config)
    if ((Get-PropertyValue $Config 'provider') -ne 'ninerouter') {
        throw '請先在 MiroFish 設定頁選擇並儲存 9Router，再執行此助手。'
    }
    $base = Get-PropertyValue $Config 'base_url'
    $parsed = $null
    if (-not [Uri]::TryCreate([string]$base, [UriKind]::Absolute, [ref]$parsed) -or
        $parsed.Scheme -ne 'http' -or $parsed.Port -ne 20128 -or
        $parsed.Host -notin @('localhost', '127.0.0.1', 'host.docker.internal') -or
        $parsed.UserInfo -or $parsed.Query -or $parsed.Fragment -or
        $parsed.AbsolutePath.TrimEnd('/') -ne '/v1') {
        throw '此助手只連接本機 9Router：localhost、127.0.0.1 或 host.docker.internal，連接埠 20128，路徑 /v1。'
    }
    return $parsed.GetLeftPart([UriPartial]::Authority)
}

function Invoke-LocalSettingsRequest {
    param(
        $Client,
        [string]$Method,
        [string]$Url,
        [string]$Origin,
        [string]$CsrfToken,
        [string]$Body
    )
    $request = $null
    $response = $null
    try {
        $httpMethod = [System.Net.Http.HttpMethod]::new($Method)
        $request = [System.Net.Http.HttpRequestMessage]::new($httpMethod, $Url)
        $request.Headers.Accept.ParseAdd('application/json')
        [void]$request.Headers.TryAddWithoutValidation('Origin', $Origin)
        if ($CsrfToken) {
            [void]$request.Headers.TryAddWithoutValidation('X-MiroFish-CSRF', $CsrfToken)
        }
        if ($Body) {
            $request.Content = [System.Net.Http.StringContent]::new($Body, [Text.Encoding]::UTF8, 'application/json')
        }
        try {
            $response = $Client.SendAsync($request).GetAwaiter().GetResult()
        } catch {
            throw '無法連線到本機 MiroFish；請先確認服務已啟動。'
        }
        $status = [int]$response.StatusCode
        if ($status -ge 300 -and $status -lt 400) {
            throw 'MiroFish 要求重新導向；助手已停止，沒有將授權傳往其他網址。'
        }
        if ($status -eq 409) {
            throw 'MiroFish 的模型服務或網址已在操作期間變更；助手已停止，請確認設定後再執行。'
        }
        if ($status -ne 200) {
            # Do not print a response body: an upstream failure may echo secrets.
            throw "MiroFish 未接受此操作（HTTP $status）；請在設定頁確認服務版本與設定。"
        }
        try {
            $document = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult() | ConvertFrom-Json
        } catch {
            throw 'MiroFish 回傳了無法辨識的設定資料。'
        }
        if ((Get-PropertyValue $document 'success') -ne $true) {
            throw 'MiroFish 沒有確認操作成功；請查看設定頁，授權資料未顯示於輸出。'
        }
        return (Get-PropertyValue $document 'data')
    } finally {
        if ($null -ne $response) { $response.Dispose() }
        if ($null -ne $request) { $request.Dispose() }
    }
}

$localBase = Assert-LocalMiroFishUrl $MiroFishBaseUrl
$dataDirectory = [IO.Path]::GetFullPath($RouterDataDirectory)
$machineIdPath = [IO.Path]::Combine($dataDirectory, 'machine-id')
$cliSecretPath = [IO.Path]::Combine($dataDirectory, 'auth', 'cli-secret')
$settingsUrl = "$localBase/api/settings/providers"

if (-not $PSCmdlet.ShouldProcess(
    "$settingsUrl（9Router 資料夾：$dataDirectory）",
    '讀取既有本機授權，僅儲存 MiroFish 的 9Router 餘額連線授權'
)) { return }

Add-Type -AssemblyName System.Net.Http
$handler = [System.Net.Http.HttpClientHandler]::new()
$handler.AllowAutoRedirect = $false
$handler.UseProxy = $false
$handler.UseCookies = $false
$client = [System.Net.Http.HttpClient]::new($handler)
$client.Timeout = [TimeSpan]::FromSeconds(20)
$client.MaxResponseContentBufferSize = 2MB
$hasher = $null
$materialBytes = $null
$digest = $null
$rawMachineId = $null
$cliSecret = $null
$cliToken = $null
$payload = $null

try {
    $before = Invoke-LocalSettingsRequest $client 'GET' $settingsUrl $localBase '' ''
    $config = Get-PropertyValue $before 'config'
    $routerOrigin = Assert-LocalRouterConfig $config
    $csrf = Get-PropertyValue $before 'csrf_token'
    if (-not ($csrf -is [string]) -or [string]::IsNullOrWhiteSpace($csrf) -or $csrf.Length -gt 4096) {
        throw 'MiroFish 尚未提供設定授權；請先更新並啟動支援供應商設定的後端。'
    }
    foreach ($credentialPath in @($machineIdPath, $cliSecretPath)) {
        if (-not [IO.File]::Exists($credentialPath)) {
            throw '找不到 9Router 已存在的本機授權檔。請確認資料夾正確並先啟動 9Router；助手不會建立或重設授權。'
        }
        if ([IO.FileInfo]::new($credentialPath).Length -gt 4096) {
            throw '9Router 本機授權檔大小不符合預期；助手已停止。'
        }
    }
    try {
        $rawMachineId = [IO.File]::ReadAllText($machineIdPath, [Text.Encoding]::UTF8).Trim()
        $cliSecret = [IO.File]::ReadAllText($cliSecretPath, [Text.Encoding]::UTF8).Trim()
    } catch {
        throw '無法讀取 9Router 已存在的本機授權檔；請用有權限的 Windows 帳戶執行。'
    }
    if ([string]::IsNullOrWhiteSpace($rawMachineId) -or $cliSecret -notmatch '^[a-fA-F0-9]{64}$') {
        throw '9Router 本機授權檔格式不符合預期；助手已停止。'
    }
    # Same algorithm as 9Router src/shared/utils/machineId.js:49-53.
    $hasher = [Security.Cryptography.SHA256]::Create()
    $materialBytes = [Text.Encoding]::UTF8.GetBytes($rawMachineId + '9r-cli-auth' + $cliSecret)
    $digest = $hasher.ComputeHash($materialBytes)
    $cliToken = ([BitConverter]::ToString($digest).Replace('-', '').ToLowerInvariant()).Substring(0, 16)

    # Partial update: do not send or replace the primary provider, URL, model,
    # model API key, or the user's selected balance account.
    $payload = @{
        balance_api_key = $cliToken
        expected_base_url = (Get-PropertyValue $config 'base_url')
        expected_provider = 'ninerouter'
    } | ConvertTo-Json -Compress
    $null = Invoke-LocalSettingsRequest $client 'PUT' $settingsUrl $localBase $csrf $payload
    $after = Invoke-LocalSettingsRequest $client 'GET' $settingsUrl $localBase '' ''
    $afterConfig = Get-PropertyValue $after 'config'
    $afterOrigin = Assert-LocalRouterConfig $afterConfig
    if ($afterOrigin -ne $routerOrigin -or
        (Get-PropertyValue $afterConfig 'has_balance_api_key') -ne $true) {
        throw '尚未確認餘額授權已保存。請開啟 MiroFish 設定頁查看；助手不會自動重送。'
    }
    Write-Host '9Router 餘額授權已儲存至本機 MiroFish。'
    Write-Host '請回到設定頁，載入 OpenCode 帳戶並選擇要查看的帳戶。'
    Write-Host '模型、網址與模型金鑰未由此助手改寫；OpenCode 錢包顯示的是 9Router 最後取得的讀值。'
} finally {
    if ($null -ne $materialBytes) { [Array]::Clear($materialBytes, 0, $materialBytes.Length) }
    if ($null -ne $digest) { [Array]::Clear($digest, 0, $digest.Length) }
    if ($null -ne $hasher) { $hasher.Dispose() }
    $payload = $null
    $cliToken = $null
    $cliSecret = $null
    $rawMachineId = $null
    $client.Dispose()
    $handler.Dispose()
}
