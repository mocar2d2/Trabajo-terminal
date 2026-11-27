# Ejecuta la suite de pruebas con limite de tiempo, sin reinstalar ni recargar datos.
# Uso:
#   powershell -ExecutionPolicy Bypass -File .\probar.ps1
#   powershell -ExecutionPolicy Bypass -File .\probar.ps1 -Pruebas agro.tests.test_plataforma.ValidacionTests -LimiteSeg 180
# Sin parametros: suite completa (limite 900 s), check, check --deploy e integridad.
# Si se agota el limite se imprime la pila de todos los hilos. Registro: logs\pruebas.log
param([string[]]$Pruebas = @(), [int]$LimiteSeg = 0)
. (Join-Path $PSScriptRoot 'scripts\comun.ps1')
Set-Location $Raiz
$Log = Join-Path $DirLogs 'pruebas.log'
Set-Content -Path $Log -Value ('Pruebas ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')) -Encoding UTF8

function Ejecutar-ConLimite([string]$Titulo, [string[]]$Argumentos, [int]$Limite) {
    Escribir-Log "== $Titulo (limite $Limite s)" $Log
    $out = Join-Path $DirLogs 'pruebas.out.tmp'
    $err = Join-Path $DirLogs 'pruebas.err.tmp'
    $env:PYTHONUNBUFFERED = '1'
    $env:PRUEBAS_LIMITE_SEG = [string]($Limite - 10)
    $p = Start-Process -FilePath $PyVenv -ArgumentList $Argumentos -WorkingDirectory $Raiz -NoNewWindow -PassThru `
        -RedirectStandardOutput $out -RedirectStandardError $err
    $null = $p.Handle
    $terminado = $p.WaitForExit($Limite * 1000)
    if (-not $terminado) {
        & taskkill.exe /PID $p.Id /T /F 2>&1 | Out-Null
        Escribir-Log "TIEMPO AGOTADO: $Titulo" $Log
    }
    Remove-Item Env:\PRUEBAS_LIMITE_SEG -ErrorAction SilentlyContinue
    foreach ($f in $out, $err) {
        if (Test-Path $f) {
            Get-Content $f -Encoding UTF8 | ForEach-Object { Write-Host $_; Add-Content -Path $Log -Value $_ -Encoding UTF8 }
            Remove-Item $f -Force
        }
    }
    $codigo = if ($terminado) { $p.ExitCode } else { -1 }
    Escribir-Log "Resultado de '$Titulo': codigo $codigo" $Log
    return ($codigo -eq 0)
}

$ok = $true
if ($Pruebas.Count -gt 0) {
    $lim = if ($LimiteSeg -gt 0) { $LimiteSeg } else { 300 }
    $ok = Ejecutar-ConLimite 'Pruebas seleccionadas' (@('manage.py', 'test') + $Pruebas + @('--verbosity', '2')) $lim
} else {
    $ok = Ejecutar-ConLimite 'Suite completa' @('manage.py', 'test', 'agro', '--verbosity', '2') 900
    if ($ok) {
        $a = Ejecutar-ConLimite 'check' @('manage.py', 'check') 120
        $b = Ejecutar-ConLimite 'check --deploy' @('manage.py', 'check', '--deploy') 120
        $c = Ejecutar-ConLimite 'Integridad' @('manage.py', 'verificar_integridad') 120
        $ok = $a -and $c
    }
}
if ($ok) { Escribir-Log 'PRUEBAS COMPLETADAS SIN FALLAS' $Log; exit 0 }
Escribir-Log 'PRUEBAS CON FALLAS O TIEMPO AGOTADO (ver logs\pruebas.log)' $Log
exit 1
