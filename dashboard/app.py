"""Dashboard de DocuVali (Streamlit): consume la API REST y muestra resultados en vivo."""
import base64
import os
import time
from pathlib import Path

import altair as alt
import pandas as pd
import requests
import streamlit as st

API_URL = os.environ.get("API_URL", "http://api:8000")
API_KEY = os.environ.get("DASHBOARD_API_KEY", "demo-key-cambiar")
VERIFY_TLS = os.environ.get("VERIFY_TLS", "false").lower() == "true"
MUESTRAS = Path(os.environ.get("MUESTRAS_DIR", Path(__file__).parent / "muestras"))
CABECERAS = {"X-API-Key": API_KEY}

TEAL, NAVY, ROJO, VERDE, AMBAR, GRIS = "#0B6E79", "#0B3C49", "#C44536", "#2E8B57", "#F2A541", "#5B7B86"
NOMBRES = {"APROBADO_AUTOMATICO": "Aprobado automático", "REVISION_HUMANA": "Revisión humana"}
ETIQUETAS = {"calidad_imagen": "Calidad de la imagen", "confianza_ocr_media": "Confianza promedio del OCR",
             "confianza_ocr_min": "Confianza mínima del OCR", "campos_detectados": "Campos encontrados",
             "rut_valido": "RUT válido", "iva_cuadra": "IVA cuadra", "total_cuadra": "Total cuadra",
             "coincide_xml": "Coincide con XML del SII", "log_monto": "Monto del documento",
             "tipo_documento=factura": "Es factura", "tipo_documento=boleta": "Es boleta",
             "tipo_documento=nota_credito": "Es nota de crédito"}
MUESTRAS_DEMO = {
    "Factura correcta": ("factura_correcta", "factura"),
    "Factura con IVA incorrecto": ("factura_iva_incorrecto", "factura"),
    "Boleta borrosa": ("boleta_borrosa", "boleta"),
}

st.set_page_config(page_title="DocuVali · Panel", page_icon="🧾", layout="wide", initial_sidebar_state="expanded")

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stMarkdown, .stText, button, input {{ font-family: 'Inter', system-ui, sans-serif; }}
.block-container {{ padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1400px; }}
#MainMenu, footer, [data-testid="stToolbar"] {{ visibility: hidden; }}
.hero {{ background: linear-gradient(120deg, {NAVY} 0%, {TEAL} 100%); border-radius: 18px; padding: 26px 32px;
        color: white; display: flex; justify-content: space-between; align-items: center; gap: 24px; flex-wrap: wrap;
        box-shadow: 0 10px 30px rgba(11,60,73,.18); margin-bottom: 18px; }}
.hero h1 {{ color: white; font-size: 1.9rem; font-weight: 700; margin: 0; letter-spacing: -.02em; }}
.hero p {{ color: #CFE3E6; margin: 4px 0 0; font-size: .98rem; }}
.chips {{ display: flex; gap: 8px; flex-wrap: wrap; }}
.chip {{ background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.25); border-radius: 999px;
        padding: 6px 12px; font-size: .82rem; color: white; white-space: nowrap; }}
.dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }}
.kpi {{ background: white; border: 1px solid #E3ECEE; border-radius: 14px; padding: 16px 18px; height: 100%;
       box-shadow: 0 2px 10px rgba(11,60,73,.05); transition: transform .15s ease; }}
