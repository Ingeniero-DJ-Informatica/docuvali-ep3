"""Dashboard de DocuVali (Streamlit): consume la API REST y muestra resultados."""
import os
import time

import altair as alt
import pandas as pd
import requests
import streamlit as st

API_URL = os.environ.get("API_URL", "http://api:8000")
API_KEY = os.environ.get("DASHBOARD_API_KEY", "demo-key-cambiar")
VERIFY_TLS = os.environ.get("VERIFY_TLS", "false").lower() == "true"
CABECERAS = {"X-API-Key": API_KEY}
NOMBRES = {"APROBADO_AUTOMATICO": "Aprobado automático", "REVISION_HUMANA": "Revisión humana"}

st.set_page_config(page_title="DocuVali", page_icon="🧾", layout="wide")


def api(metodo, ruta, **kw):
    r = requests.request(metodo, f"{API_URL}{ruta}", headers=CABECERAS, timeout=15, verify=VERIFY_TLS, **kw)
    r.raise_for_status()
    return r.json()


def mostrar_prediccion(p, variables=None):
    revision = p["decision"] == "REVISION_HUMANA"
    c1, c2, c3 = st.columns(3)
    (c1.error if revision else c1.success)(f"**{NOMBRES[p['decision']]}**")
    c2.metric("Probabilidad de error", f"{p['probabilidad_error']:.1%}")
    c3.metric("Confianza de la decisión", f"{p['confianza_decision']:.1%}")
    if p.get("razones"):
        st.markdown("**¿Por qué el modelo decidió esto?**")
        df = pd.DataFrame(p["razones"])
        df["Variable"] = df["descripcion"]
        graf = alt.Chart(df).mark_bar().encode(
            x=alt.X("aporte:Q", title="Aporte a la decisión (+ aumenta el riesgo, − lo reduce)"),
            y=alt.Y("Variable:N", sort="-x", title=None),
            color=alt.condition(alt.datum.aporte > 0, alt.value("#C44536"), alt.value("#0B6E79")))
        st.altair_chart(graf, use_container_width=True)
        for r in p["razones"]:
            st.write(f"- **{r['descripcion']}** (valor {r['valor']}): {r['efecto']}")
    if variables:
        with st.expander("Variables enviadas al modelo"):
            st.json(variables)


st.title("🧾 DocuVali · Validación inteligente de documentos tributarios")
st.caption(f"API: {API_URL} · modelo en Amazon SageMaker · OCR con Amazon Textract · cola RabbitMQ")

try:
    m = api("GET", "/api/v1/metricas")
    op, cola = m["operacion"], m["cola"]
    k = st.columns(5)
    k[0].metric("Documentos", op["documentos_total"])
    k[1].metric("Aprobados automáticos", f"{op['pct_automatico']:.0%}" if op["pct_automatico"] is not None else "—")
    k[2].metric("A revisión humana", op["revision_humana"])
    k[3].metric("Procesamiento p95", f"{op['ms_procesamiento_p95']:.0f} ms" if op["ms_procesamiento_p95"] else "—")
    k[4].metric("En cola RabbitMQ", cola.get("en_cola", "—"), help=f"Fallidos (DLQ): {cola.get('fallidos', '—')}")
except Exception as e:
    m = None
    st.warning(f"No se pudo conectar con la API: {e}")

t1, t2, t3, t4 = st.tabs(["Analizar documento", "Simulador del modelo", "Historial", "Calidad del modelo"])

with t1:
    st.subheader("Subir factura o boleta")
    c1, c2 = st.columns([2, 1])
    archivo = c1.file_uploader("Imagen (PNG/JPG) o PDF", type=["png", "jpg", "jpeg", "pdf"])
    tipo = c2.selectbox("Tipo de documento", ["factura", "boleta", "nota_credito"])
    xml = c2.file_uploader("XML del SII (opcional)", type=["xml"])
    if archivo and st.button("Procesar documento", type="primary"):
        files = {"archivo": (archivo.name, archivo.getvalue(), archivo.type)}
        if xml:
            files["xml_dte"] = (xml.name, xml.getvalue(), "application/xml")
        r = api("POST", "/api/v1/documentos", files=files, data={"tipo_documento": tipo})
        st.info(f"Documento **{r['id']}** en cola. Esperando al worker…")
        doc = None
        with st.spinner("Textract → reglas → SageMaker"):
            for _ in range(40):
                doc = api("GET", f"/api/v1/documentos/{r['id']}")
                if doc["estado"] in ("listo", "error"):
                    break
                time.sleep(0.5)
        if doc and doc["estado"] == "listo":
            res = doc["resultado"]
            st.caption(f"OCR {doc['ms_extraccion']} ms · modelo {doc['ms_modelo']} ms · total {doc['ms_total']} ms")
            if res.get("extraccion"):
                ca, cb = st.columns(2)
                ca.markdown("**Campos extraídos**")
                ca.json(res["extraccion"]["campos"])
                cb.image(archivo.getvalue(), caption=archivo.name, use_container_width=True)
            mostrar_prediccion(res["prediccion"], res["variables"])
        else:
            st.error(f"El documento no terminó: {doc.get('error') if doc else 'sin respuesta'}")

