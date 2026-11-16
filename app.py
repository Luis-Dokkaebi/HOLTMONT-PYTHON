import streamlit as st
import pandas as pd
import plotly.express as px

# REGLA TÉCNICA OBLIGATORIA 1: La PRIMERA llamada de Streamlit debe ser st.set_page_config
st.set_page_config(
    page_title="Project Activity Report - Daily Report",
    layout="wide"
)

# ---------------------------------------------------------
# DATOS AUTÓNOMOS EN MEMORIA (REGLA TÉCNICA OBLIGATORIA 2)
# ---------------------------------------------------------
metadata = {
    "document_title": "Project Activity Report - Daily Report",
    "entity_or_subject": "OPD Enrgy Tranfer / Project Frac 9",
    "date": "2026-09-22",
    "date_context": "Fecha de reporte de actividad",
    "general_summary": "Informe diario de avance de proyecto para OPD Enrgy Tranfer (Frac 9) en Mont Belvieu. Incluye condiciones del turno, control de seguridad e higiene, registros de personal y resumen de trabajo ejecutado."
}

global_kpis = [
    {"metric": "Total Manpower", "value": "6", "unit": "trabajadores", "context": "Personal total asignado durante el turno de día"},
    {"metric": "Temperature", "value": "85", "unit": "°F", "context": "Temperatura ambiental registrada durante la jornada"},
    {"metric": "JSA/JHA Reviewed", "value": "Yes", "unit": "booleano", "context": "Verificación de cumplimiento de Análisis de Seguridad en el Trabajo"},
    {"metric": "Permits Verified", "value": "Yes", "unit": "booleano", "context": "Estado de verificación de permisos requeridos"},
    {"metric": "PPE Compliance", "value": "Yes", "unit": "booleano", "context": "Cumplimiento del uso de Equipo de Protección Personal"}
]

default_job_controls = pd.DataFrame([
    {"control_parameter": "Client", "value": "OPD Enrgy Tranfer"},
    {"control_parameter": "Job #", "value": "1106"},
    {"control_parameter": "Project Name", "value": "Frac 9"},
    {"control_parameter": "Location", "value": "Mont Belvieu"},
    {"control_parameter": "Shift", "value": "Days"},
    {"control_parameter": "Day of Week", "value": "Tuesday"},
    {"control_parameter": "Weather", "value": "sunny"}
])

default_issues_log = pd.DataFrame(columns=[
    "Issue", "Impact", "Action Taken", "Responsible", "Status", "Start", "End"
])

default_work_performed = pd.DataFrame([
    {"entry_id": 1, "description": "kldkflkdlk"},
    {"entry_id": 2, "description": "kjwejfdoeojodwjoj"}
])

# ---------------------------------------------------------
# BARRA LATERAL E INTERACCIÓN DE DATOS (REGLA 3)
# ---------------------------------------------------------
st.sidebar.title("🎛️ Control Operativo")
uploaded_file = st.sidebar.file_uploader("Cargar datos externos", type=['xlsx', 'csv'])

# Carga dinámica o fallback
df_job_controls = default_job_controls.copy()
df_issues_log = default_issues_log.copy()
df_work_performed = default_work_performed.copy()

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv'):
            uploaded_df = pd.read_csv(uploaded_file)
        else:
            uploaded_df = pd.read_excel(uploaded_file)
        st.sidebar.success("Archivo cargado exitosamente.")
        # Si el dataframe subido coincide con alguna estructura se asigna, de lo contrario se complementa
        if 'description' in uploaded_df.columns:
            df_work_performed = uploaded_df
        elif 'Issue' in uploaded_df.columns:
            df_issues_log = uploaded_df
        elif 'control_parameter' in uploaded_df.columns:
            df_job_controls = uploaded_df
    except Exception as e:
        st.sidebar.error(f"Error al leer el archivo: {e}")

# Filtros interactivos en sidebar
selected_date = st.sidebar.date_input("Fecha de Filtro", pd.to_datetime(metadata["date"]))

# Extraer opciones dinámicamente si existen
shift_options = ["Days", "Nights"]
if 'control_parameter' in df_job_controls.columns and 'value' in df_job_controls.columns:
    shift_val = df_job_controls[df_job_controls['control_parameter'] == 'Shift']['value'].values
    if len(shift_val) > 0:
        shift_options = list(set(shift_options + [shift_val[0]]))

