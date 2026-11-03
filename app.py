import streamlit as st
import pandas as pd
import plotly.express as px

# -----------------------------------------------------------------------------
# 1. CONFIGURACIÓN DE PÁGINA (DEBE SER LA PRIMERA LLAMADA DE STREAMLIT)
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Bitácora de Seguimiento de Compras y Diseño",
    page_icon="🏗️",
    layout="wide"
)

# -----------------------------------------------------------------------------
# 2. AUTONOMÍA DE DATOS (DATASET EMBEBIDO COMPLETO)
# -----------------------------------------------------------------------------
RAW_RECORDS = [
    {
        "ID": 1,
        "Fecha captura": "2026-07-07 00:00:00",
        "Concepto": "OC cimentaciones",
        "Departamento": "Compras",
        "Responsable": None,
        "Estatus": "Cerrado",
        "Siguiente paso": "ya se tiene cotizacion con Rangel, se comparte el dia de hoy para revision"
    },
    {
        "ID": 2,
        "Fecha captura": "2026-07-07 00:00:00",
        "Concepto": "OC estructura",
        "Departamento": "Compras",
        "Responsable": "Judith Echeverria",
        "Estatus": "Critico",
        "Siguiente paso": "Se comparte OC el dia de hoy, anticipo se paga en 15 dias, en confirmacion de reunion el dia de hoy  (TECOIMSA)"
    },
    {
        "ID": 3,
        "Fecha captura": "2026-07-07 00:00:00",
        "Concepto": "Entrega diseño de estructura",
        "Departamento": "Diseño",
        "Responsable": "Carlos Mendez",
        "Estatus": "En proceso",
        "Siguiente paso": "En proceso de revision y vobo de NIDEC"
    },
    {
        "ID": 4,
        "Fecha captura": "2026-07-07 00:00:00",
        "Concepto": "OC de anclas y placas",
        "Departamento": "Compras",
        "Responsable": "Judith Echeverria",
        "Estatus": "En proceso",
        "Siguiente paso": "Ya se comenzo cotizacion de materiales para entrega a Luis Ramirez. (tiempo de fabricacion 4 dias)"
    },
    {
        "ID": 5,
        "Fecha captura": "2026-07-07 00:00:00",
        "Concepto": "Memoria calculo estructural (estructura metalica)",
        "Departamento": "Diseño",
        "Responsable": None,
        "Estatus": "Cerrado",
        "Siguiente paso": "Se espera entrega el proximo miercoles 15"
    }
]

# -----------------------------------------------------------------------------
# 3. BARRA LATERAL (FILE UPLOADER Y FILTROS INTERACTIVOS)
# -----------------------------------------------------------------------------
st.sidebar.header("⚙️ Configuración y Filtros")

uploaded_file = st.sidebar.file_uploader("Cargar nuevo archivo (CSV o XLSX)", type=["csv", "xlsx"])

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith(".csv"):
            df_base = pd.read_csv(uploaded_file)
        else:
            df_base = pd.read_excel(uploaded_file)
        st.sidebar.success("Archivo cargado con éxito.")
    except Exception as e:
        st.sidebar.warning(f"Error al leer el archivo cargado: {e}. Se utilizarán los datos por defecto.")
        df_base = pd.DataFrame(RAW_RECORDS)
else:
    df_base = pd.DataFrame(RAW_RECORDS)

# Tipado defensivo de datos
if "ID" in df_base.columns:
    df_base["ID"] = pd.to_numeric(df_base["ID"], errors="coerce")

if "Fecha captura" in df_base.columns:
    df_base["Fecha captura"] = pd.to_datetime(df_base["Fecha captura"], errors="coerce")

if "Responsable" in df_base.columns:
    df_base["Responsable_Display"] = df_base["Responsable"].fillna("Sin Asignar")
else:
    df_base["Responsable_Display"] = "Sin Asignar"

# Opciones para filtros
deptos_opt = sorted(df_base["Departamento"].dropna().unique().tolist()) if "Departamento" in df_base.columns else []
estatus_opt = sorted(df_base["Estatus"].dropna().unique().tolist()) if "Estatus" in df_base.columns else []
resp_opt = sorted(df_base["Responsable_Display"].unique().tolist())

sel_deptos = st.sidebar.multiselect("Filtrar por Departamento:", options=deptos_opt, default=deptos_opt)
sel_estatus = st.sidebar.multiselect("Filtrar por Estatus:", options=estatus_opt, default=estatus_opt)
sel_resp = st.sidebar.multiselect("Filtrar por Responsable:", options=resp_opt, default=resp_opt)

search_query = st.sidebar.text_input("🔍 Búsqueda libre (Concepto / Siguiente paso):", "")

# Aplicar filtros interactivos
df_filtrado = df_base.copy()

if "Departamento" in df_filtrado.columns and sel_deptos:
    df_filtrado = df_filtrado[df_filtrado["Departamento"].isin(sel_deptos)]

if "Estatus" in df_filtrado.columns and sel_estatus:
    df_filtrado = df_filtrado[df_filtrado["Estatus"].isin(sel_estatus)]

