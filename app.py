import streamlit as st
import pandas as pd
import plotly.express as px

# ---------------------------------------------------------
# 1. CONFIGURACIÓN DE PÁGINA (PRIMERA LLAMADA OBLIGATORIA)
# ---------------------------------------------------------
st.set_page_config(
    page_title="Seguimiento de Órdenes de Compra y Diseño de Estructura",
    page_icon="🏗️",
    layout="wide"
)

# ---------------------------------------------------------
# 2. AUTONOMÍA DE DATOS (DATOS DEFAULT EN MEMORIA)
# ---------------------------------------------------------
DEFAULT_RECORDS = [
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

# ---------------------------------------------------------
# 3. CARGA Y TRATAMIENTO DEFENSIVO DE DATOS
# ---------------------------------------------------------
st.sidebar.header("⚙️ Filtros y Configuración")

uploaded_file = st.sidebar.file_uploader(
    "Cargar nuevos datos (CSV o XLSX)", 
    type=['csv', 'xlsx']
)

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv'):
            df_base = pd.read_csv(uploaded_file)
        else:
            df_base = pd.read_excel(uploaded_file)
        st.sidebar.success("Archivo externo cargado correctamente.")
    except Exception as e:
        st.sidebar.error(f"Error al leer el archivo: {e}")
        df_base = pd.DataFrame(DEFAULT_RECORDS)
else:
    df_base = pd.DataFrame(DEFAULT_RECORDS)

# Asegurar existencia de columnas y tipado defensivo
if 'ID' in df_base.columns:
    df_base['ID'] = pd.to_numeric(df_base['ID'], errors='coerce')

if 'Responsable' in df_base.columns:
    df_base['Responsable_Clean'] = df_base['Responsable'].fillna('Sin Asignar')
else:
    df_base['Responsable_Clean'] = 'Sin Asignar'

if 'Departamento' not in df_base.columns:
    df_base['Departamento'] = 'Sin Clasificar'

if 'Estatus' not in df_base.columns:
    df_base['Estatus'] = 'Sin Estatus'

if 'Concepto' not in df_base.columns:
    df_base['Concepto'] = 'Sin Concepto'

if 'Siguiente paso' not in df_base.columns:
    df_base['Siguiente paso'] = 'Sin Detalle'

# ---------------------------------------------------------
# 4. FILTROS INTERACTIVOS (SIDEBAR)
# ---------------------------------------------------------
if st.sidebar.button("🔄 Restablecer Filtros"):
    st.session_state.clear()
    st.rerun()

deptos_opt = sorted(list(df_base['Departamento'].astype(str).unique()))
estatus_opt = sorted(list(df_base['Estatus'].astype(str).unique()))
resp_opt = sorted(list(df_base['Responsable_Clean'].astype(str).unique()))

selected_deptos = st.sidebar.multiselect("Filtrar por Departamento:", options=deptos_opt, default=deptos_opt)
selected_estatus = st.sidebar.multiselect("Filtrar por Estatus:", options=estatus_opt, default=estatus_opt)
selected_resp = st.sidebar.multiselect("Filtrar por Responsable:", options=resp_opt, default=resp_opt)

search_query = st.sidebar.text_input("🔍 Búsqueda rápida por palabra clave:", value="")

# Aplicación de filtros reactivos
df_filtered = df_base.copy()

if selected_deptos:
    df_filtered = df_filtered[df_filtered['Departamento'].astype(str).isin(selected_deptos)]

if selected_estatus:
    df_filtered = df_filtered[df_filtered['Estatus'].astype(str).isin(selected_estatus)]

if selected_resp:
    df_filtered = df_filtered[df_filtered['Responsable_Clean'].astype(str).isin(selected_resp)]

if search_query.strip():
    sq = search_query.lower()
    mask_c = df_filtered['Concepto'].astype(str).str.lower().str.contains(sq)
    mask_p = df_filtered['Siguiente paso'].astype(str).str.lower().str.contains(sq)
    df_filtered = df_filtered[mask_c | mask_p]

# ---------------------------------------------------------
# 5. ENCABEZADO PRINCIPAL Y METADATOS
# ---------------------------------------------------------
st.title("🏗️ Seguimiento de Órdenes de Compra y Diseño de Estructura")

with st.expander("ℹ️ Información General y Contexto del Proyecto", expanded=False):
    st.markdown("""
    * **Dominio:** Gestión de Proyectos / Control de Obras y Compras
    * **Fecha de Captura:** `2026-07-07`
    * **Resumen Executivo:** Bitácora de seguimiento de estatus, responsables y siguientes pasos para órdenes de compra y diseño estructural (cimentaciones, estructuras metálicas, anclas y placas).
    """)

# ---------------------------------------------------------
# 6. MÉTICAS Y KPIS GLOBALES (2 FILAS X 3 COLUMNAS)
# ---------------------------------------------------------
st.subheader("📌 Indicadores Clave de Desempeño (KPIs)")

total_regs = len(df_filtered)
cerrados = len(df_filtered[df_filtered['Estatus'] == 'Cerrado'])
criticos = len(df_filtered[df_filtered['Estatus'].isin(['Critico', 'Crítico'])])
en_proceso = len(df_filtered[df_filtered['Estatus'] == 'En proceso'])

vol_compras = len(df_filtered[df_filtered['Departamento'] == 'Compras'])
vol_diseno = len(df_filtered[df_filtered['Departamento'] == 'Diseño'])

pct_cerrado = (cerrados / total_regs * 100) if total_regs > 0 else 0
pct_critico = (criticos / total_regs * 100) if total_regs > 0 else 0
pct_proceso = (en_proceso / total_regs * 100) if total_regs > 0 else 0

# Fila 1 KPI
kpi1, kpi2, kpi3 = st.columns(3)
with kpi1:
    st.metric(
        label="Total Tareas",
        value=f"{total_regs} registros",
        help="Total de conceptos filtrados"
    )
with kpi2:
    st.metric(
        label="Tareas Cerradas",
        value=cerrados,
        delta=f"{pct_cerrado:.0f}% del total",
        delta_color="normal"
    )
with kpi3:
    st.metric(
        label="Tareas Críticas ⚠️",
        value=criticos,
        delta=f"{pct_critico:.0f}% - Atención Requerida",
        delta_color="inverse"
    )

# Fila 2 KPI
kpi4, kpi5, kpi6 = st.columns(3)
with kpi4:
    st.metric(
        label="En Proceso",
        value=en_proceso,
        delta=f"{pct_proceso:.0f}% del total",
        delta_color="off"
    )
with kpi5:
    pct_compras = (vol_compras / total_regs * 100) if total_regs > 0 else 0
    st.metric(
        label="Volumen Compras",
        value=f"{vol_compras} tareas",
        help=f"{pct_compras:.0f}% del trabajo activo"
    )
with kpi6:
    pct_diseno = (vol_diseno / total_regs * 100) if total_regs > 0 else 0
    st.metric(
        label="Volumen Diseño",
        value=f"{vol_diseno} tareas",
        help=f"{pct_diseno:.0f}% del trabajo activo"
    )

st.markdown("---")

# Validar DataFrame Vacío tras Filtros
if df_filtered.empty:
    st.warning("⚠️ No se encontraron registros con los filtros seleccionados. Por favor ajuste la selección.")
    st.stop()

# ---------------------------------------------------------
# 7. ESTRUCTURA DE PESTAÑAS (TABS)
# ---------------------------------------------------------
tab_exec, tab_table, tab_semantics = st.tabs([
    "📊 Tablero Ejecutivo & Gráficos",
    "📋 Control de Tareas (Datos Crudos)",
    "🔍 Análisis Semántico & Alertas"
])

COLOR_MAP = {
    'Critico': '#FF4B4B',
    'Crítico': '#FF4B4B',
    'En proceso': '#FFAA00',
    'Cerrado': '#00CC96'
}

# =========================================================
# TAB 1: TABLERO EJECUTIVO & GRÁFICOS
# =========================================================
with tab_exec:
    st.subheader("Visualización y Desglose Operativo")
    
    col_g1, col_g2 = st.columns(2)
    
    with col_g1:
        st.markdown("##### Estado de Tareas por Departamento")
        fig_bar = px.bar(
            df_filtered,
            x='Departamento',
            color='Estatus',
            barmode='stack',
            color_discrete_map=COLOR_MAP,
            hover_data=['Concepto', 'Responsable_Clean']
        )
        fig_bar.update_layout(
            legend=dict(orientation='h', yanchor='bottom', y=-0.25, xanchor='center', x=0.5),
            xaxis_title="Departamento",
            yaxis_title="Cantidad de Tareas"
        )
        st.plotly_chart(fig_bar, width="stretch")
        
    with col_g2:
        st.markdown("##### Carga de Trabajo por Responsable")
        fig_resp = px.bar(
            df_filtered,
            y='Responsable_Clean',
            color='Estatus',
            orientation='h',
            color_discrete_map=COLOR_MAP,
            hover_data=['Concepto', 'Departamento']
        )
        fig_resp.update_layout(
            legend=dict(orientation='h', yanchor='bottom', y=-0.25, xanchor='center', x=0.5),
            xaxis_title="Número de Tareas",
            yaxis_title="Responsable Asignado"
        )
        st.plotly_chart(fig_resp, width="stretch")

    st.markdown("##### Estructura Jerárquica de Tareas (Treemap)")
    fig_tree = px.treemap(
        df_filtered,
        path=['Departamento', 'Responsable_Clean', 'Estatus', 'Concepto'],
        color='Estatus',
        color_discrete_map=COLOR_MAP
    )
    fig_tree.update_layout(
        margin=dict(t=25, l=10, r=10, b=10)
    )
    st.plotly_chart(fig_tree, width="stretch")

# =========================================================
# TAB 2: CONTROL DE TAREAS (DATOS CRUDOS)
# =========================================================
with tab_table:
    st.subheader("Bitácora Completa de Control")
    
    cols_export = [c for c in ['ID', 'Fecha captura', 'Concepto', 'Departamento', 'Responsable_Clean', 'Estatus', 'Siguiente paso'] if c in df_filtered.columns]
    
    df_display = df_filtered[cols_export].copy()
    if 'Responsable_Clean' in df_display.columns:
        df_display.rename(columns={'Responsable_Clean': 'Responsable'}, inplace=True)
        
    st.dataframe(
        df_display,
        width="stretch",
        hide_index=True,
        column_config={
            "ID": st.column_config.NumberColumn("ID", format="%d"),
            "Fecha captura": st.column_config.TextColumn("Fecha Captura"),
            "Concepto": st.column_config.TextColumn("Concepto / Tarea", width="medium"),
            "Departamento": st.column_config.TextColumn("Departamento", width="small"),
            "Responsable": st.column_config.TextColumn("Responsable Asignado", width="medium"),
            "Estatus": st.column_config.TextColumn("Estatus Actual", width="small"),
            "Siguiente paso": st.column_config.TextColumn("Acción / Siguiente Paso", width="large")
        }
    )
    
    csv_bytes = df_display.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Descargar Vista en CSV",
        data=csv_bytes,
        file_name="bitacora_ordenes_compra.csv",
        mime="text/csv"
    )