selected_shift = st.sidebar.multiselect("Seleccionar Turno (Shift)", shift_options, default=["Days"])

weather_val = "sunny"
if 'control_parameter' in df_job_controls.columns and 'value' in df_job_controls.columns:
    w_val = df_job_controls[df_job_controls['control_parameter'] == 'Weather']['value'].values
    if len(w_val) > 0:
        weather_val = w_val[0]

selected_weather = st.sidebar.selectbox("Condición Climática", [weather_val, "rainy", "cloudy", "windy"])

status_options = ["Open", "Closed", "In Progress", "Pending"]
if 'Status' in df_issues_log.columns and not df_issues_log['Status'].empty:
    status_options = list(set(status_options + df_issues_log['Status'].dropna().unique().tolist()))

selected_status = st.sidebar.multiselect("Estado de Incidencias", status_options, default=status_options)

# Información de Sistema en Sidebar
st.sidebar.markdown("---")
st.sidebar.caption("📌 **Información del Sistema:**")
st.sidebar.caption("Job #: **1106**")
st.sidebar.caption("Cliente: **OPD Enrgy Tranfer**")


# ---------------------------------------------------------
# ESTRUCTURA VISUAL SUPERIOR (HEADER Y KPIS)
# ---------------------------------------------------------
st.title(metadata["document_title"])
st.subheader(metadata["entity_or_subject"])

st.info(f"📅 **{metadata['date_context']}:** {selected_date.strftime('%Y-%m-%d')}\n\n"
        f"📝 **Resumen General:** {metadata['general_summary']}")

# Tarjetas de Métricas (5 columnas)
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric(
        label=global_kpis[0]["metric"],
        value=f"{global_kpis[0]['value']} {global_kpis[0]['unit']}",
        help=global_kpis[0]["context"]
    )
with col2:
    st.metric(
        label=global_kpis[1]["metric"],
        value=f"{global_kpis[1]['value']} {global_kpis[1]['unit']}",
        help=global_kpis[1]["context"]
    )
with col3:
    st.metric(
        label=global_kpis[2]["metric"],
        value=f"{global_kpis[2]['value']} ✅",
        help=global_kpis[2]["context"]
    )
with col4:
    st.metric(
        label=global_kpis[3]["metric"],
        value=f"{global_kpis[3]['value']} ✅",
        help=global_kpis[3]["context"]
    )
with col5:
    st.metric(
        label=global_kpis[4]["metric"],
        value=f"{global_kpis[4]['value']} ✅",
        help=global_kpis[4]["context"]
    )

st.markdown("---")

# ---------------------------------------------------------
# PESTAÑAS PRINCIPALES
# ---------------------------------------------------------
tab1, tab2, tab3 = st.tabs([
    "📋 Controles de Trabajo y Parámetros",
    "⚠️ Bitácora de Incidencias y Retrasos",
    "🏗️ Trabajo Ejecutado Hoy"
])

# ---------------------------------------------------------
# PESTAÑA 1: Controles de Trabajo
# ---------------------------------------------------------
with tab1:
    st.markdown("### Parámetros Operativos del Proyecto")
    
    # Renderizado defensivo de tabla
    if not df_job_controls.empty:
        st.dataframe(df_job_controls, width="stretch")
    else:
        st.warning("No hay parámetros de control registrados.")

    st.markdown("---")
    st.markdown("### Indicador de Cumplimiento HSE (Seguridad, Salud y Medio Ambiente)")
    
    # Gráfico 1: Cumplimiento de Seguridad HSE
    hse_metrics = pd.DataFrame({
        "Categoría": ["JSA/JHA Reviewed", "Permits Verified", "PPE Compliance"],
        "Cumplimiento": [100, 100, 100]
    })
    
    fig_hse = px.pie(
        hse_metrics,
        names="Categoría",
        values="Cumplimiento",
        hole=0.4,
        color_discrete_sequence=["#2ECC71", "#27AE60", "#1E8449"],
        title="Tasa de Cumplimiento de Protocolos HSE (100% Efectividad)"
    )
    # REGLA ESTRICTA DE SINTAXIS PLOTLY
    fig_hse.update_layout(
        legend=dict(orientation='h', yanchor='bottom', y=-0.25, xanchor='center', x=0.5)
    )
    st.plotly_chart(fig_hse, width="stretch")