if sel_resp:
    df_filtrado = df_filtrado[df_filtrado["Responsable_Display"].isin(sel_resp)]

if search_query:
    q = search_query.lower()
    c_mask = df_filtrado["Concepto"].astype(str).str.lower().str.contains(q, na=False) if "Concepto" in df_filtrado.columns else False
    s_mask = df_filtrado["Siguiente paso"].astype(str).str.lower().str.contains(q, na=False) if "Siguiente paso" in df_filtrado.columns else False
    df_filtrado = df_filtrado[c_mask | s_mask]

# Validar DataFrame vacío tras aplicar filtros
if df_filtrado.empty:
    st.warning("⚠️ No se encontraron registros que coincidan con los filtros seleccionados.")
    st.stop()

# -----------------------------------------------------------------------------
# 4. ENCABEZADO Y METADATOS INSTITUCIONALES
# -----------------------------------------------------------------------------
st.title("🏗️ Bitácora de Seguimiento de Compras y Diseño")
st.caption("📍 **Proyecto:** Seguimiento de Proyecto de Construcción y Estructuras Metálicas | 📅 **Fecha de Corte:** 2026-07-07")

st.info("ℹ️ **Resumen General:** Registro detallado del estatus y siguientes pasos de las órdenes de compra (OC) y entregables del área de diseño para el proyecto.")

# -----------------------------------------------------------------------------
# 5. REJILLA DE MÉTRICAS GLOBALES (KPIS)
# -----------------------------------------------------------------------------
total_tareas = len(df_base)
critico_cnt = len(df_base[df_base["Estatus"] == "Critico"]) if "Estatus" in df_base.columns else 0
proceso_cnt = len(df_base[df_base["Estatus"] == "En proceso"]) if "Estatus" in df_base.columns else 0
cerrado_cnt = len(df_base[df_base["Estatus"] == "Cerrado"]) if "Estatus" in df_base.columns else 0
compras_cnt = len(df_base[df_base["Departamento"] == "Compras"]) if "Departamento" in df_base.columns else 0
diseno_cnt = len(df_base[df_base["Departamento"] == "Diseño"]) if "Departamento" in df_base.columns else 0

col1, col2, col3 = st.columns(3)
with col1:
    st.metric(
        label="Total de Tareas",
        value=f"{total_tareas} tareas",
        help="Total de ítems en la lista de seguimiento"
    )
with col2:
    pct_critico = (critico_cnt / total_tareas * 100) if total_tareas > 0 else 0
    st.metric(
        label="Estatus Crítico",
        value=f"{critico_cnt} ({pct_critico:.0f}%)",
        delta="-1 Atención Inmediata",
        delta_color="inverse",
        help="OC estructura - TECOIMSA (ID 2)"
    )
with col3:
    pct_proceso = (proceso_cnt / total_tareas * 100) if total_tareas > 0 else 0
    st.metric(
        label="En Proceso",
        value=f"{proceso_cnt} ({pct_proceso:.0f}%)",
        delta="Operativo",
        delta_color="normal",
        help="Entrega diseño de estructura y OC anclas/placas"
    )

col4, col5, col6 = st.columns(3)
with col4:
    pct_cerrado = (cerrado_cnt / total_tareas * 100) if total_tareas > 0 else 0
    st.metric(
        label="Cerradas / Concluidas",
        value=f"{cerrado_cnt} ({pct_cerrado:.0f}%)",
        delta="Completado",
        delta_color="normal",
        help="OC cimentaciones y Memoria cálculo estructural"
    )
with col5:
    st.metric(
        label="Dpto. Compras",
        value=f"{compras_cnt} tareas",
        help="OC cimentaciones, OC estructura, OC de anclas y placas"
    )
with col6:
    st.metric(
        label="Dpto. Diseño",
        value=f"{diseno_cnt} tareas",
        help="Entrega diseño de estructura, Memoria cálculo estructural"
    )

st.markdown("---")

# -----------------------------------------------------------------------------
# 6. ORGANIZACIÓN POR PESTAÑAS (TABS)
# -----------------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs([
    "📊 Dashboard & Analítica", 
    "📋 Tabla de Seguimiento Operativo", 
    "🚨 Panel de Alertas Críticas"
])

COLOR_MAP = {
    "Critico": "#EF553B",
    "En proceso": "#FFA15A",
    "Cerrado": "#00CC96"
}