# =========================================================
# TAB 3: ANÁLISIS SEMÁNTICO Y ALERTAS
# =========================================================
with tab_semantics:
    st.subheader("Hallazgos Clave y Relaciones Semánticas")
    
    st.warning("""
    ### 🚨 1. Atención Inmediata: Tarea Crítica Detectada
    * **Registro Afectado:** ID 2 - **OC estructura**
    * **Departamento / Responsable:** Compras | Judith Echeverria
    * **Estatus Actual:** **CRÍTICO**
    * **Detalle / Acción:** Se comparte OC el día de hoy, el anticipo se paga en 15 días, en confirmación de reunión el día de hoy con **TECOIMSA**.
    """)
    
    st.info("""
    ### 📐 2. Análisis de Dependencias en Diseño
    * **Comparativa de Avance:**
      * **Memoria de cálculo estructural (ID 5):** Estatus **Cerrado**, entrega programada para el próximo miércoles 15.
      * **Entrega diseño de estructura (ID 3):** Estatus **En proceso** a cargo de *Carlos Mendez*, sujeto a revisión y VoBo de **NIDEC**.
    """)
    
    st.warning("""
    ### 👤 3. Concentración de Carga Operativa en Compras
    * **Evaluación de Asignaciones:** *Judith Echeverria* tiene a su cargo 2 órdenes de compra estratégicas dentro del departamento de Compras:
      1. **OC estructura** (Estatus Crítico - TECOIMSA)
      2. **OC de anclas y placas** (Estatus En proceso - Cotización de materiales enviada a Luis Ramirez, tiempo de fabricación estimado: 4 días).
    """)