.kpi:hover {{ transform: translateY(-2px); }}
.kpi .lbl {{ color: {GRIS}; font-size: .8rem; font-weight: 500; text-transform: uppercase; letter-spacing: .04em; }}
.kpi .val {{ color: {NAVY}; font-size: 1.9rem; font-weight: 700; margin-top: 4px; line-height: 1.1; }}
.kpi .sub {{ color: {GRIS}; font-size: .82rem; margin-top: 4px; }}
.kpi.acc {{ border-left: 5px solid {TEAL}; }} .kpi.warn {{ border-left: 5px solid {ROJO}; }} .kpi.amb {{ border-left: 5px solid {AMBAR}; }}
.veredicto {{ border-radius: 16px; padding: 20px 24px; color: white; margin-bottom: 14px; }}
.veredicto h2 {{ color: white; margin: 0; font-size: 1.6rem; }}
.veredicto p {{ margin: 4px 0 0; opacity: .92; }}
.ok {{ background: linear-gradient(120deg, #1F7A4D, {VERDE}); }} .rev {{ background: linear-gradient(120deg, #9E2F23, {ROJO}); }}
.check {{ display: flex; justify-content: space-between; padding: 9px 12px; border-radius: 10px; margin-bottom: 6px;
         background: #F5F9FA; font-size: .92rem; }}
.check b.si {{ color: {VERDE}; }} .check b.no {{ color: {ROJO}; }}
.paso {{ display: flex; align-items: center; gap: 10px; padding: 6px 0; font-size: .92rem; color: {NAVY}; }}
.paso .n {{ width: 26px; height: 26px; border-radius: 50%; background: {TEAL}; color: white; display: grid;
           place-items: center; font-size: .8rem; font-weight: 600; }}
.stTabs [data-baseweb="tab-list"] {{ gap: 6px; }}
.stTabs [data-baseweb="tab"] {{ background: #F1F6F7; border-radius: 10px 10px 0 0; padding: 10px 18px; font-weight: 600; }}
.stTabs [aria-selected="true"] {{ background: {TEAL} !important; color: white !important; }}
div.stButton > button {{ border-radius: 10px; font-weight: 600; }}
</style>
""", unsafe_allow_html=True)


# ---------------- API ----------------
def api(metodo, ruta, **kw):
    r = requests.request(metodo, f"{API_URL}{ruta}", headers=CABECERAS, timeout=20, verify=VERIFY_TLS, **kw)
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=3, show_spinner=False)
def leer_metricas():
    return api("GET", "/api/v1/metricas")


@st.cache_data(ttl=10, show_spinner=False)
def leer_salud():
    try:
        return requests.get(f"{API_URL}/health", timeout=3, verify=VERIFY_TLS).json()
    except Exception:
        return None


def pct(x):
    return "—" if x is None else f"{x:.0%}"


# ---------------- Componentes visuales ----------------
def kpi(col, etiqueta, valor, sub="", clase="acc"):
    col.markdown(f'<div class="kpi {clase}"><div class="lbl">{etiqueta}</div><div class="val">{valor}</div>'
                 f'<div class="sub">{sub}</div></div>', unsafe_allow_html=True)


def medidor(prob, revision):
    color = ROJO if revision else VERDE
    df = pd.DataFrame({"parte": ["valor", "resto"], "v": [prob, max(1 - prob, 0.0001)]})
    arco = alt.Chart(df).mark_arc(innerRadius=62, outerRadius=86, cornerRadius=6).encode(
        theta=alt.Theta("v:Q", stack=True),
        color=alt.Color("parte:N", scale=alt.Scale(domain=["valor", "resto"], range=[color, "#E8EFF1"]), legend=None),
        order=alt.Order("parte:N", sort="descending"), tooltip=alt.value(None))
    texto = alt.Chart(pd.DataFrame({"t": [f"{prob:.1%}"]})).mark_text(fontSize=30, fontWeight=700, color=NAVY).encode(text="t:N")
    sub = alt.Chart(pd.DataFrame({"t": ["riesgo de error"]})).mark_text(fontSize=12, dy=24, color=GRIS).encode(text="t:N")
    return (arco + texto + sub).properties(height=200).configure_view(strokeWidth=0)


def razones_html(razones):
    maximo = max(abs(r["aporte"]) for r in razones) or 1
    html = ""
    for i, r in enumerate(razones, 1):
        color = ROJO if r["aporte"] > 0 else VERDE
        ancho = abs(r["aporte"]) / maximo * 100
        texto = r["descripcion"][0].upper() + r["descripcion"][1:]
        html += (f'<div style="margin-bottom:12px"><div style="display:flex;justify-content:space-between;font-size:.92rem">'
                 f'<span><b>{i}. {texto}</b></span><span style="color:{color};font-weight:600">{r["efecto"]}</span></div>'
                 f'<div style="background:#E8EFF1;border-radius:6px;height:10px;margin-top:5px">'
                 f'<div style="width:{ancho:.0f}%;background:{color};height:10px;border-radius:6px"></div></div></div>')
    return html


def chequeos(v):
    filas = [("RUT del emisor válido (módulo 11)", v.get("rut_valido")), ("IVA = 19% del neto", v.get("iva_cuadra")),
             ("Total = neto + IVA", v.get("total_cuadra")), ("Coincide con el XML del SII", v.get("coincide_xml"))]
    html = "".join(f'<div class="check"><span>{t}</span><b class="{"si" if ok else "no"}">{"✔ Sí" if ok else "✘ No"}</b></div>'
                   for t, ok in filas)
    html += (f'<div class="check"><span>Calidad de la imagen</span><b>{v.get("calidad_imagen", 0):.0%}</b></div>'
             f'<div class="check"><span>Confianza mínima del OCR</span><b>{v.get("confianza_ocr_min", 0):.0%}</b></div>')
    st.markdown(html, unsafe_allow_html=True)


def mostrar_resultado(p, variables=None, campos=None, tiempos=None):
    revision = p["decision"] == "REVISION_HUMANA"
    titulo = "🔎 Enviar a revisión humana" if revision else "✅ Aprobado automáticamente"
    detalle = ("El modelo detectó riesgo de error en la extracción." if revision
               else "El documento se puede registrar sin intervención.")
    st.markdown(f'<div class="veredicto {"rev" if revision else "ok"}"><h2>{titulo}</h2>'
                f'<p>{detalle} Confianza de la decisión: <b>{p["confianza_decision"]:.1%}</b> · '
                f'modelo {p.get("version_modelo", "")}</p></div>', unsafe_allow_html=True)
    c1, c2 = st.columns([1, 2])
    with c1:
        st.altair_chart(medidor(p["probabilidad_error"], revision), use_container_width=True)
    with c2:
        if p.get("razones"):
            st.markdown("**¿Por qué el modelo decidió esto?**")
            st.markdown(razones_html(p["razones"]), unsafe_allow_html=True)
    if variables or campos or tiempos:
        a, b = st.columns(2)
        if variables:
            with a:
                st.markdown("**Validaciones tributarias**")
                chequeos(variables)
        if campos:
            with b:
                st.markdown("**Campos leídos por el OCR**")
                def fmt(k, v):
                    return "$ " + f"{int(v):,}".replace(",", ".") if k in ("neto", "iva", "total") and v is not None else v
                tabla = pd.DataFrame([{"Campo": k.replace("_", " ").capitalize(), "Valor": str(fmt(k, v))} for k, v in campos.items()])
                st.dataframe(tabla, hide_index=True, use_container_width=True)
        if tiempos:
            st.markdown("**Tiempo de cada etapa**")
            dt = pd.DataFrame({"Etapa": list(tiempos), "ms": list(tiempos.values())})
            st.altair_chart(alt.Chart(dt).mark_bar(cornerRadiusEnd=5, color=TEAL, height=18).encode(
                x=alt.X("ms:Q", title="milisegundos"), y=alt.Y("Etapa:N", sort=None, title=None),
                tooltip=["Etapa", alt.Tooltip("ms:Q", format=".1f")]).properties(height=120).configure_view(strokeWidth=0), use_container_width=True)


def procesar(nombre, contenido, tipo_mime, tipo, xml=None):
    files = {"archivo": (nombre, contenido, tipo_mime)}
    if xml:
        files["xml_dte"] = (f"{Path(nombre).stem}.xml", xml, "application/xml")
    with st.status("Procesando documento…", expanded=True) as estado:
        t0 = time.perf_counter()
        r = api("POST", "/api/v1/documentos", files=files, data={"tipo_documento": tipo})
        st.write(f"📨 La API respondió **202** en {(time.perf_counter() - t0) * 1000:.0f} ms · ID `{r['id']}`")
        st.write("🐇 Documento en la cola de RabbitMQ, esperando un worker…")
        doc = None
        for _ in range(60):
            doc = api("GET", f"/api/v1/documentos/{r['id']}")
            if doc["estado"] in ("listo", "error"):
                break
            time.sleep(0.4)
        if doc and doc["estado"] == "listo":
            st.write("🔍 OCR (Amazon Textract) leyó los campos de la factura")
            st.write("📐 Reglas del SII aplicadas: RUT, IVA, total y XML")
            st.write(f"🧠 Modelo ({doc['resultado']['motor_modelo']}) entregó su decisión")
            estado.update(label=f"Listo en {doc['ms_total']:.0f} ms", state="complete", expanded=False)
        else:
            estado.update(label="El documento no pudo procesarse", state="error")
    st.cache_data.clear()
    return doc


# ---------------- Barra lateral ----------------
salud = leer_salud()
with st.sidebar:
    st.markdown("### ⚙️ Estado del sistema")
    if salud:
        st.success(f"API en línea · modelo **{salud.get('modelo', '?')}**")
    else:
        st.error("API sin respuesta")
    auto = st.toggle("Actualizar indicadores cada 5 s", value=True)
    st.divider()
    st.markdown("### 🔄 Flujo de un documento")
    for i, paso in enumerate(["API REST recibe (HTTPS)", "Cola RabbitMQ", "Worker: Amazon Textract",
                              "Reglas SII (RUT, IVA, XML)", "Modelo en SageMaker", "Resultado y explicación"], 1):
        st.markdown(f'<div class="paso"><span class="n">{i}</span>{paso}</div>', unsafe_allow_html=True)
    st.divider()
    st.caption("DocuVali · EP3 ITY1102 · Duoc UC")

# ---------------- Encabezado ----------------
try:
    m0 = leer_metricas()
    cola0 = m0["cola"]
except Exception:
    m0, cola0 = None, {}
estado_api = ("#4ADE80", "API en línea") if salud else ("#F87171", "API sin conexión")
estado_cola = ("#4ADE80", "RabbitMQ conectado") if cola0.get("conectado") else ("#F87171", "RabbitMQ sin conexión")
st.markdown(f"""
<div class="hero">
  <div><h1>🧾 DocuVali</h1><p>Validación inteligente de documentos tributarios · ¿aprobar o revisar?, con la razón</p></div>
  <div class="chips">
    <span class="chip"><span class="dot" style="background:{estado_api[0]}"></span>{estado_api[1]}</span>
    <span class="chip"><span class="dot" style="background:{estado_cola[0]}"></span>{estado_cola[1]}</span>
    <span class="chip">🧠 Modelo: {(salud or {}).get('modelo', '—')}</span>
    <span class="chip">🔒 HTTPS · clave de API</span>
  </div>
</div>""", unsafe_allow_html=True)


@st.fragment(run_every=5 if auto else None)
def panel_kpis():
    try:
        m = leer_metricas()
    except Exception as e:
        st.warning(f"No se pudo leer la API: {e}")
        return
    op, cola = m["operacion"], m["cola"]
    c = st.columns(5)
    kpi(c[0], "Documentos", f"{op['documentos_total']:,}".replace(",", "."), f"{op['procesados']} procesados")
    kpi(c[1], "Aprobados automáticos", pct(op["pct_automatico"]), f"{op['aprobados_automatico']} documentos")
    kpi(c[2], "A revisión humana", op["revision_humana"], "el contador los revisa", "warn")
    p95 = op["ms_procesamiento_p95"]
    kpi(c[3], "Procesamiento p95", f"{p95:.0f} ms" if p95 else "—", "meta: menos de 3 s", "amb")
    kpi(c[4], "Cola RabbitMQ", cola.get("en_cola", "—"), f"fallidos (DLQ): {cola.get('fallidos', '—')}")


panel_kpis()
st.write("")

t1, t2, t3, t4 = st.tabs(["📄  Analizar documento", "🧪  Simulador del modelo", "📊  Operación", "🧠  Calidad del modelo"])

# ---------------- Analizar ----------------
with t1:
    izq, der = st.columns([3, 2], gap="large")
    with izq:
        st.markdown("#### Sube una factura o boleta")
        archivo = st.file_uploader("Imagen (PNG/JPG) o PDF", type=["png", "jpg", "jpeg", "pdf"])
        a, b = st.columns(2)
        tipo = a.selectbox("Tipo de documento", ["factura", "boleta", "nota_credito"])
        xml = b.file_uploader("XML del SII (opcional)", type=["xml"])
        enviar = st.button("Procesar documento", type="primary", disabled=archivo is None, use_container_width=True)
    with der:
        st.markdown("#### …o prueba con una muestra")
        st.caption("Documentos ficticios incluidos en el proyecto")
        elegido = None
        for etiqueta in MUESTRAS_DEMO:
            if st.button(f"▶  {etiqueta}", use_container_width=True, disabled=not MUESTRAS.exists()):
                elegido = etiqueta

    doc, imagen = None, None
    if enviar and archivo:
        imagen = archivo.getvalue()
        doc = procesar(archivo.name, imagen, archivo.type, tipo, xml.getvalue() if xml else None)
    elif elegido:
        nombre, tipo_m = MUESTRAS_DEMO[elegido]
        imagen = (MUESTRAS / f"{nombre}.png").read_bytes()
        ruta_xml = MUESTRAS / f"{nombre}.xml"
        doc = procesar(f"{nombre}.png", imagen, "image/png", tipo_m, ruta_xml.read_bytes() if ruta_xml.exists() else None)

    if doc and doc["estado"] == "listo":
        res = doc["resultado"]
        st.divider()
        col_img, col_res = st.columns([1, 2.6], gap="large")
        with col_img:
            if imagen:
                st.image(imagen, caption=doc.get("nombre_archivo"), use_container_width=True)
        with col_res:
            mostrar_resultado(res["prediccion"], res["variables"], (res.get("extraccion") or {}).get("campos"),
                              {"OCR": doc["ms_extraccion"], "Modelo": doc["ms_modelo"], "Total": doc["ms_total"]})
    elif doc:
        st.error(f"Error al procesar: {doc.get('error')}")

# ---------------- Simulador ----------------
with t2:
    st.markdown("#### Mueve las variables y mira cómo cambia la decisión del modelo en tiempo real")
    izq, der = st.columns([2, 3], gap="large")
    with izq:
        v = {"tipo_documento": st.selectbox("Tipo", ["factura", "boleta", "nota_credito"], key="sim_tipo"),
             "calidad_imagen": st.slider("Calidad de la imagen", 0.0, 1.0, 0.85, 0.01),
             "confianza_ocr_media": st.slider("Confianza promedio del OCR", 0.0, 1.0, 0.93, 0.01),
             "confianza_ocr_min": st.slider("Confianza mínima del OCR", 0.0, 1.0, 0.80, 0.01),
             "campos_detectados": st.slider("Campos encontrados", 0.0, 1.0, 1.0, 0.01),
             "monto_total": st.number_input("Monto total (CLP)", 0, 100_000_000, 119_000, step=10_000)}
        c = st.columns(2)
        v["rut_valido"] = int(c[0].toggle("RUT válido", True))
        v["iva_cuadra"] = int(c[1].toggle("IVA cuadra", True))
        v["total_cuadra"] = int(c[0].toggle("Total cuadra", True))
        v["coincide_xml"] = int(c[1].toggle("Coincide con XML", True))
    with der:
        try:
            p = api("POST", "/api/v1/predicciones", json=v)
            st.caption(f"Respuesta del modelo **{p['motor_modelo']}** en {p['ms_modelo']} ms")
            mostrar_resultado(p, v)
        except Exception as e:
            st.error(f"El modelo no respondió: {e}")

# ---------------- Operación ----------------
with t3:
    try:
        docs = api("GET", "/api/v1/documentos", params={"limite": 300})
    except Exception as e:
        docs = []
        st.error(str(e))
    filas = []
    for d in docs:
        pr = (d.get("resultado") or {}).get("prediccion") or {}
        filas.append({"ID": d["id"], "Fecha": pd.to_datetime(d["creado"]).tz_convert("America/Santiago").tz_localize(None), "Tipo": d["tipo_documento"],
                      "Estado": d["estado"], "Decisión": NOMBRES.get(pr.get("decision"), "—"),
                      "Riesgo": pr.get("probabilidad_error"), "ms": d["ms_total"]})
    df = pd.DataFrame(filas)
    if df.empty:
        st.info("Aún no hay documentos. Prueba con una muestra en la pestaña «Analizar documento».")
    else:
        listos = df[df["Decisión"] != "—"]
        a, b = st.columns(2, gap="large")
        with a:
            st.markdown("**Decisiones**")
            if not listos.empty:
                conteo = listos["Decisión"].value_counts().reset_index()
                conteo.columns = ["Decisión", "n"]
                st.altair_chart(alt.Chart(conteo).mark_arc(innerRadius=70, cornerRadius=5).encode(
                    theta="n:Q", color=alt.Color("Decisión:N", scale=alt.Scale(domain=list(NOMBRES.values()),
                                                 range=[VERDE, ROJO]), legend=alt.Legend(orient="bottom")),
                    tooltip=["Decisión", "n"]).properties(height=260), use_container_width=True)
        with b:
            st.markdown("**Riesgo de cada documento en el tiempo**")
            if not listos.empty:
                st.altair_chart(alt.Chart(listos).mark_circle(size=110, opacity=.85).encode(
                    x=alt.X("Fecha:T", title=None), y=alt.Y("Riesgo:Q", title="probabilidad de error", axis=alt.Axis(format="%"),
                                                            scale=alt.Scale(domain=[0, 1])),
                    color=alt.Color("Decisión:N", scale=alt.Scale(domain=list(NOMBRES.values()), range=[VERDE, ROJO]), legend=None),
                    tooltip=["ID", "Tipo", "Decisión", alt.Tooltip("Riesgo:Q", format=".1%")]).properties(height=260)
                    + alt.Chart(pd.DataFrame({"u": [0.5]})).mark_rule(strokeDash=[6, 4], color=GRIS).encode(y="u:Q"),
                    use_container_width=True)
        f1, f2 = st.columns(2)
        filtro_d = f1.multiselect("Filtrar por decisión", list(NOMBRES.values()), default=list(NOMBRES.values()))
        filtro_t = f2.multiselect("Filtrar por tipo", sorted(df["Tipo"].unique()), default=sorted(df["Tipo"].unique()))
        vista = df[(df["Decisión"].isin(filtro_d) | (df["Decisión"] == "—")) & df["Tipo"].isin(filtro_t)]
        st.dataframe(vista, hide_index=True, use_container_width=True, column_config={
            "Fecha": st.column_config.DatetimeColumn(format="DD-MM-YYYY HH:mm:ss"),
            "Riesgo": st.column_config.ProgressColumn("Riesgo de error", min_value=0, max_value=1, format="percent"),
            "ms": st.column_config.NumberColumn("Tiempo (ms)", format="%.0f")})
        st.download_button("⬇  Descargar CSV", vista.to_csv(index=False).encode("utf-8"), "docuvali_documentos.csv")

# ---------------- Modelo ----------------
with t4:
    mod = (m0 or {}).get("modelo")
    if not mod:
        st.info("Métricas del modelo no disponibles.")
    else:
        rl = mod["regresion_logistica"]
        st.markdown(f"#### Regresión logística · C = {mod['hiperparametros']['C']} · umbral {mod['hiperparametros']['umbral_decision']}"
                    f" · {mod['n_prueba']:,} documentos de prueba".replace(",", "."))
        c = st.columns(5)
        for col, (n, k, s) in zip(c, [("Accuracy", "accuracy", "aciertos totales"), ("Precision", "precision", "de los enviados a revisión"),
                                      ("Recall", "recall", "errores detectados"), ("F1-score", "f1", "equilibrio"), ("ROC-AUC", "roc_auc", "capacidad de separar")]):
            kpi(col, n, f"{rl[k]:.3f}", s)
        st.write("")
        a, b = st.columns(2, gap="large")
        with a:
            st.markdown("**Matriz de confusión**")
            mc = rl["matriz_confusion"]
            dm = pd.DataFrame([{"Real": "Correcto", "Predicho": "Aprobar", "n": mc["tn"]},
                               {"Real": "Correcto", "Predicho": "Revisar", "n": mc["fp"]},
                               {"Real": "Con error", "Predicho": "Aprobar", "n": mc["fn"]},
                               {"Real": "Con error", "Predicho": "Revisar", "n": mc["tp"]}])
            base = alt.Chart(dm).encode(x=alt.X("Predicho:N", title="Predicción", axis=alt.Axis(labelAngle=0)), y=alt.Y("Real:N", title="Realidad"))
            st.altair_chart((base.mark_rect(cornerRadius=8).encode(color=alt.Color("n:Q", scale=alt.Scale(range=["#E6F2F3", TEAL]), legend=None))
                             + base.mark_text(fontSize=22, fontWeight=700).encode(text="n:Q",
                               color=alt.condition(alt.datum.n > 500, alt.value("white"), alt.value(NAVY))))
                            .properties(height=260), use_container_width=True)
        with b:
            st.markdown("**Peso de cada variable (interpretabilidad global)**")
            coef = pd.DataFrame({"Variable": [ETIQUETAS.get(k, k) for k in mod["coeficientes"]], "Peso": list(mod["coeficientes"].values())})
            st.altair_chart(alt.Chart(coef).mark_bar(cornerRadiusEnd=5).encode(
                x=alt.X("Peso:Q", title="− reduce el riesgo · + lo aumenta"),
                y=alt.Y("Variable:N", sort="-x", title=None, axis=alt.Axis(labelLimit=260)),
                color=alt.condition(alt.datum.Peso > 0, alt.value(ROJO), alt.value(VERDE)),
                tooltip=["Variable", alt.Tooltip("Peso:Q", format=".3f")]).properties(height=300), use_container_width=True)
        if mod.get("analisis_umbrales"):
            st.markdown("**¿Qué pasa si cambio el umbral de decisión?**")
            du = pd.DataFrame([{"Umbral": u, "% automático": x["pct_automatico"], "Errores detectados": x["recall"],
                                "Errores sin revisar": x["errores_no_detectados_pct"]} for u, x in mod["analisis_umbrales"].items()])
            larga = du.melt("Umbral", var_name="Indicador", value_name="valor")
            st.altair_chart(alt.Chart(larga).mark_line(point=alt.OverlayMarkDef(size=90), strokeWidth=3).encode(
                x=alt.X("Umbral:O", axis=alt.Axis(labelAngle=0)), y=alt.Y("valor:Q", axis=alt.Axis(format="%"), title=None),
                color=alt.Color("Indicador:N", scale=alt.Scale(range=[TEAL, AMBAR, ROJO]), legend=alt.Legend(orient="bottom")),
                tooltip=["Umbral", "Indicador", alt.Tooltip("valor:Q", format=".1%")]).properties(height=280),
                use_container_width=True)
