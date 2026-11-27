# Instalacion y verificacion completa de la plataforma (ejecutar una vez).
# Uso: powershell -ExecutionPolicy Bypass -File .\instalar.ps1
. (Join-Path $PSScriptRoot 'scripts\comun.ps1')
Set-Location $Raiz
$Log = Join-Path $DirLogs 'instalacion.log'
Set-Content -Path $Log -Value ('Instalacion iniciada ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')) -Encoding UTF8

function Buscar-PythonBase {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        foreach ($v in '3.12', '3.13', '3.11', '3.10', '3.14') {
            $previo = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
            $r = & py "-$v" -c "import sys; print(sys.executable)" 2>$null
            $ErrorActionPreference = $previo
            if ($LASTEXITCODE -eq 0 -and $r) { return ([string]$r).Trim() }
        }
    }
    $c = Get-Command python -ErrorAction SilentlyContinue
    if ($c -and $c.Source -notlike '*WindowsApps*') { return $c.Source }
    return $null
}

try {
    Escribir-Log "Carpeta del proyecto: $Raiz" $Log
    if (-not (Test-Path $PyVenv)) {
        $base = Buscar-PythonBase
        if (-not $base) { throw 'No se encontro Python 3.10 o superior. Instale Python desde python.org y vuelva a ejecutar.' }
        Escribir-Log "Python base: $base" $Log
        & $base -m venv (Join-Path $Raiz '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno virtual.' }
    }
    Ejecutar-Python 'Version de Python' @('--version') $Log
    Ejecutar-Python 'Actualizar pip' @('-m', 'pip', 'install', '--upgrade', 'pip', '--disable-pip-version-check') $Log
    Ejecutar-Python 'Instalar dependencias' @('-m', 'pip', 'install', '-r', 'requirements.txt', '--disable-pip-version-check') $Log

    if (-not (Test-Path (Join-Path $Raiz '.env'))) {
        Copy-Item (Join-Path $Raiz '.env.example') (Join-Path $Raiz '.env')
        $clave = & $PyVenv -c "import secrets; print(secrets.token_urlsafe(50))"
        Fijar-Env 'DJANGO_SECRET_KEY' ([string]$clave).Trim()
        Remove-Variable clave
        Escribir-Log 'Archivo .env creado con una clave secreta nueva (no se muestra).' $Log
    }

    Ejecutar-Python 'Verificar integridad de insumos' @('manage.py', 'verificar_integridad') $Log
    Ejecutar-Python 'Preparar Plotly.js local' @('manage.py', 'preparar_estaticos') $Log
    Ejecutar-Python 'Migraciones' @('manage.py', 'migrate', '--noinput') $Log
    Ejecutar-Python 'Validar e importar datos' @('manage.py', 'cargar_datos') $Log
    Ejecutar-Python 'Recolectar archivos estaticos' @('manage.py', 'collectstatic', '--noinput') $Log
    Ejecutar-Python 'Revision de Django' @('manage.py', 'check') $Log
    Ejecutar-Python 'Revision de despliegue' @('manage.py', 'check', '--deploy') $Log
    Ejecutar-Python 'Suite de pruebas' @('manage.py', 'test', 'agro', '--verbosity', '2') $Log
    Ejecutar-Python 'Verificar integridad final' @('manage.py', 'verificar_integridad') $Log

    $lock = & $PyVenv -m pip freeze --disable-pip-version-check
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines((Join-Path $Raiz 'requirements.lock.txt'), [string[]]$lock, $utf8)

    Get-ChildItem (Join-Path $Raiz 'data\raw') -File | ForEach-Object { $_.IsReadOnly = $true }
    Escribir-Log 'Copias en data\raw marcadas como solo lectura.' $Log
    Escribir-Log 'INSTALACION COMPLETADA' $Log
} catch {
    Escribir-Log ("ERROR: " + $_.Exception.Message) $Log
    exit 1
}
