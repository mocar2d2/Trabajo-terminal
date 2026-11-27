# Detiene unicamente los procesos de Waitress y ngrok iniciados por este proyecto (modo local o publico).
# Uso (desde la carpeta del proyecto; desde otra carpeta, indique la ruta completa del script):
#   powershell -ExecutionPolicy Bypass -File .\detener_plataforma.ps1
. (Join-Path $PSScriptRoot 'scripts\comun.ps1')
$Log = Join-Path $DirLogs 'plataforma.log'

foreach ($nombre in 'waitress', 'ngrok') {
    $estado = Obtener-Estado $nombre
    $archivo = Join-Path $DirRun "$nombre.json"
    if ($estado) {
        $previo = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
        & taskkill.exe /PID $estado.pid /T /F 2>&1 | Out-Null
        $ErrorActionPreference = $previo
        Escribir-Log "$nombre detenido (PID $($estado.pid))." $Log
    } else {
        Escribir-Log "$nombre no estaba activo para este proyecto." $Log
    }
    if (Test-Path $archivo) { Remove-Item $archivo -Force }
}
$u = Join-Path $DirRun 'url.txt'
if (Test-Path $u) { Remove-Item $u -Force }
Escribir-Log 'Sesion de la plataforma terminada.' $Log
