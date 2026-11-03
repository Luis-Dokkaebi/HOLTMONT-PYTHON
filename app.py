import streamlit as st
import pandas as pd
import plotly.express as px

# 1. Configuración de página (DEBE SER LA PRIMERA LLAMADA STREAMLIT)
st.set_page_config(
    page_title="Reporte Tráfico B2C",
    page_icon="📈",
    layout="wide"
)

# 2. Datos In-Memory Autónomos
DEFAULT_RECORDS = [
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

# 3. Barra Lateral de Control y Carga de Archivos
st.sidebar.header("Filtros de Control")

uploaded_file = st.sidebar.file_uploader("Cargar archivo de datos (CSV o XLSX)", type=["csv", "xlsx"])

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith(".csv"):
            df_raw = pd.read_csv(uploaded_file)
        else:
            df_raw = pd.read_excel(uploaded_file)
    except Exception as e:
        st.sidebar.error(f"Error al leer el archivo cargado: {e}")
        df_raw = pd.DataFrame(DEFAULT_RECORDS)
else:
    df_raw = pd.DataFrame(DEFAULT_RECORDS)

# Tipado defensivo y preparación de columnas
df = df_raw.copy()

if 'Fecha' in df.columns:
    df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce')
    df = df.dropna(subset=['Fecha']).sort_values('Fecha')
else:
    st.error("La columna 'Fecha' no existe en los datos proporcionados.")
    st.stop()

if 'Visitantes' in df.columns:
    df['Visitantes'] = pd.to_numeric(df['Visitantes'], errors='coerce').fillna(0).astype(int)
else:
    st.error("La columna 'Visitantes' no existe en los datos proporcionados.")
    st.stop()

# Generar nombres de día en español y orden
dias_traduccion = {
    'Monday': 'Lunes',
    'Tuesday': 'Martes',
    'Wednesday': 'Miércoles',
    'Thursday': 'Jueves',
    'Friday': 'Viernes',
    'Saturday': 'Sábado',
    'Sunday': 'Domingo'
}
df['Dia_Semana'] = df['Fecha'].dt.day_name().map(dias_traduccion)
df['Dia_Num'] = df['Fecha'].dt.weekday

# Filtros reactivos en Sidebar
min_date = df['Fecha'].min().date()
max_date = df['Fecha'].max().date()

date_range = st.sidebar.date_input(
    "Seleccionar Rango de Fechas",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date
)

min_vis = int(df['Visitantes'].min())
max_vis = int(df['Visitantes'].max())

if min_vis < max_vis:
    vis_range = st.sidebar.slider(
        "Rango de Visitantes",
        min_value=min_vis,
        max_value=max_vis,
        value=(min_vis, max_vis)
    )
else:
    vis_range = (min_vis, max_vis)

dias_ordenados = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
dias_disponibles = [d for d in dias_ordenados if d in df['Dia_Semana'].unique()]

selected_dias = st.sidebar.multiselect(
    "Filtrar por Día de la Semana",
    options=dias_ordenados,
    default=dias_disponibles
)

# Aplicar filtros
df_filtrado = df.copy()

if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    start_d, end_d = date_range
    df_filtrado = df_filtrado[(df_filtrado['Fecha'].dt.date >= start_d) & (df_filtrado['Fecha'].dt.date <= end_d)]
elif isinstance(date_range, (list, tuple)) and len(date_range) == 1:
    df_filtrado = df_filtrado[df_filtrado['Fecha'].dt.date >= date_range[0]]

df_filtrado = df_filtrado[
    (df_filtrado['Visitantes'] >= vis_range[0]) & 
    (df_filtrado['Visitantes'] <= vis_range[1])
]

if selected_dias:
    df_filtrado = df_filtrado[df_filtrado['Dia_Semana'].isin(selected_dias)]
else:
    df_filtrado = df_filtrado.iloc[0:0]

st.sidebar.caption(f"Mostrando {len(df_filtrado)} de {len(df)} días registrados")

# Validación defensiva de DataFrame vacío
if df_filtrado.empty:
    st.warning("⚠️ No se encontraron registros para los filtros seleccionados. Por favor, ajusta los parámetros en la barra lateral.")
    st.stop()

# 4. Encabezado y Metadatos del Dashboard
st.title("Reporte de Tráfico de Visitantes - Canal B2C")
st.markdown("**Entidad:** ST_B2C | **Período:** 2025-12-24 a 2026-01-21")
st.info("Registro histórico del flujo diario de visitantes registrados en la pestaña ST_B2C durante el periodo del 24 de diciembre de 2025 al 21 de enero de 2026.")

# Tarjetas de KPI
total_vis = int(df_filtrado['Visitantes'].sum())
avg_vis = round(df_filtrado['Visitantes'].mean(), 1)
max_vis_val = int(df_filtrado['Visitantes'].max())
min_vis_val = int(df_filtrado['Visitantes'].min())

pico_rows = df_filtrado[df_filtrado['Visitantes'] == max_vis_val]
pico_fecha_str = pico_rows['Fecha'].dt.strftime('%Y-%m-%d').iloc[0] if not pico_rows.empty else "N/A"

col1, col2, col3, col4 = st.columns(4)
col1.metric(
    label="Total de Visitantes",
    value=f"{total_vis:,} visitantes",
    help="Suma acumulada de visitantes en el periodo filtrado"
)
col2.metric(
    label="Promedio Diario",
    value=f"{avg_vis} visitantes/día",
    help="Promedio de tráfico diario en el periodo filtrado"
)
col3.metric(
    label="Máximo Diario",
    value=f"{max_vis_val} visitantes",
    delta=f"Pico: {pico_fecha_str}",
    help="Nivel más alto alcanzado en los datos filtrados"
)
col4.metric(
    label="Mínimo Diario",
    value=f"{min_vis_val} visitantes",
    delta="- Valle",
    delta_color="inverse",
    help="Nivel más bajo registrado en los datos filtrados"
)

st.write("---")

# 5. Estructura de Pestañas
tab_b2c, tab_analisis_avanzado = st.tabs(["📊 Canal B2C (ST_B2C)", "🔍 Análisis Patrones y Distribución"])

with tab_b2c:
    st.subheader("Evolución Temporal del Tráfico Diario de Visitantes")
    
    fig_line = px.line(
        df_filtrado,
        x='Fecha',
        y='Visitantes',
        title="Evolución Temporal del Tráfico Diario de Visitantes",
        markers=True
    )
    
    fig_line.add_hline(
        y=18,
        line_dash="dash",
        line_color="red",
        annotation_text="Promedio Referencial (18)",
        annotation_position="bottom right"
    )
    
    # Anotación si el pico histórico está en la selección
    if (df_filtrado['Visitantes'] == 35).any():
        pico_idx = df_filtrado[df_filtrado['Visitantes'] == 35].index[0]
        fig_line.add_annotation(
            x=df_filtrado.loc[pico_idx, 'Fecha'],
            y=35,
            text="Pico Máximo (35)",
            showarrow=True,
            arrowhead=2,
            ax=0,
            ay=-30
        )
        
    fig_line.update_layout(
        legend=dict(orientation='h', yanchor='bottom', y=-0.25, xanchor='center', x=0.5),
        xaxis_title="Fecha",
        yaxis_title="Visitantes"
    )
    st.plotly_chart(fig_line, width="stretch")
    
    st.subheader("Volumen Diario de Visitantes Registrados")
    fig_bar = px.bar(
        df_filtrado,
        x='Fecha',
        y='Visitantes',
        color='Visitantes',
        color_continuous_scale='Viridis',
        text_auto=True,
        title="Volumen Diario de Visitantes Registrados"
    )
    fig_bar.update_layout(
        legend=dict(orientation='h', yanchor='bottom', y=-0.25, xanchor='center', x=0.5),
        xaxis_title="Fecha",
        yaxis_title="Visitantes"
    )
    st.plotly_chart(fig_bar, width="stretch")
    
    with st.expander("📁 Explorar Registro de Datos Crudos (ST_B2C)", expanded=False):
        df_display = df_filtrado[['Fecha', 'Dia_Semana', 'Visitantes']].sort_values(by='Fecha', ascending=False)
        
        st.dataframe(
            df_display,
            width="stretch",
            column_config={
                "Fecha": st.column_config.DatetimeColumn("Fecha", format="YYYY-MM-DD"),
                "Dia_Semana": "Día de la Semana",
                "Visitantes": st.column_config.ProgressColumn(
                    "Visitantes",
                    min_value=0,
                    max_value=40,
                    format="%d visitantes"
                )
            }
        )
        
        csv_data = df_display.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Descargar Datos Filtrados (CSV)",
            data=csv_data,
            file_name="trafico_b2c_filtrado.csv",
            mime="text/csv"
        )

