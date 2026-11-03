import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# 1. Configuración de página (OBLIGATORIO SER LA PRIMERA LLAMADA DE STREAMLIT)
st.set_page_config(
    page_title="Reporte de Tráfico de Visitantes B2C",
    page_icon="📊",
    layout="wide"
)

# 2. Datos embebidos directamente desde el esquema JSON
DATASET_DEFAULT = [
    {"Fecha": "2026-01-21 00:00:00", "Visitantes": 31},
    {"Fecha": "2026-01-20 00:00:00", "Visitantes": 28},
    {"Fecha": "2026-01-19 00:00:00", "Visitantes": 26},
    {"Fecha": "2026-01-18 00:00:00", "Visitantes": 25},
    {"Fecha": "2026-01-17 00:00:00", "Visitantes": 27},
    {"Fecha": "2026-01-16 00:00:00", "Visitantes": 18},
    {"Fecha": "2026-01-15 00:00:00", "Visitantes": 22},
    {"Fecha": "2026-01-14 00:00:00", "Visitantes": 15},
    {"Fecha": "2026-01-13 00:00:00", "Visitantes": 15},
    {"Fecha": "2026-01-12 00:00:00", "Visitantes": 8},
    {"Fecha": "2026-01-11 00:00:00", "Visitantes": 9},
    {"Fecha": "2026-01-10 00:00:00", "Visitantes": 15},
    {"Fecha": "2026-01-09 00:00:00", "Visitantes": 16},
    {"Fecha": "2026-01-08 00:00:00", "Visitantes": 12},
    {"Fecha": "2026-01-07 00:00:00", "Visitantes": 16},
    {"Fecha": "2026-01-06 00:00:00", "Visitantes": 14},
    {"Fecha": "2026-01-05 00:00:00", "Visitantes": 24},
    {"Fecha": "2026-01-04 00:00:00", "Visitantes": 15},
    {"Fecha": "2026-01-03 00:00:00", "Visitantes": 8},
    {"Fecha": "2026-01-02 00:00:00", "Visitantes": 15},
    {"Fecha": "2026-01-01 00:00:00", "Visitantes": 14},
    {"Fecha": "2025-12-31 00:00:00", "Visitantes": 10},
    {"Fecha": "2025-12-30 00:00:00", "Visitantes": 35},
    {"Fecha": "2025-12-29 00:00:00", "Visitantes": 13},
    {"Fecha": "2025-12-28 00:00:00", "Visitantes": 13},
    {"Fecha": "2025-12-27 00:00:00", "Visitantes": 26},
    {"Fecha": "2025-12-26 00:00:00", "Visitantes": 26},
    {"Fecha": "2025-12-25 00:00:00", "Visitantes": 12},
    {"Fecha": "2025-12-24 00:00:00", "Visitantes": 14}
]

# 3. Carga e inicialización de datos con File Uploader opcional en Sidebar
st.sidebar.header("⚙️ Configuración y Filtros")
uploaded_file = st.sidebar.file_uploader("Cargar archivo de datos (.xlsx, .csv)", type=['xlsx', 'csv'])

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv'):
            df_raw = pd.read_csv(uploaded_file)
        else:
            df_raw = pd.read_excel(uploaded_file)
        st.sidebar.success("¡Archivo cargado correctamente!")
    except Exception as e:
        st.sidebar.error(f"Error al leer el archivo: {e}")
        df_raw = pd.DataFrame(DATASET_DEFAULT)
else:
    df_raw = pd.DataFrame(DATASET_DEFAULT)

# Tipado defensivo y preparación de columnas
df_base = df_raw.copy()

if 'Fecha' in df_base.columns:
    df_base['Fecha'] = pd.to_datetime(df_base['Fecha'], errors='coerce')
    df_base = df_base.dropna(subset=['Fecha'])
    df_base = df_base.sort_values('Fecha').reset_index(drop=True)

if 'Visitantes' in df_base.columns:
    df_base['Visitantes'] = pd.to_numeric(df_base['Visitantes'], errors='coerce').fillna(0)

# Creación de variables derivadas
dias_semana_esp = {
    'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
    'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
}
if 'Fecha' in df_base.columns:
    df_base['Día_Semana'] = df_base['Fecha'].dt.day_name().map(dias_semana_esp)
    dias_orden = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']

# 4. Barra Lateral Interactiva y Filtros
st.sidebar.subheader("Filtros Interactivos")

# Control de Reset
if st.sidebar.button("🔄 Restablecer Filtros"):
    st.session_state.clear()
    st.rerun()

