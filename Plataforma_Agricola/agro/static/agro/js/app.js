/* Comportamiento del sitio: menú, gráficas Plotly, mapas Leaflet e indicadores de carga. */
(function () {
  "use strict";
  document.documentElement.classList.add("js");

  function debounce(fn, ms) {
    var t;
    return function () {
      var args = arguments, ctx = this;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(ctx, args); }, ms);
    };
  }

  /* --------------------------------------------------------------- Mapas */
  function mapas() {
    var lista = [];
    document.querySelectorAll(".folium-map").forEach(function (el) {
      var m = window[el.id];
      if (m && typeof m.invalidateSize === "function") { lista.push(m); }
    });
    return lista;
  }
  // Leaflet calcula el tamaño del contenedor al crearse; tras cualquier cambio
  // de dimensiones se debe recalcular para no dejar áreas grises.
  // Nombres accesibles en español para los controles de acercamiento de Leaflet.
  function traducirControlesMapa() {
    [[".leaflet-control-zoom-in", "Acercar el mapa"], [".leaflet-control-zoom-out", "Alejar el mapa"]].forEach(function (par) {
      document.querySelectorAll(par[0]).forEach(function (b) {
        b.setAttribute("title", par[1]);
        b.setAttribute("aria-label", par[1]);
      });
    });
  }
  traducirControlesMapa();

  // Vista de la seleccion (limites o centro) calculada en el servidor con los
  // puntos filtrados; se vuelve a aplicar tras recalcular el tamaño mientras el
  // usuario no haya desplazado ni acercado el mapa.
  function aplicarVista(m) {
    var v = m._vistaSeleccion;
    if (!v) { return; }
    m._ajusteProgramatico = true;
    try {
      if (v.tipo === "limites") {
        m.fitBounds(v.limites, { padding: v.padding, maxZoom: v.zoomMax, animate: false });
      } else {
        m.setView(v.centro, v.zoom, { animate: false });
      }
    } finally {
      m._ajusteProgramatico = false;
    }
  }

  // Base geográfica local (límites estatales incluidos en el proyecto). Se dibuja en
  // ambos modos: sin Internet es el fondo del mapa y con OpenStreetMap se superpone
  // solo el contorno. No hace solicitudes externas.
  var geoCargado = {};
  function cargarGeo(url) {
    if (!geoCargado[url]) {
      geoCargado[url] = window.fetch(url, { credentials: "same-origin" }).then(function (r) {
        if (!r.ok) { throw new Error("HTTP " + r.status); }
        return r.json();
      });
    }
    return geoCargado[url];
  }
  function agregarBase(m) {
    var lienzo = m.getContainer().closest(".mapa__lienzo");
    var url = lienzo && lienzo.getAttribute("data-base-geo");
    if (!url || !window.fetch || !window.L) { return; }
    var conTeselas = lienzo.getAttribute("data-teselas") === "1";
    var estado = lienzo.getAttribute("data-estado") || "";
    cargarGeo(url).then(function (geo) {
      if (!m.getPane("base")) { m.createPane("base").style.zIndex = 250; }
      var capa = window.L.geoJSON(geo, {
        pane: "base",
        renderer: window.L.svg({ pane: "base" }),
        style: function (f) {
          var sel = estado && f.properties.nombre === estado;
          return {
            color: sel ? "#135c3b" : "#7d858c", weight: sel ? 2.4 : (conTeselas ? 0.8 : 1),
            opacity: conTeselas && !sel ? 0.7 : 1,
            fillColor: sel ? "#e8f4ee" : "#fbfcfa", fillOpacity: conTeselas ? 0 : 1
          };
        },
        onEachFeature: function (f, capaEstado) {
          if (!f.properties.nombre) { return; }
          capaEstado.bindTooltip(f.properties.nombre, { sticky: true, className: "mapa__etiqueta" });
        }
      }).addTo(m);
      capa.bringToBack();
      if (m.attributionControl) { m.attributionControl.addAttribution("Límites estatales: Natural Earth"); }
    }).catch(function () { /* sin base local: los datos del mapa siguen disponibles */ });
  }

  mapas().forEach(function (m) {
    agregarBase(m);
    var lienzo = m.getContainer().closest(".mapa__lienzo");
    try {
      var dato = lienzo && lienzo.getAttribute("data-vista");
      m._vistaSeleccion = dato ? JSON.parse(dato) : null;
    } catch (e) { m._vistaSeleccion = null; }
    m.on("dragstart", function () { m._interactuado = true; });
    m.on("zoomstart", function () { if (!m._ajusteProgramatico) { m._interactuado = true; } });
    m.invalidateSize({ pan: false });
    aplicarVista(m);
  });

  var ajustarMapas = debounce(function () {
    mapas().forEach(function (m) {
      m.invalidateSize({ pan: false });
      if (!m._interactuado) { aplicarVista(m); }
    });
  }, 150);

  /* ---------------------------------------------------------------- Menú */
  var boton = document.querySelector(".menu-boton");
  var menu = document.getElementById("menu-principal");
  function cerrarMenu(devolverFoco) {
    if (!menu || !menu.classList.contains("abierto")) { return; }
    menu.classList.remove("abierto");
    boton.setAttribute("aria-expanded", "false");
    if (devolverFoco) { boton.focus(); }
    ajustarMapas();
  }
  if (boton && menu) {
    boton.addEventListener("click", function () {
      var abierto = menu.classList.toggle("abierto");
      boton.setAttribute("aria-expanded", abierto ? "true" : "false");
      if (abierto) {
        var primero = menu.querySelector("a");
        if (primero) { primero.focus(); }
      }
      ajustarMapas();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { cerrarMenu(true); }
    });
    document.addEventListener("click", function (e) {
      if (!menu.contains(e.target) && !boton.contains(e.target)) { cerrarMenu(false); }
    });
    menu.querySelectorAll("a").forEach(function (a) {
      a.addEventListener("click", function () { cerrarMenu(false); });
    });
    var escritorio = window.matchMedia("(min-width: 75em)");
    if (escritorio.addEventListener) {
      escritorio.addEventListener("change", function () { cerrarMenu(false); ajustarMapas(); });
    }
  }

  /* ------------------------------------------------- Indicadores de carga */
  document.querySelectorAll("form[data-carga]").forEach(function (form) {
    form.addEventListener("submit", function () {
      var ind = form.querySelector(".indicador");
      if (ind) { ind.textContent = "Cargando…"; }
      var b = form.querySelector("button[type=submit]");
      if (b) { b.setAttribute("aria-busy", "true"); }
    });
  });

  // Página restaurada desde la caché al navegar hacia atrás: se retira el indicador de carga.
  window.addEventListener("pageshow", function (e) {
    if (!e.persisted) { return; }
    document.querySelectorAll("form[data-carga]").forEach(function (form) {
      var ind = form.querySelector(".indicador");
      if (ind) { ind.textContent = ""; }
      var b = form.querySelector("button[type=submit]");
      if (b) { b.removeAttribute("aria-busy"); }
    });
  });

  /* ------------------------------------------------ Filtros dependientes */
  // Las combinaciones con datos se calculan en el servidor (mismo criterio que
  // la vista) y se incluyen en la página: no hay consultas asíncronas que puedan
  // llegar fuera de orden. Cada lista ofrece solo valores compatibles con los
  // demás filtros; el servidor vuelve a validar la combinación recibida.
  function iniciarDependencias(form) {
    var fuente = document.getElementById(form.getAttribute("data-disponibilidad"));
    if (!fuente) { return; }
    var spec;
    try { spec = JSON.parse(fuente.textContent); } catch (e) { return; }
    var nombres = [], selects = {}, originales = {};
    Array.prototype.forEach.call(form.querySelectorAll("select"), function (s) {
      if (Object.prototype.hasOwnProperty.call(spec.campos, s.name)) {
        nombres.push(s.name);
        selects[s.name] = s;
        originales[s.name] = Array.prototype.map.call(s.options, function (o) {
          var g = o.parentNode && o.parentNode.tagName === "OPTGROUP" ? o.parentNode.label : null;
          return { valor: o.value, texto: o.text, grupo: g };
        });
      }
    });
    // El servidor solo muestra las opciones de la selección actual; se completan con
    // los valores existentes en los datos para poder cambiar a otra combinación.
    nombres.forEach(function (n, i) {
      var conocidos = {}, nuevos = [];
      originales[n].forEach(function (o) { conocidos[o.valor] = true; });
      spec.filas.forEach(function (f) {
        var v = String(f[spec.campos[n]]);
        if (v !== "" && !conocidos[v]) { conocidos[v] = true; nuevos.push({ valor: v, texto: v }); }
      });
      if (!nuevos.length) { return; }
      var lista = originales[n].concat(nuevos);
      if (i > 0) {
        var vacio = lista.filter(function (o) { return o.valor === ""; });
        var resto = lista.filter(function (o) { return o.valor !== ""; }).sort(function (a, b) {
          return a.valor.localeCompare(b.valor, "es", { numeric: true });
        });
        lista = vacio.concat(resto);
      }
      originales[n] = lista;
    });
    var boton = form.querySelector("button[type=submit]");
    var aviso = form.querySelector(".filtros__sin-opciones");

    function cumple(fila, nombre, valor) {
      var x = fila[spec.campos[nombre]], tipo = (spec.rangos || {})[nombre];
      if (tipo === "desde") { return Number(x) >= Number(valor); }
      if (tipo === "hasta") { return Number(x) <= Number(valor); }
      return String(x) === valor;
    }
    function permitidos(nombre, restricciones) {
      var conjunto = {};
      spec.filas.forEach(function (fila) {
        for (var i = 0; i < restricciones.length; i++) {
          var r = restricciones[i];
          if (r !== nombre && selects[r].value && !cumple(fila, r, selects[r].value)) { return; }
        }
        conjunto[String(fila[spec.campos[nombre]])] = true;
      });
      return conjunto;
    }
    function reconstruir(nombre, conjunto) {
      var s = selects[nombre], actual = s.value, hayVacio = false, primero = null, grupos = {};
      while (s.firstChild) { s.removeChild(s.firstChild); }
      originales[nombre].forEach(function (o) {
        if (o.valor === "" || conjunto[o.valor]) {
          // Se conservan los grupos (optgroup) del formulario, p. ej. productos por cultivo.
          var destino = s;
          if (o.grupo) {
            if (!grupos[o.grupo]) {
              grupos[o.grupo] = document.createElement("optgroup");
              grupos[o.grupo].label = o.grupo;
              s.appendChild(grupos[o.grupo]);
            }
            destino = grupos[o.grupo];
          }
          destino.appendChild(new Option(o.texto, o.valor));
          if (o.valor === "") { hayVacio = true; } else if (primero === null) { primero = o.valor; }
        }
      });
      if (actual === "" ? hayVacio : conjunto[actual]) { s.value = actual; }
      else { s.value = hayVacio ? "" : (primero || ""); }
      return primero !== null || hayVacio;
    }
    function actualizar() {
      // Dependencia jerárquica en el orden del formulario: cada filtro ofrece solo los
      // valores con datos para los filtros anteriores y conserva su selección si sigue
      // siendo válida; de lo contrario pasa a la opción general o a la primera disponible.
      var completo = true;
      nombres.forEach(function (n, i) {
        if (!reconstruir(n, permitidos(n, nombres.slice(0, i)))) { completo = false; }
      });
      // Un filtro opcional sin valores para la selección (p. ej. la presentación de los
      // granos) se oculta en lugar de mostrar solo la opción general.
      nombres.forEach(function (n) {
        var s = selects[n], campo = s.closest(".campo");
        if (campo && s.hasAttribute("data-ocultar-sin-opciones")) {
          campo.hidden = !Array.prototype.some.call(s.options, function (o) { return o.value !== ""; });
        }
      });
      if (boton) { boton.disabled = !completo; }
      if (aviso) { aviso.hidden = completo; }
    }
    nombres.forEach(function (n) {
      selects[n].addEventListener("change", actualizar);
    });
    // Antes de enviar se recalculan las listas con los valores actuales: no se envía una
    // combinación sin datos ni un valor que ya no figura entre las opciones.
    form.addEventListener("submit", function (e) {
      actualizar();
      if (boton && boton.disabled) { e.preventDefault(); e.stopImmediatePropagation(); }
    }, true);
    // Al volver con Atrás/Adelante (caché de página) o si el navegador restaura valores
    // del formulario, las listas se reconstruyen con la selección restaurada.
    window.addEventListener("pageshow", actualizar);
    actualizar();
  }
  document.querySelectorAll("form[data-disponibilidad]").forEach(iniciarDependencias);

  /* ------------------------------------------------------------ Gráficas */
  var LOCALE_ES = {
    moduleType: "locale",
    name: "es",
    dictionary: {
      "Zoom": "Ampliar un área", "Pan": "Desplazar", "Zoom in": "Acercar", "Zoom out": "Alejar",
      "Reset axes": "Restablecer los ejes", "Autoscale": "Ajuste automático",
      "Download plot as a png": "Descargar como imagen PNG", "Double-click to zoom back out": "Haga doble clic para alejar"
    },
    format: {
      days: ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"],
      shortDays: ["dom.", "lun.", "mar.", "miérc.", "juev.", "vier.", "sáb."],
      months: ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
               "septiembre", "octubre", "noviembre", "diciembre"],
      shortMonths: ["ene.", "feb.", "mar.", "abr.", "may.", "jun.", "jul.", "ago.", "sept.", "oct.", "nov.", "dic."],
      date: "%d/%m/%Y",
      decimal: ".",
      thousands: ","
    }
  };
  var tactil = window.matchMedia("(pointer: coarse)").matches;
  var config = {
    responsive: true,
    displaylogo: false,
    locale: "es",
    scrollZoom: false,
    doubleClick: "reset+autosize",
    displayModeBar: tactil ? true : "hover",
    modeBarButtonsToRemove: ["lasso2d", "select2d", "toggleSpikelines"]
  };

  function ajustarLayout(layout, nSeries) {
    layout.autosize = true;
    if (window.innerWidth < 600) {
      // Margen inferior para etiquetas de fecha en dos lineas o rotadas, y margen
      // derecho para que la ultima etiqueta del eje no se corte.
      // Con título en el eje temporal (fechas en dos líneas más el título) se reserva más espacio.
      var conTituloX = Object.keys(layout).some(function (k) {
        return /^xaxis\d*$/.test(k) && layout[k] && layout[k].title && layout[k].title.text;
      });
      layout.margin = Object.assign({}, layout.margin || {}, { l: 44, r: 24, b: Math.max((layout.margin || {}).b || 0, conTituloX ? 88 : 64) });
      layout.legend = Object.assign({}, layout.legend || {}, { font: { size: 11 } });
      // Títulos de los paneles: los largos se parten en dos líneas para que no se corten.
      (layout.annotations || []).forEach(function (a) {
        if (!a.showarrow && typeof a.text === "string" && a.text.length > 34 && a.text.indexOf("<br>") < 0) {
          var medio = Math.floor(a.text.length / 2), i = a.text.lastIndexOf(" ", medio);
          if (i < 0) { i = a.text.indexOf(" ", medio); }
          if (i > 0) { a.text = a.text.slice(0, i) + "<br>" + a.text.slice(i + 1); }
        }
      });
      // Leyenda debajo de la gráfica: en pantallas estrechas cada serie ocupa una o
      // dos filas, así que se reserva altura para no reducir el área de datos.
      if (layout.legend.yanchor === "top" && layout.legend.y < 0 && layout.height) {
        layout.height = Math.max(layout.height, 440 + 34 * nSeries);
        layout.margin = Object.assign({}, layout.margin, { b: layout.margin.b + 24 });
      }
      layout.font = Object.assign({}, layout.font || {}, { size: 12 });
    }
    // En pantallas táctiles la barra de herramientas está siempre visible: se reserva
    // espacio para que no cubra los títulos de los paneles ubicados en el borde superior.
    if (tactil && (layout.annotations || []).some(function (a) {
      return !a.showarrow && a.yref === "paper" && a.y >= 0.99;
    })) {
      layout.margin = Object.assign({}, layout.margin || {}, { t: Math.max((layout.margin || {}).t || 0, 72) });
    }
    // En pantallas táctiles el arrastre desplaza la página; el zoom se realiza
    // con los botones de la barra de herramientas o el control de rango.
    if (tactil) { layout.dragmode = false; }
    return layout;
  }

  // La barra de herramientas se ubica en la esquina superior; cuando la leyenda
  // va arriba se reserva espacio para que no se superpongan.
  function reservarBarra(el) {
    var fl = el._fullLayout;
    if (!fl || !fl.showlegend || !fl.legend || fl.legend.yanchor !== "bottom" || fl.legend.y < 1) { return; }
    var barra = el.querySelector(".modebar");
    var altoBarra = barra ? Math.max(barra.getBoundingClientRect().height, 28) : 28;
    var separacion = Math.max(0, (fl.legend.y - 1) * ((fl._size && fl._size.h) || 0));
    var necesario = Math.ceil((fl.legend._height || 0) + altoBarra + separacion + 8);
    if (Math.abs((fl.margin.t || 0) - necesario) > 3) {
      window.Plotly.relayout(el, { "margin.t": necesario });
    }
  }

  var observador = window.ResizeObserver ? new ResizeObserver(debounce(function (entradas) {
    entradas.forEach(function (e) {
      // Solo los cambios de ancho requieren recalcular; el alto lo ajusta la propia figura.
      var ancho = Math.round(e.contentRect.width);
      if (e.target._anchoPrevio === ancho) { return; }
      e.target._anchoPrevio = ancho;
      if (e.target.classList.contains("grafica--lista")) {
        window.Plotly.Plots.resize(e.target).then(function () { reservarBarra(e.target); });
      }
    });
  }, 150)) : null;

  /* Escala vertical del intervalo visible. Plotly calcula el ajuste automático con
     todos los datos; al acercar el eje temporal (control de rango, botones de
     periodo o selección horizontal) se recalcula con los valores visibles para que
     las curvas no queden comprimidas. No se aplica cuando el usuario fija también
     el eje vertical. */
  function ms(v) {
    if (typeof v === "number") { return v; }
    var s = String(v);
    if (s.length <= 10) { s += "T00:00:00"; }
    return Date.parse(s.replace(" ", "T") + (/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? "" : "Z"));
  }
  function rangoX(el) {
    var ax = el._fullLayout && el._fullLayout.xaxis;
    return ax && ax.range ? [ms(ax.range[0]), ms(ax.range[1])] : null;
  }
  function ajustarEjeY(el) {
    var fl = el._fullLayout, r = rangoX(el);
    if (!fl || !r) { return; }
    var ext = {};
    el._fullData.forEach(function (t) {
      if (t.visible !== true || !t.x || !t.y || t.type === "heatmap" || t.type === "box") { return; }
      var eje = (t.yaxis || "y").replace("y", "yaxis"), e = ext[eje] || (ext[eje] = { min: Infinity, max: -Infinity });
      if (t.type === "bar") { e.min = Math.min(e.min, 0); e.max = Math.max(e.max, 0); }
      for (var i = 0; i < t.x.length; i++) {
        var y = t.y[i];
        if (y === null || y === undefined || isNaN(y)) { continue; }
        var x = ms(t.x[i]);
        if (x >= r[0] && x <= r[1]) { e.min = Math.min(e.min, y); e.max = Math.max(e.max, y); }
      }
    });
    var cambios = {};
    Object.keys(ext).forEach(function (eje) {
      var e = ext[eje];
      if (!isFinite(e.min)) { return; }
      var pad = (e.max - e.min) * 0.06 || Math.max(Math.abs(e.max) * 0.05, 1);
      var min = e.min - pad;
      var ax = fl[eje];
      if (ax && ax.rangemode === "tozero" && e.min >= 0) { min = 0; }
      cambios[eje + ".range"] = [min, e.max + pad];
    });
    if (Object.keys(cambios).length) {
      el._ajustandoY = true;
      window.Plotly.relayout(el, cambios).then(function () { el._ajustandoY = false; }, function () { el._ajustandoY = false; });
    }
  }
  function vigilarEjeX(el) {
    el.on("plotly_relayout", function (ev) {
      if (el._ajustandoY || !ev) { return; }
      var claves = Object.keys(ev);
      var x = claves.some(function (k) { return /^xaxis\d*\.(range|autorange)/.test(k); });
      var y = claves.some(function (k) { return /^yaxis\d*\.(range|autorange)/.test(k); });
      if (x && !y) { ajustarEjeY(el); }
    });
  }

  /* Controles de la gráfica de validación: modelos, periodo y acercamiento. */
  function aplicarModelos(el, valor) {
    var meta = (el.layout && el.layout.meta) || {}, iniciales = meta.iniciales || [];
    var visible = el.data.map(function (t) {
      var m = t.meta || {};
      if (m.rol === "observado") { return true; }
      if (m.rol === "ajuste") { return (valor !== "inicial" && valor !== "todos" && m.modelo === valor) ? true : "legendonly"; }
      if (m.rol === "pronostico") {
        if (valor === "todos") { return true; }
        if (valor === "inicial") { return iniciales.indexOf(m.modelo) >= 0 ? true : "legendonly"; }
        return m.modelo === valor ? true : "legendonly";
      }
      return t.visible;
    });
    return window.Plotly.restyle(el, { visible: visible });
  }
  function aplicarRango(el, clave) {
    var vistas = ((el.layout && el.layout.meta) || {}).vistas || {};
    if (!vistas[clave]) { return Promise.resolve(); }
    el._vistaActual = clave;
    return window.Plotly.relayout(el, { "xaxis.range": vistas[clave].slice() });
  }
  function iniciarControles(el) {
    var caja = document.querySelector('[data-controles="' + el.getAttribute("data-figura") + '"]');
    if (!caja) { return; }
    var botonesRango = caja.querySelectorAll("[data-rango]");
    function marcar(clave) {
      Array.prototype.forEach.call(botonesRango, function (b) {
        b.setAttribute("aria-pressed", b.getAttribute("data-rango") === clave ? "true" : "false");
      });
    }
    el._vistaActual = ((el.layout.meta || {}).vistaInicial) || "evaluacion";
    Array.prototype.forEach.call(botonesRango, function (b) {
      b.addEventListener("click", function () {
        marcar(b.getAttribute("data-rango"));
        aplicarRango(el, b.getAttribute("data-rango"));
      });
    });
    caja.querySelectorAll("[data-zoom]").forEach(function (b) {
      b.addEventListener("click", function () {
        var r = rangoX(el), vistas = (el.layout.meta || {}).vistas || {}, total = vistas.historico;
        if (!r) { return; }
        var f = Number(b.getAttribute("data-zoom")), centro = (r[0] + r[1]) / 2, medio = (r[1] - r[0]) * f / 2;
        medio = Math.max(medio, 14 * 86400000);
        var a = centro - medio, z = centro + medio;
        if (total) {
          var t0 = ms(total[0]), t1 = ms(total[1]);
          if (z - a >= t1 - t0) { a = t0; z = t1; }
          else if (a < t0) { z += t0 - a; a = t0; }
          else if (z > t1) { a -= z - t1; z = t1; }
        }
        marcar(null);
        window.Plotly.relayout(el, { "xaxis.range": [new Date(a).toISOString(), new Date(z).toISOString()] });
      });
    });
    var sel = caja.querySelector("[data-modelos]");
    if (sel) {
      sel.addEventListener("change", function () {
        // Al cambiar de modelo se vuelve al periodo activo para no conservar un
        // acercamiento que correspondía a la selección anterior.
        aplicarModelos(el, sel.value).then(function () {
          marcar(el._vistaActual);
          return aplicarRango(el, el._vistaActual);
        });
      });
    }
  }

  function dibujar() {
    if (window.Plotly.register) { window.Plotly.register(LOCALE_ES); }
    document.querySelectorAll(".grafica[data-figura]").forEach(function (el) {
      var fuente = document.getElementById(el.getAttribute("data-figura"));
      if (!fuente) { return; }
      try {
        var fig = JSON.parse(fuente.textContent);
        if (!fig || !fig.data) { throw new Error("figura vacía"); }
        var layout = ajustarLayout(fig.layout || {}, fig.data.length);
        // Con config.responsive, Plotly toma el alto del contenedor: se fija al alto de
        // la figura para no recortarla ni comprimirla.
        if (layout.height) { el.style.height = layout.height + "px"; }
        var conf = config;
        if (layout.meta && layout.meta.vistas) { conf = Object.assign({}, config, { displayModeBar: true }); }
        window.Plotly.newPlot(el, fig.data, layout, conf).then(function () {
          reservarBarra(el);
          el.classList.add("grafica--lista");
          if (observador) { observador.observe(el); }
          if (layout.meta && layout.meta.ajustarY) { vigilarEjeX(el); }
          if (layout.meta && layout.meta.vistas) { iniciarControles(el); }
        });
      } catch (e) {
        el.innerHTML = '<p class="grafica__error">No fue posible mostrar la gráfica. Recargue la página para intentarlo de nuevo.</p>';
      }
    });
  }

  // Selector de periodo (Anual / Mensual / Semanal): muestra las trazas cuya
  // propiedad meta.vista coincide; las trazas sin vista permanecen visibles.
  document.querySelectorAll(".vistas[data-para]").forEach(function (grupo) {
    var objetivo = document.querySelector('.grafica[data-figura="' + grupo.getAttribute("data-para") + '"]');
    grupo.querySelectorAll("[data-vista]").forEach(function (b) {
      b.addEventListener("click", function () {
        if (!objetivo || !objetivo.data) { return; }
        var vista = b.getAttribute("data-vista");
        var visibles = objetivo.data.map(function (t) {
          return !(t.meta && t.meta.vista) || t.meta.vista === vista;
        });
        window.Plotly.restyle(objetivo, { visible: visibles });
        // Títulos que dependen del periodo elegido (eje o panel), definidos por la figura.
        var textos = (((objetivo.layout || {}).meta || {}).textosVista || {})[vista] || {};
        window.Plotly.relayout(objetivo, Object.assign({ "xaxis.autorange": true, "yaxis.autorange": true }, textos));
        grupo.querySelectorAll("[data-vista]").forEach(function (o) {
          o.setAttribute("aria-pressed", o === b ? "true" : "false");
        });
      });
    });
  });

  if (window.Plotly) { dibujar(); }
  else { window.addEventListener("load", function () { if (window.Plotly) { dibujar(); } }); }

  if (window.ResizeObserver) {
    var ro = new ResizeObserver(ajustarMapas);
    document.querySelectorAll(".mapa__lienzo").forEach(function (el) { ro.observe(el); });
  }
  window.addEventListener("resize", ajustarMapas);
  window.addEventListener("orientationchange", ajustarMapas);
  document.querySelectorAll("details").forEach(function (d) { d.addEventListener("toggle", ajustarMapas); });
  window.addEventListener("load", ajustarMapas);
})();
