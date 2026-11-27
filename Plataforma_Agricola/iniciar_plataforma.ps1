# Inicia la plataforma.
# Uso (desde la carpeta del proyecto; desde otra carpeta, indique la ruta completa del script):
#   powershell -ExecutionPolicy Bypass -File .\iniciar_plataforma.ps1          # publica con ngrok (requiere Internet)
#   powershell -ExecutionPolicy Bypass -File .\iniciar_plataforma.ps1 -Local   # solo en este equipo, sin Internet ni ngrok
param([switch]$Local)
. (Join-Path $PSScriptRoot 'scripts\comun.ps1')
Set-Location $Raiz
$Log = Join-Path $DirLogs 'plataforma.log'
$Modo = if ($Local) { 'local' } else { 'publico' }
$script:ModoLocal = [bool]$Local

function Iniciar-Waitress([int]$Puerto, [string]$ModoServidor) {
    # El modo se pasa al proceso de Waitress como variable de entorno (tiene prioridad sobre .env).
    $env:PLATAFORMA_MODO = $ModoServidor
    try {
        $pw = Start-Process -FilePath $PyVenv -ArgumentList @('servidor.py', '--port', "$Puerto") -WorkingDirectory $Raiz `
            -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $DirLogs 'waitress.out.log') -RedirectStandardError (Join-Path $DirLogs 'waitress.err.log')
    } finally {
        Remove-Item Env:\PLATAFORMA_MODO -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 500
    Guardar-Estado 'waitress' $pw $ModoServidor
    $urlLocal = "http://127.0.0.1:$Puerto"
    $ok = $false
    for ($i = 0; $i -lt 60 -and -not $ok; $i++) {
        Start-Sleep -Milliseconds 500
        $r = Solicitud-Http "$urlLocal/salud/"
        $ok = ($r.Codigo -eq 200)
    }
    if (-not $ok) { throw "Waitress no respondio en $urlLocal. Revise logs\waitress.err.log." }
    Escribir-Log "Waitress responde en $urlLocal (modo $ModoServidor)" $Log
    return $urlLocal
}

try {
    Escribir-Log "--- Inicio de sesion de la plataforma (modo $Modo) ---" $Log
    if (-not (Test-Path $PyVenv)) { throw 'No existe .venv. Ejecute primero instalar.ps1.' }
    if (-not (Test-Path (Join-Path $Raiz '.env'))) { throw 'No existe .env. Ejecute primero instalar.ps1.' }
    $previo = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & $PyVenv -c "import django, waitress, whitenoise, pandas, folium, plotly, statsmodels" 2>$null
    $ErrorActionPreference = $previo
    if ($LASTEXITCODE -ne 0) { throw 'Faltan dependencias. Ejecute instalar.ps1.' }

    $envv = Leer-Env
    $Puerto = 8000
    if ($envv['PUERTO']) { $Puerto = [int]$envv['PUERTO'] }
    $w = Obtener-Estado 'waitress'; $n = Obtener-Estado 'ngrok'

    if ($Local) {
        # ----------------------------------------------------------- modo local
        if ($w) {
            if ($w.modo -eq 'local') {
                Escribir-Log "La plataforma ya esta activa en modo local: http://127.0.0.1:$Puerto/" $Log
                exit 0
            }
            throw ('La plataforma esta activa en modo publico (ngrok). Para usarla sin Internet, detengala con ' +
                   'detener_plataforma.ps1 y vuelva a ejecutar este script con -Local.')
        }
        if ($n) { & (Join-Path $Raiz 'detener_plataforma.ps1') | Out-Null }
    } else {
        # --------------------------------------------------------- modo publico
        $ngrok = Buscar-Ngrok
        if (-not $ngrok) { throw 'No se encontro ngrok. Ejecute configurar_ngrok.ps1.' }
        if ($w -and $n -and $w.modo -ne 'local') {
            $url = Url-Publica-Ngrok
            Escribir-Log "La plataforma ya esta activa. URL: $url" $Log
            exit 0
        }
        if ($w -or $n) { & (Join-Path $Raiz 'detener_plataforma.ps1') | Out-Null }
    }

    $ocupado = Get-NetTCPConnection -LocalPort $Puerto -State Listen -ErrorAction SilentlyContinue
    if ($ocupado) { throw "El puerto $Puerto ya esta en uso por otro proceso. Cambie PUERTO en .env." }

    # Preparacion sin conexion: no instala, no descarga, no recalcula datos ni modelos.
    Ejecutar-Python 'Migraciones pendientes' @('manage.py', 'migrate', '--noinput') $Log
    Ejecutar-Python 'Archivos estaticos' @('manage.py', 'preparar_estaticos') $Log
    Ejecutar-Python 'collectstatic' @('manage.py', 'collectstatic', '--noinput', '-v', '0') $Log
    Ejecutar-Python 'Revision rapida' @('manage.py', 'check') $Log
    Ejecutar-Python 'Integridad de insumos' @('manage.py', 'verificar_integridad') $Log

    if ($Local) {
        $urlLocal = Iniciar-Waitress $Puerto 'local'
        Write-Host ''
        Write-Host '=============================================================='
        Write-Host "  Abra en el navegador de este equipo:  $urlLocal/"
        Write-Host '  Modo local: no usa Internet ni ngrok; solo es accesible desde este equipo.'
        Write-Host ('  Para detener: powershell -ExecutionPolicy Bypass -File "' + (Join-Path $Raiz 'detener_plataforma.ps1') + '"')
        Write-Host '=============================================================='
        exit 0
    }

    # 1. ngrok primero, para conocer el dominio real y autorizarlo en Django.
    # Si ya hay un dominio registrado se solicita exactamente ese dominio; si ngrok
    # no lo concede, el inicio se detiene sin cambiar la configuracion.
    $dominioPrevio = $envv['NGROK_DOMAIN']
    $argsNgrok = @('http', "127.0.0.1:$Puerto", '--log', 'false')
    if ($dominioPrevio) { $argsNgrok += @('--url', "https://$dominioPrevio") }
    $pn = Start-Process -FilePath $ngrok -ArgumentList $argsNgrok -WindowStyle Hidden -PassThru
    Start-Sleep -Milliseconds 500
    Guardar-Estado 'ngrok' $pn
    $url = $null
    for ($i = 0; $i -lt 40 -and -not $url; $i++) { Start-Sleep -Milliseconds 500; $url = Url-Publica-Ngrok }
    if (-not $url) {
        & taskkill.exe /PID $pn.Id /T /F 2>&1 | Out-Null
        throw ('ngrok no publico el tunel (sin Internet o authtoken no configurado). ' +
               'Sin conexion, use: iniciar_plataforma.ps1 -Local')
    }
    $dominio = ([Uri]$url).Host
    if ($dominioPrevio -and $dominioPrevio -ne $dominio) {
        & taskkill.exe /PID $pn.Id /T /F 2>&1 | Out-Null
        throw "ngrok asigno $dominio en lugar del dominio configurado $dominioPrevio. No se modifico .env."
    }
    if ($envv['NGROK_DOMAIN'] -ne $dominio) {
        Fijar-Env 'NGROK_DOMAIN' $dominio
        Escribir-Log "Dominio de ngrok registrado en .env: $dominio" $Log
    }

    # 2. Waitress.
    $urlLocal = Iniciar-Waitress $Puerto 'publico'

    $r = Solicitud-Http "$url/salud/"
    if ($r.Codigo -ne 200) { throw "La URL publica no respondio correctamente (codigo $($r.Codigo))." }
    Set-Content -Path (Join-Path $DirRun 'url.txt') -Value $url -Encoding UTF8
    Escribir-Log "URL publica verificada: $url" $Log
    Write-Host ''
    Write-Host '=============================================================='
    Write-Host "  Comparta esta URL:  $url"
    Write-Host ('  Para detener: powershell -ExecutionPolicy Bypass -File "' + (Join-Path $Raiz 'detener_plataforma.ps1') + '"')
    Write-Host '=============================================================='
} catch {
    Escribir-Log ('ERROR: ' + $_.Exception.Message) $Log
    exit 1
}
