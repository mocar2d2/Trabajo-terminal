# Funciones comunes para los scripts de operacion (PowerShell 5.1+).
# Solo registra informacion operativa; nunca imprime secretos.

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Raiz = Split-Path -Parent $PSScriptRoot
$PyVenv = Join-Path $Raiz '.venv\Scripts\python.exe'
$DirLogs = Join-Path $Raiz 'logs'
$DirRun = Join-Path $Raiz 'run'
New-Item -ItemType Directory -Force -Path $DirLogs, $DirRun | Out-Null

function Escribir-Log {
    param([string]$Texto, [string]$Archivo)
    $linea = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Texto
    Write-Host $Texto
    if ($Archivo) { Add-Content -Path $Archivo -Value $linea -Encoding UTF8 }
}

function Ejecutar-Python {
    # Ejecuta python del entorno virtual; registra salida y falla si el codigo no es 0.
    param([string]$Titulo, [string[]]$Argumentos, [string]$Archivo)
    Escribir-Log "== $Titulo" $Archivo
    $previo = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $PyVenv @Argumentos 2>&1 | ForEach-Object {
        if ($_ -is [System.Management.Automation.ErrorRecord]) { $l = [string]$_.TargetObject } else { $l = "$_" }
        Write-Host $l
        if ($Archivo) { Add-Content -Path $Archivo -Value $l -Encoding UTF8 }
    }
    $codigo = $LASTEXITCODE
    $ErrorActionPreference = $previo
    if ($codigo -ne 0) { throw "Fallo: $Titulo (codigo $codigo)" }
}

function Leer-Env {
    $valores = @{}
    $ruta = Join-Path $Raiz '.env'
    if (Test-Path $ruta) {
        foreach ($l in Get-Content $ruta -Encoding UTF8) {
            if ($l -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') { $valores[$matches[1]] = $matches[2].Trim() }
        }
    }
    return $valores
}

function Fijar-Env {
    param([string]$Clave, [string]$Valor)
    $ruta = Join-Path $Raiz '.env'
    $lineas = @()
    if (Test-Path $ruta) { $lineas = @(Get-Content $ruta -Encoding UTF8) }
    $encontrada = $false
    $nuevas = foreach ($l in $lineas) {
        if ($l -match ('^\s*' + [regex]::Escape($Clave) + '\s*=')) { $encontrada = $true; "$Clave=$Valor" } else { $l }
    }
    if (-not $encontrada) { $nuevas = @($nuevas) + "$Clave=$Valor" }
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($ruta, [string[]]$nuevas, $utf8)
}

function Buscar-Ngrok {
    $c = Get-Command ngrok -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $candidatos = @(
        (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\ngrok.exe'),
        (Join-Path $env:LOCALAPPDATA 'ngrok\ngrok.exe'),
        (Join-Path $env:ProgramFiles 'ngrok\ngrok.exe'),
        (Join-Path $env:USERPROFILE 'ngrok\ngrok.exe')
    )
    foreach ($p in $candidatos) { if ($p -and (Test-Path $p)) { return $p } }
    $pkg = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
    if (Test-Path $pkg) {
        $e = Get-ChildItem -Path $pkg -Filter ngrok.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($e) { return $e.FullName }
    }
    return $null
}

function Obtener-Estado {
    # Devuelve @{Pid; Inicio} del proceso registrado o $null si no esta activo.
    param([string]$Nombre)
    $ruta = Join-Path $DirRun "$Nombre.json"
    if (-not (Test-Path $ruta)) { return $null }
    $d = Get-Content $ruta -Raw | ConvertFrom-Json
    $p = Get-Process -Id $d.pid -ErrorAction SilentlyContinue
    if (-not $p) { return $null }
    try { if ($p.StartTime.ToString('o') -ne $d.inicio) { return $null } } catch { return $null }
    return $d
}

function Guardar-Estado {
    # Modo: 'publico' (con ngrok) o 'local' (solo este equipo, sin Internet).
    param([string]$Nombre, $Proceso, [string]$Modo = '')
    $p = Get-Process -Id $Proceso.Id
    $d = @{ pid = $p.Id; inicio = $p.StartTime.ToString('o') }
    if ($Modo) { $d['modo'] = $Modo }
    $d | ConvertTo-Json | Set-Content -Path (Join-Path $DirRun "$Nombre.json") -Encoding UTF8
}

function Solicitud-Http {
    # Devuelve @{Codigo; Contenido}. No lanza excepcion por codigos 4xx/5xx.
    param([string]$Url, [string]$Metodo = 'GET', $Cuerpo = $null, $Sesion = $null, [hashtable]$Encabezados = @{})
    $Encabezados['ngrok-skip-browser-warning'] = '1'
    # Modo publico: las solicitudes locales declaran HTTPS como lo hace ngrok (Waitress
    # solo acepta este encabezado desde 127.0.0.1); asi no aplica la redireccion.
    # En modo local ($script:ModoLocal) se usa HTTP sin encabezados de proxy, como un navegador.
    if ($Url.StartsWith('http://127.0.0.1') -and -not $script:ModoLocal) { $Encabezados['X-Forwarded-Proto'] = 'https' }
    $params = @{ Uri = $Url; Method = $Metodo; UseBasicParsing = $true; Headers = $Encabezados; TimeoutSec = 30 }
    if ($Cuerpo) { $params['Body'] = $Cuerpo }
    if ($Sesion) { $params['WebSession'] = $Sesion }
    try {
        $r = Invoke-WebRequest @params
        return @{ Codigo = [int]$r.StatusCode; Contenido = $r.Content }
    } catch {
        $resp = $_.Exception.Response
        if ($resp) { return @{ Codigo = [int]$resp.StatusCode; Contenido = '' } }
        return @{ Codigo = 0; Contenido = '' }
    }
}

function Url-Publica-Ngrok {
    try {
        $t = Invoke-RestMethod -Uri 'http://127.0.0.1:4040/api/tunnels' -TimeoutSec 5
        $https = $t.tunnels | Where-Object { $_.public_url -like 'https://*' } | Select-Object -First 1
        if ($https) { return $https.public_url }
    } catch {}
    return $null
}