with tab_analisis_avanzado:
    st.subheader("Comportamiento del Tráfico por Día de la Semana")
    
    df_weekly = df_filtrado.groupby(['Dia_Num', 'Dia_Semana'])['Visitantes'].agg(['mean', 'sum', 'count']).reset_index()
    df_weekly = df_weekly.sort_values('Dia_Num')
    df_weekly['Promedio'] = df_weekly['mean'].round(1)
    
    fig_weekly = px.bar(
        df_weekly,
        x='Dia_Semana',
        y='Promedio',
        text='Promedio',
        color='Promedio',
        color_continuous_scale='Blues',
        title="Promedio Diario de Visitantes por Día de la Semana"
    )
    fig_weekly.update_layout(
        legend=dict(orientation='h', yanchor='bottom', y=-0.25, xanchor='center', x=0.5),
        xaxis_title="Día de la Semana",
        yaxis_title="Promedio de Visitantes"
    )
    st.plotly_chart(fig_weekly, width="stretch")
    
    st.subheader("Análisis Estadístico de Dispersión y Outliers")
    fig_box = px.box(
        df_filtrado,
        y='Visitantes',
        points="all",
        title="Distribución y Dispersión del Tráfico Diario"
    )
    fig_box.update_layout(
        legend=dict(orientation='h', yanchor='bottom', y=-0.25, xanchor='center', x=0.5),
        yaxis_title="Cantidad de Visitantes"
    )
    st.plotly_chart(fig_box, width="stretch")
