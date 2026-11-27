# Verifica la plataforma activa.
# Uso (desde la carpeta del proyecto; desde otra carpeta, indique la ruta completa del script):
#   powershell -ExecutionPolicy Bypass -File .\verificar_plataforma.ps1          # modo publico (local + URL de ngrok)
#   powershell -ExecutionPolicy Bypass -File .\verificar_plataforma.ps1 -Local   # modo local (sin Internet)
param([switch]$Local)
. (Join-Path $PSScriptRoot 'scripts\comun.ps1')
Set-Location $Raiz
$script:ModoLocal = [bool]$Local
$Log = Join-Path $DirLogs 'verificacion.log'
Set-Content -Path $Log -Value ('Verificacion ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + $(if ($Local) { ' (modo local)' } else { ' (modo publico)' })) -Encoding UTF8
$fallas = 0
function Resultado([string]$Nombre, [bool]$Ok, [string]$Detalle = '') {
    $estado = if ($Ok) { 'OK   ' } else { 'FALLA' }
    if (-not $Ok) { $script:fallas++ }
    Escribir-Log ("[{0}] {1} {2}" -f $estado, $Nombre, $Detalle) $Log
}

$envv = Leer-Env
$Puerto = 8000
if ($envv['PUERTO']) { $Puerto = [int]$envv['PUERTO'] }
$urlLocal = "http://127.0.0.1:$Puerto"
$paginas = @('/', '/precios/', '/clima/', '/prediccion/', '/analisis/', '/sequia/', '/comparar/', '/metodologia/')

# Comprobaciones de contenido y seguridad sobre una base (local o publica).
function Verificar-Sitio([string]$Base, [string]$Etiqueta) {
    foreach ($p in $paginas) {
        $r = Solicitud-Http "$Base$p"
        Resultado "$Etiqueta $p" ($r.Codigo -eq 200) "codigo $($r.Codigo)"
    }
    $inicio = Solicitud-Http "$Base/"
    $clima = Solicitud-Http "$Base/clima/"
    $recursos = @(
        @{ Nombre = 'CSS'; Html = $inicio; Patron = 'href="(/static/agro/css/[^"]+)"' },
        @{ Nombre = 'Plotly.js'; Html = $inicio; Patron = 'src="(/static/vendor/plotly[^"]+)"' },
        @{ Nombre = 'Leaflet.js'; Html = $clima; Patron = 'src="(/static/agro/vendor/leaflet/leaflet[^"]+\.js)"' },
        @{ Nombre = 'Leaflet.css'; Html = $clima; Patron = 'href="(/static/agro/vendor/leaflet/leaflet[^"]+\.css)"' },
        @{ Nombre = 'Limites estatales'; Html = $clima; Patron = 'data-base-geo="(/static/agro/geo/[^"]+)"' }
    )
    foreach ($x in $recursos) {
        $m = [regex]::Match($x.Html.Contenido, $x.Patron)
        if ($m.Success) {
            $r = Solicitud-Http ("$Base" + $m.Groups[1].Value)
            Resultado "$Etiqueta estatico $($x.Nombre)" ($r.Codigo -eq 200) $m.Groups[1].Value
        } else { Resultado "$Etiqueta estatico $($x.Nombre)" $false 'no se encontro el enlace' }
    }

    # Formulario POST con CSRF.
    $ses = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $g = Solicitud-Http "$Base/comparar/" -Sesion $ses
    $tok = [regex]::Match($g.Contenido, 'name="csrfmiddlewaretoken" value="([^"]+)"').Groups[1].Value
    $cuerpo = @{ csrfmiddlewaretoken = $tok; producto = 'Haba'; estado = 'Puebla'; variable = 'PRECIP' }
    $r = Solicitud-Http "$Base/comparar/" -Metodo 'POST' -Cuerpo $cuerpo -Sesion $ses -Encabezados @{ Referer = "$Base/comparar/"; Origin = $Base }
    Resultado "$Etiqueta POST con CSRF" (($r.Codigo -eq 200) -and ($r.Contenido -match 'Semanas comparadas')) "codigo $($r.Codigo)"
    $r = Solicitud-Http "$Base/comparar/" -Metodo 'POST' -Cuerpo @{ producto = 'Haba' }
    Resultado "$Etiqueta POST sin token rechazado" ($r.Codigo -eq 403) "codigo $($r.Codigo)"

    foreach ($ruta in '/.env', '/data/raw/Precios_Historicos_SNIIM_Continuo.csv', '/manage.py', '/static/../.env') {
        $r = Solicitud-Http "$Base$ruta"
        Resultado "$Etiqueta no expuesto $ruta" ($r.Codigo -eq 404 -or $r.Codigo -eq 400) "codigo $($r.Codigo)"
    }
    $r = Solicitud-Http "$Base/no-existe/"
    Resultado "$Etiqueta error 404 sin detalles" (($r.Codigo -eq 404) -and ($r.Contenido -notmatch 'Traceback')) "codigo $($r.Codigo)"
    Resultado "$Etiqueta sin secretos visibles" (-not ($inicio.Contenido -match 'SECRET_KEY|authtoken|DJANGO_')) ''
    return $clima
}

# Cualquier error inesperado se registra como falla: el script termina con codigo distinto de cero.
try {
    $w = Obtener-Estado 'waitress'
    Resultado 'Waitress activo' ([bool]$w)
    $modoActivo = if ($w -and $w.modo) { $w.modo } else { 'publico' }

    if ($Local) {
        Resultado 'Waitress en modo local' ($modoActivo -eq 'local') "modo $modoActivo"
        $clima = Verificar-Sitio $urlLocal 'Local'
        # Sin recursos externos: ningun script, hoja de estilo, imagen ni mosaico fuera del equipo.
        $externos = 0
        foreach ($p in $paginas) {
            $h = (Solicitud-Http "$urlLocal$p").Contenido
            $externos += [regex]::Matches($h, '<(script|link|img|iframe)[^>]+(src|href)="(https?:)?//').Count
            $externos += [regex]::Matches($h, 'tileLayer\(\s*"https?://').Count
        }
        Resultado 'Sin recursos externos en las paginas' ($externos -eq 0) "$externos referencias"
        $r = Solicitud-Http "$urlLocal/"
        Resultado 'HTTP local sin redireccion a HTTPS' ($r.Codigo -eq 200) "codigo $($r.Codigo)"
    } else {
        Resultado 'ngrok activo' ([bool](Obtener-Estado 'ngrok'))
        $url = Url-Publica-Ngrok
        Resultado 'URL publica HTTPS' ([bool]$url -and $url.StartsWith('https://')) "$url"
        $r = Solicitud-Http "$urlLocal/"
        Resultado 'Respuesta local /' ($r.Codigo -eq 200) "codigo $($r.Codigo)"
        if ($url) { [void](Verificar-Sitio $url 'Publica') }
    }

    # Host no permitido (solo local).
    try {
        $req = [System.Net.HttpWebRequest]::Create("$urlLocal/")
        $req.Host = 'host-no-permitido.example'
        $req.Timeout = 10000
        try { $resp = $req.GetResponse(); $cod = [int]$resp.StatusCode; $resp.Close() }
        catch [System.Net.WebException] { $cod = [int]$_.Exception.Response.StatusCode }
        Resultado 'Host no permitido rechazado' ($cod -eq 400) "codigo $cod"
    } catch { Resultado 'Host no permitido rechazado' $false $_.Exception.Message }

    $previo = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    $env:PLATAFORMA_MODO = $modoActivo
    $dbg = & $PyVenv -c "import os, django; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings'); django.setup(); from django.conf import settings as s; print(s.DEBUG, ','.join(s.ALLOWED_HOSTS), ','.join(s.CSRF_TRUSTED_ORIGINS))" 2>$null
    Remove-Item Env:\PLATAFORMA_MODO -ErrorAction SilentlyContinue
    $ErrorActionPreference = $previo
    $partes = ([string]$dbg).Trim().Split(' ')
    Resultado 'DEBUG=False' ($partes[0] -eq 'False') ''
    Resultado 'ALLOWED_HOSTS sin comodin' (-not ([string]$dbg).Contains('*')) ''
    if (-not $Local -and $url) {
        $dom = ([Uri]$url).Host
        Resultado 'Dominio ngrok en ALLOWED_HOSTS' (([string]$dbg).Contains($dom)) $dom
        Resultado 'Origen ngrok en CSRF_TRUSTED_ORIGINS' (([string]$dbg).Contains("https://$dom")) ''
    }
} catch {
    Resultado 'Error inesperado de la verificacion' $false $_.Exception.Message
}

if ($fallas -eq 0) { Escribir-Log 'VERIFICACION COMPLETA: sin fallas.' $Log; exit 0 }
Escribir-Log "VERIFICACION CON $fallas FALLA(S)." $Log
exit 1