with t2:
    st.subheader("Probar el modelo en tiempo real")
    c = st.columns(3)
    v = {
        "tipo_documento": c[0].selectbox("Tipo", ["factura", "boleta", "nota_credito"], key="sim_tipo"),
        "calidad_imagen": c[0].slider("Calidad de imagen", 0.0, 1.0, 0.85),
        "confianza_ocr_media": c[0].slider("Confianza OCR promedio", 0.0, 1.0, 0.93),
        "confianza_ocr_min": c[1].slider("Confianza OCR mínima", 0.0, 1.0, 0.80),
        "campos_detectados": c[1].slider("Campos detectados", 0.0, 1.0, 1.0),
        "monto_total": c[1].number_input("Monto total (CLP)", 0, 100_000_000, 119_000, step=1000),
        "rut_valido": int(c[2].checkbox("RUT válido", True)),
        "iva_cuadra": int(c[2].checkbox("IVA cuadra", True)),
        "total_cuadra": int(c[2].checkbox("Total cuadra", True)),
        "coincide_xml": int(c[2].checkbox("Coincide con XML SII", True)),
    }
    if st.button("Predecir", type="primary"):
        p = api("POST", "/api/v1/predicciones", json=v)
        st.caption(f"Respuesta del modelo ({p['motor_modelo']}) en {p['ms_modelo']} ms")
        mostrar_prediccion(p)

with t3:
    st.subheader("Últimos documentos")
    try:
        docs = api("GET", "/api/v1/documentos", params={"limite": 100})
        filas = [{"id": d["id"], "creado": d["creado"][:19].replace("T", " "), "tipo": d["tipo_documento"],
                  "estado": d["estado"], "ms_total": d["ms_total"],
                  "decision": NOMBRES.get(((d.get("resultado") or {}).get("prediccion") or {}).get("decision"), "—"),
                  "prob_error": ((d.get("resultado") or {}).get("prediccion") or {}).get("probabilidad_error")}
                 for d in docs]
        df = pd.DataFrame(filas)
        if not df.empty:
            listos = df[df.decision != "—"]
            if not listos.empty:
                st.altair_chart(alt.Chart(listos).mark_bar().encode(
                    x=alt.X("count():Q", title="Documentos"), y=alt.Y("decision:N", title=None),
                    color=alt.Color("decision:N", legend=None, scale=alt.Scale(
                        domain=list(NOMBRES.values()), range=["#0B6E79", "#C44536"]))), use_container_width=True)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("Aún no hay documentos.")
    except Exception as e:
        st.error(str(e))

with t4:
    st.subheader("Métricas del modelo (conjunto de prueba)")
    mod = (m or {}).get("modelo")
    if mod:
        rl = mod["regresion_logistica"]
        c = st.columns(5)
        for col, (n, k) in zip(c, [("Accuracy", "accuracy"), ("Precision", "precision"), ("Recall", "recall"),
                                   ("F1-score", "f1"), ("ROC-AUC", "roc_auc")]):
            col.metric(n, f"{rl[k]:.3f}")
        mc = rl["matriz_confusion"]
        st.markdown("**Matriz de confusión**")
        st.table(pd.DataFrame([[mc["tn"], mc["fp"]], [mc["fn"], mc["tp"]]],
                              index=["Real: correcto", "Real: con error"],
                              columns=["Predicho: aprobar", "Predicho: revisar"]))
        coef = pd.DataFrame({"variable": list(mod["coeficientes"]), "peso": list(mod["coeficientes"].values())})
        st.markdown("**Peso de cada variable (interpretabilidad global)**")
        st.altair_chart(alt.Chart(coef).mark_bar().encode(
            x="peso:Q", y=alt.Y("variable:N", sort="-x", title=None),
            color=alt.condition(alt.datum.peso > 0, alt.value("#C44536"), alt.value("#0B6E79"))),
            use_container_width=True)
        if mod.get("analisis_umbrales"):
            st.markdown("**Efecto del umbral de decisión**")
            st.table(pd.DataFrame({u: {"F1": v["f1"], "Recall": v["recall"], "% automático": v["pct_automatico"]}
                                   for u, v in mod["analisis_umbrales"].items()}).T)
    else:
        st.info("Métricas no disponibles.")