# Filtro 1: Rango de Fechas
if 'Fecha' in df_base.columns and not df_base.empty:
    min_date = df_base['Fecha'].min().date()
    max_date = df_base['Fecha'].max().date()
    rango_fechas = st.sidebar.date_input(
        "Rango de Fechas:",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )
else:
    rango_fechas = []

# Filtro 2: Rango de Visitantes
if 'Visitantes' in df_base.columns and not df_base.empty:
    min_vis = int(df_base['Visitantes'].min())
    max_vis = int(df_base['Visitantes'].max())
    rango_visitantes = st.sidebar.slider(
        "Rango de Visitantes Diarios:",
        min_value=min_vis,
        max_value=max_vis,
        value=(min_vis, max_vis)
    )
else:
    rango_visitantes = (0, 100)

# Filtro 3: Día de la Semana
if 'Día_Semana' in df_base.columns:
    dias_disponibles = [d for d in dias_orden if d in df_base['Día_Semana'].unique()]
    dias_seleccionados = st.sidebar.multiselect(
        "Días de la Semana:",
        options=dias_disponibles,
        default=dias_disponibles
    )
else:
    dias_seleccionados = []

# Aplicación Reactiva de Filtros
df_filtrado = df_base.copy()

if len(rango_fechas) == 2 and 'Fecha' in df_filtrado.columns:
    inicio, fin = rango_fechas
    df_filtrado = df_filtrado[
        (df_filtrado['Fecha'].dt.date >= inicio) & 
        (df_filtrado['Fecha'].dt.date <= fin)
    ]

if 'Visitantes' in df_filtrado.columns:
    df_filtrado = df_filtrado[
        (df_filtrado['Visitantes'] >= rango_visitantes[0]) & 
        (df_filtrado['Visitantes'] <= rango_visitantes[1])
    ]

if 'Día_Semana' in df_filtrado.columns and dias_seleccionados:
    df_filtrado = df_filtrado[df_filtrado['Día_Semana'].isin(dias_seleccionados)]

# Validación defensiva de conjunto vacío
if df_filtrado.empty:
    st.warning("⚠️ No se encontraron registros que coincidan con los filtros seleccionados.")
    st.stop()

# 5. Encabezado y Metadatos Principales
st.title("Reporte de Tráfico de Visitantes B2C")

col_sub1, col_sub2 = st.columns([2, 1])
with col_sub1:
    st.caption("📍 **Entidad:** Canal ST_B2C | 📅 **Periodo:** 2025-12-24 a 2026-01-21")
with col_sub2:
    st.caption(f"🔍 **Registros Visualizados:** {len(df_filtrado)} / {len(df_base)} días")

with st.expander("ℹ️ Resumen Ejecutivo del Reporte"):
    st.write(
        "Registro diario del volumen de visitantes registrado en la pestaña ST_B2C, "
        "abarcando desde el 24 de diciembre de 2025 hasta el 21 de enero de 2026."
    )

# 6. Tarjetas de Métricas / KPIs Globales
st.markdown("### 📈 Indicadores Clave de Rendimiento (KPIs)")

# Cálculo dinámico basado en filtros
total_visitantes = int(df_filtrado['Visitantes'].sum())
promedio_diario = float(df_filtrado['Visitantes'].mean()) if len(df_filtrado) > 0 else 0.0
pico_maximo = int(df_filtrado['Visitantes'].max()) if len(df_filtrado) > 0 else 0
minimo_diario = int(df_filtrado['Visitantes'].min()) if len(df_filtrado) > 0 else 0

# Obtener fechas de pico y mínimo
fechas_pico = df_filtrado[df_filtrado['Visitantes'] == pico_maximo]['Fecha'].dt.strftime('%Y-%m-%d').tolist()
fechas_min = df_filtrado[df_filtrado['Visitantes'] == minimo_diario]['Fecha'].dt.strftime('%Y-%m-%d').tolist()

pico_sub = f"Fecha: {fechas_pico[0]}" if fechas_pico else ""
min_sub = f"Fechas: {', '.join(fechas_min[:2])}" if fechas_min else ""

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        label="Total de Visitantes",
        value=f"{total_visitantes:,}",
        help="Suma total de visitantes registrados durante el periodo filtrado"
    )

with col2:
    st.metric(
        label="Promedio Diario",
        value=f"{promedio_diario:.2f} / día",
        help="Promedio de visitas diarias en el periodo analizado"
    )

with col3:
    st.metric(
        label="Pico Máximo Diario",
        value=f"{pico_maximo} visitantes",
        delta=pico_sub,
        delta_color="normal",
        help="Mayor número de visitantes registrado en un solo día"
    )