# -----------------------------------------------------------------------------
# TAB 1: DASHBOARD & ANALÍTICA
# -----------------------------------------------------------------------------
with tab1:
    st.subheader("Análisis Visual de Estatus y Carga de Trabajo")
    
    g_col1, g_col2 = st.columns(2)
    
    with g_col1:
        # Gráfico 1: Anillo por Estatus
        df_estatus = df_filtrado["Estatus"].value_counts().reset_index()
        df_estatus.columns = ["Estatus", "Conteo"]
        
        fig_pie = px.pie(
            df_estatus,
            names="Estatus",
            values="Conteo",
            hole=0.4,
            title="<b>Distribución por Estatus</b>",
            color="Estatus",
            color_discrete_map=COLOR_MAP
        )
        fig_pie.update_layout(
            legend=dict(orientation='h', yanchor='bottom', y=-0.25, xanchor='center', x=0.5)
        )
        st.plotly_chart(fig_pie, width="stretch")

    with g_col2:
        # Gráfico 2: Carga de trabajo por Departamento
        df_depto = df_filtrado.groupby(["Departamento", "Estatus"]).size().reset_index(name="Conteo")
        
        fig_bar_dept = px.bar(
            df_depto,
            x="Departamento",
            y="Conteo",
            color="Estatus",
            title="<b>Carga por Departamento y Estatus</b>",
            barmode="stack",
            color_discrete_map=COLOR_MAP
        )
        fig_bar_dept.update_layout(
            legend=dict(orientation='h', yanchor='bottom', y=-0.25, xanchor='center', x=0.5)
        )
        st.plotly_chart(fig_bar_dept, width="stretch")

    st.markdown("---")
    
    # Gráfico 3: Matriz de asignación por Responsable
    df_resp = df_filtrado.groupby(["Responsable_Display", "Estatus"]).size().reset_index(name="Conteo")
    
    fig_resp = px.bar(
        df_resp,
        y="Responsable_Display",
        x="Conteo",
        color="Estatus",
        orientation="h",
        title="<b>Asignación de Tareas por Responsable</b>",
        labels={"Responsable_Display": "Responsable"},
        color_discrete_map=COLOR_MAP
    )
    fig_resp.update_layout(
        legend=dict(orientation='h', yanchor='bottom', y=-0.25, xanchor='center', x=0.5)
    )
    st.plotly_chart(fig_resp, width="stretch")

# -----------------------------------------------------------------------------
# TAB 2: TABLA DE SEGUIMIENTO OPERATIVO
# -----------------------------------------------------------------------------
with tab2:
    st.subheader("Control Detallado de Entregables y Órdenes de Compra")
    
    df_tabla = df_filtrado.copy()
    if "Responsable_Display" in df_tabla.columns and "Responsable" in df_tabla.columns:
        df_tabla["Responsable"] = df_tabla["Responsable_Display"]
    
    cols_to_show = ["ID", "Fecha captura", "Concepto", "Departamento", "Responsable", "Estatus", "Siguiente paso"]
    cols_existing = [c for c in cols_to_show if c in df_tabla.columns]
    
    st.dataframe(
        df_tabla[cols_existing],
        column_config={
            "ID": st.column_config.NumberColumn("ID", format="%d"),
            "Fecha captura": st.column_config.DatetimeColumn("Fecha Captura", format="YYYY-MM-DD"),
            "Concepto": st.column_config.TextColumn("Concepto / Tarea", width="medium"),
            "Departamento": st.column_config.TextColumn("Departamento", width="small"),
            "Responsable": st.column_config.TextColumn("Responsable Asignado", width="medium"),
            "Estatus": st.column_config.SelectboxColumn(
                "Estatus Actual",
                options=["Critico", "En proceso", "Cerrado"],
                width="small"
            ),
            "Siguiente paso": st.column_config.TextColumn("Acción / Siguiente Paso", width="large")
        },
        hide_index=True,
        width="stretch"
    )
    
    st.markdown("### Exportación de Datos")
    csv_data = df_filtrado.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Exportar Seguimiento a CSV",
        data=csv_data,
        file_name="bitacora_seguimiento_compras_diseno.csv",
        mime="text/csv"
    )

# -----------------------------------------------------------------------------
# TAB 3: PANEL DE ALERTAS CRÍTICAS
# -----------------------------------------------------------------------------
with tab3:
    st.subheader("🚨 Control de Elementos Bloqueantes y Estatus Crítico")
    
    df_criticos = df_filtrado[df_filtrado["Estatus"] == "Critico"] if "Estatus" in df_filtrado.columns else pd.DataFrame()
    
    if not df_criticos.empty:
        st.warning(f"⚠️ Atención: Se identifican {len(df_criticos)} tarea(s) en estatus CRÍTICO que requieren acción inmediata.")
        
        for idx, row in df_criticos.iterrows():
            with st.container():
                st.markdown(f"### 🔴 [ID {row.get('ID', 'N/A')}] {row.get('Concepto', 'Sin concepto')}")
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    st.markdown(f"**Departamento:** {row.get('Departamento', 'N/A')}")
                with col_b:
                    st.markdown(f"**Responsable:** {row.get('Responsable_Display', 'Sin Asignar')}")
                with col_c:
                    st.markdown(f"**Fecha Captura:** {str(row.get('Fecha captura', 'N/A'))[:10]}")
                
                st.markdown("**🚨 Acción Inmediata / Siguiente Paso:**")
                st.info(f"👉 {row.get('Siguiente paso', 'Sin especificación.')}")
                st.markdown("---")
    else:
        st.success("✅ No hay tareas en estatus crítico dentro del conjunto de datos filtrado.")