# ---------------------------------------------------------
# PESTAÑA 2: Bitácora de Incidencias y Retrasos
# ---------------------------------------------------------
with tab2:
    st.markdown("### Control de Eventos e Incidencias del Turno")
    
    # Aplicar filtro defensivo si la columna existe
    df_issues_filtered = df_issues_log.copy()
    if 'Status' in df_issues_filtered.columns and not df_issues_filtered.empty:
        df_issues_filtered = df_issues_filtered[df_issues_filtered['Status'].isin(selected_status)]
    
    # Manejo defensivo de dataframe vacío (Caso borde especificado)
    if df_issues_filtered.empty:
        st.warning("No se registraron incidencias o retrasos durante este turno.")
        if st.button("➕ Registrar Nueva Incidencia / Evento Extra"):
            st.info("Formulario de registro habilitado para captura de nuevos eventos.")
    else:
        st.dataframe(df_issues_filtered, width="stretch")
        
        # Si la tabla tiene fechas válidas, renderizar Gantt
        if 'Start' in df_issues_filtered.columns and 'End' in df_issues_filtered.columns and 'Issue' in df_issues_filtered.columns:
            if df_issues_filtered['Start'].notnull().any() and df_issues_filtered['End'].notnull().any():
                fig_timeline = px.timeline(
                    df_issues_filtered,
                    x_start="Start",
                    x_end="End",
                    y="Issue",
                    color="Status" if "Status" in df_issues_filtered.columns else None,
                    title="Línea de Tiempo de Incidencias Reportadas"
                )
                fig_timeline.update_layout(
                    legend=dict(orientation='h', yanchor='bottom', y=-0.25, xanchor='center', x=0.5)
                )
                st.plotly_chart(fig_timeline, width="stretch")

# ---------------------------------------------------------
# PESTAÑA 3: Trabajo Ejecutado Hoy
# ---------------------------------------------------------
with tab3:
    st.markdown("### Tareas y Actividades Ejecutadas")
    
    if df_work_performed.empty:
        st.warning("No hay registros de trabajo ejecutado para mostrar.")
        st.stop()
    
    # Garantizar tipado numérico defensivo
    if 'entry_id' in df_work_performed.columns:
        df_work_performed['entry_id'] = pd.to_numeric(df_work_performed['entry_id'], errors='coerce')
    
    # Gráfico 2: Asignación Semántica de Personal por Tarea
    df_chart = df_work_performed.copy()
    total_manpower = 6
    num_tasks = len(df_chart) if len(df_chart) > 0 else 1
    # Distribuir de forma equitativa para representación semántica
    df_chart['personal_asignado'] = total_manpower / num_tasks
    df_chart['tarea_label'] = df_chart['entry_id'].astype(str).apply(lambda x: f"Tarea {x}")
    
    fig_work = px.bar(
        df_chart,
        x="personal_asignado",
        y="tarea_label",
        orientation="h",
        hover_data=["description"] if "description" in df_chart.columns else None,
        labels={"personal_asignado": "Personal Asignado (Manpower)", "tarea_label": "ID de Tarea"},
        title="Asignación Semántica de Personal por Tarea (Total Manpower: 6)",
        color_discrete_sequence=["#3498DB"]
    )
    
    # REGLA ESTRICTA DE SINTAXIS PLOTLY
    fig_work.update_layout(
        legend=dict(orientation='h', yanchor='bottom', y=-0.25, xanchor='center', x=0.5)
    )
    
    st.plotly_chart(fig_work, width="stretch")
    
    st.markdown("---")
    st.markdown("### Registro Detallado de Tareas Realizadas")
    
    # Tabla estructurada con column_config
    st.dataframe(
        df_work_performed,
        width="stretch",
        column_config={
            "entry_id": st.column_config.NumberColumn("ID de Entrada", format="%d"),
            "description": st.column_config.TextColumn("Descripción detallada del trabajo realizado", width="large")
        }
    )
