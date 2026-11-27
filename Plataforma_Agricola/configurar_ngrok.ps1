# Configura el authtoken de ngrok leyendolo del portapapeles sin mostrarlo.
# Uso: powershell -ExecutionPolicy Bypass -File .\configurar_ngrok.ps1
. (Join-Path $PSScriptRoot 'scripts\comun.ps1')
$Log = Join-Path $DirLogs 'ngrok_configuracion.log'

try {
    $ngrok = Buscar-Ngrok
    if (-not $ngrok) {
        $winget = Get-Command winget -ErrorAction SilentlyContinue
        if (-not $winget) { throw 'ngrok no esta instalado y winget no esta disponible. Instale ngrok desde https://ngrok.com/download.' }
        Escribir-Log 'Instalando ngrok con winget (acepte los terminos si se solicitan)...' $Log
        & winget install --id Ngrok.Ngrok -e --source winget
        $ngrok = Buscar-Ngrok
        if (-not $ngrok) { throw 'No se encontro ngrok despues de la instalacion. Cierre y abra PowerShell y ejecute de nuevo este script.' }
    }
    Escribir-Log "ngrok: $ngrok" $Log
    $previo = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    $version = & $ngrok version 2>&1
    $ErrorActionPreference = $previo
    Escribir-Log "Version: $version" $Log

    Write-Host ''
    Write-Host 'Copie ahora el nuevo authtoken de ngrok al portapapeles y presione Enter cuando este listo.'
    [void](Read-Host)

    $tmp = Get-Clipboard -Raw
    if ($tmp) { $tmp = $tmp.Trim() }
    if (-not $tmp -or $tmp -notmatch '^[A-Za-z0-9_\-]{20,}$') {
        Remove-Variable tmp -ErrorAction SilentlyContinue
        throw 'El portapapeles no contiene un authtoken con formato valido.'
    }
    $previo = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & $ngrok config add-authtoken $tmp *> $null
    $codigo = $LASTEXITCODE
    $ErrorActionPreference = $previo
    Remove-Variable tmp -ErrorAction SilentlyContinue
    [System.GC]::Collect()
    if ($codigo -ne 0) { throw 'ngrok no acepto el authtoken.' }

    $previo = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    $chk = & $ngrok config check 2>&1
    $ErrorActionPreference = $previo
    if ($LASTEXITCODE -ne 0) { throw 'La configuracion de ngrok no es valida.' }
    try { Set-Clipboard -Value ' ' } catch {}
    Escribir-Log 'ngrok autenticado. El portapapeles fue limpiado.' $Log
} catch {
    Escribir-Log ('ERROR: ' + $_.Exception.Message) $Log
    exit 1
}