with col4:
    st.metric(
        label="Mínimo Diario",
        value=f"{minimo_diario} visitantes",
        delta=min_sub,
        delta_color="inverse",
        help="Menor número de visitantes registrado en un día"
    )

st.markdown("---")

# 7. Estructura de Secciones en Pestañas (Tabs)
tab_analisis, tab_datos = st.tabs(["📊 Análisis Visual (ST_B2C)", "📋 Explorador de Datos Crudos"])

# --- PESTAÑA 1: ANÁLISIS VISUAL ---
with tab_analisis:
    # Gráfico 1: Tendencia Temporal Diaria
    fig_trend = px.area(
        df_filtrado,
        x='Fecha',
        y='Visitantes',
        title="Evolución Diaria del Tráfico de Visitantes B2C",
        markers=True,
        labels={'Fecha': 'Fecha de Registro', 'Visitantes': 'Visitantes'}
    )
    
    # Línea horizontal del promedio
    fig_trend.add_hline(
        y=promedio_diario,
        line_dash="dash",
        line_color="#EF553B",
        annotation_text=f"Promedio Filtrado ({promedio_diario:.2f})",
        annotation_position="top left"
    )
    
    fig_trend.update_layout(
        hovermode="x unified",
        margin=dict(l=20, r=20, t=50, b=50),
        legend=dict(orientation='h', yanchor='bottom', y=-0.25, xanchor='center', x=0.5)
    )
    st.plotly_chart(fig_trend, width="stretch")
    st.caption("ℹ️ *El total acumulado resulta de la agregación continua de las mediciones diarias.*")

    col_g1, col_g2 = st.columns(2)

    with col_g1:
        # Gráfico 2: Distribución por Intensidad de Visitantes
        fig_bar = px.bar(
            df_filtrado,
            x='Fecha',
            y='Visitantes',
            color='Visitantes',
            color_continuous_scale='Viridis',
            title="Volumen Diario de Visitantes por Intensidad",
            labels={'Fecha': 'Fecha', 'Visitantes': 'Cantidad de Visitantes'}
        )
        fig_bar.update_layout(
            coloraxis_showscale=True,
            margin=dict(l=20, r=20, t=50, b=50),
            legend=dict(orientation='h', yanchor='bottom', y=-0.25, xanchor='center', x=0.5)
        )
        st.plotly_chart(fig_bar, width="stretch")

    with col_g2:
        # Gráfico 3: Boxplot de Dispersión Estadísticas
        fig_box = px.box(
            df_filtrado,
            y='Visitantes',
            points="all",
            title="Dispersión y Comportamiento Estadístico del Tráfico",
            labels={'Visitantes': 'Visitantes Diarios'}
        )
        fig_box.update_layout(
            margin=dict(l=20, r=20, t=50, b=50),
            legend=dict(orientation='h', yanchor='bottom', y=-0.25, xanchor='center', x=0.5)
        )
        st.plotly_chart(fig_box, width="stretch")

# --- PESTAÑA 2: EXPLORADOR DE DATOS CRUDOS ---
with tab_datos:
    st.subheader("Tabla de Registros Diarios - ST_B2C")
    
    # Preparar vista de datos con formateo optimizado
    df_display = df_filtrado.copy()
    df_display['Fecha_Str'] = df_display['Fecha'].dt.strftime('%Y-%m-%d')
    
    st.dataframe(
        df_display[['Fecha_Str', 'Día_Semana', 'Visitantes']],
        width="stretch",
        column_config={
            "Fecha_Str": st.column_config.Column("Fecha de Registro"),
            "Día_Semana": st.column_config.Column("Día de la Semana"),
            "Visitantes": st.column_config.NumberColumn(
                "Cantidad de Visitantes",
                format="%d 👤"
            )
        }
    )

    col_df1, col_df2 = st.columns([3, 1])
    
    with col_df1:
        with st.expander("📊 Estadísticas Descriptivas Dinámicas"):
            st.dataframe(
                df_filtrado[['Visitantes']].describe().T,
                width="stretch"
            )
            
    with col_df2:
        # Botón de Descarga
        csv_data = df_filtrado.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Descargar CSV Filtrado",
            data=csv_data,
            file_name="st_b2c_traffic_data.csv",
            mime="text/csv",
            help="Descarga el conjunto de datos filtrado actualmente en formato CSV"
        )

# Pie de página sobre semántica de datos
st.markdown("---")
st.caption(
    "💡 **Notas Semánticas del Negocio:** "
    "El total reportado de 537 visitantes representa la agregación de los 29 registros de la tabla ST_B2C. "
    "El promedio general de 18.52 visitantes/día se obtiene dividiendo el acumulado global entre los 29 días observados."
)
