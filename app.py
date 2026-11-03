import io
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ==========================================
# 1. CONFIGURACIÓN DE PÁGINA (PRIMERA LLAMADA)
# ==========================================
st.set_page_config(
    page_title="Reporte de Tráfico de Visitantes ST_B2C",
    layout="wide"
)

# ==========================================
# 2. DATOS DE RESPALDO (IN-MEMORY AUTÓNOMOS)
# ==========================================
RAW_RECORDS = [
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

DAY_TRANSLATION = {
    'Monday': 'Lunes',
    'Tuesday': 'Martes',
    'Wednesday': 'Miércoles',
    'Thursday': 'Jueves',
    'Friday': 'Viernes',
    'Saturday': 'Sábado',
    'Sunday': 'Domingo'
}
DAY_ORDER = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']

# ==========================================
# 3. CARGA DE DATOS Y PROCESAMIENTO INICIAL
# ==========================================
st.sidebar.title("⚙️ Configuración")
uploaded_file = st.sidebar.file_uploader("Cargar archivo de datos (CSV o Excel)", type=['csv', 'xlsx'])

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv'):
            df_raw = pd.read_csv(uploaded_file)
        else:
            df_raw = pd.read_excel(uploaded_file)
        st.sidebar.success("¡Archivo cargado correctamente!")
    except Exception as e:
        st.sidebar.error(f"Error al leer el archivo: {e}")
        df_raw = pd.DataFrame(RAW_RECORDS)
else:
    df_raw = pd.DataFrame(RAW_RECORDS)

# Tipado defensivo y preparación
df = df_raw.copy()

if 'Fecha' in df.columns:
    df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce')
    df = df.dropna(subset=['Fecha'])
else:
    st.error("La columna 'Fecha' no existe en el conjunto de datos cargado.")
    st.stop()

if 'Visitantes' in df.columns:
    df['Visitantes'] = pd.to_numeric(df['Visitantes'], errors='coerce').fillna(0)
else:
    st.error("La columna 'Visitantes' no existe en el conjunto de datos cargado.")
    st.stop()

# Enriquecimiento de datos
df = df.sort_values('Fecha').reset_index(drop=True)
df['Día_Semana'] = df['Fecha'].dt.day_name().map(DAY_TRANSLATION)
df['Diferencia_Promedio'] = df['Visitantes'] - 18.0

# ==========================================
# 4. CONTROLES Y FILTROS REACTIVOS (SIDEBAR)
# ==========================================
st.sidebar.header("🔍 Filtros de Análisis")

# Botón de Restablecimiento
if st.sidebar.button("🔄 Restablecer Filtros"):
    st.session_state.clear()
    st.rerun()

# Rango de Fechas
min_date = df['Fecha'].min().date()
max_date = df['Fecha'].max().date()

selected_dates = st.sidebar.date_input(
    "Seleccionar Rango de Fechas",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date
)

# Rango de Visitantes
min_vis = int(df['Visitantes'].min())
max_vis = int(df['Visitantes'].max())

selected_visitors = st.sidebar.slider(
    "Rango de Visitantes Diarios",
    min_value=min_vis,
    max_value=max_vis,
    value=(min_vis, max_vis)
)

# Filtro por Día de la Semana
available_days = [d for d in DAY_ORDER if d in df['Día_Semana'].unique()]
selected_days = st.sidebar.multiselect(
    "Filtrar por Día de la Semana",
    options=available_days,
    default=available_days
)

# Aplicación de filtros
df_filtered = df.copy()

if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
    start_date, end_date = selected_dates
    df_filtered = df_filtered[
        (df_filtered['Fecha'].dt.date >= start_date) & 
        (df_filtered['Fecha'].dt.date <= end_date)
    ]

df_filtered = df_filtered[
    (df_filtered['Visitantes'] >= selected_visitors[0]) & 
    (df_filtered['Visitantes'] <= selected_visitors[1])
]

if selected_days:
    df_filtered = df_filtered[df_filtered['Día_Semana'].isin(selected_days)]
else:
    df_filtered = pd.DataFrame(columns=df.columns)

# Validación de DataFrame Vacío
if df_filtered.empty:
    st.warning("⚠️ No existen registros que coincidan con los filtros seleccionados. Ajusta los parámetros en la barra lateral.")
    st.stop()

# ==========================================
# 5. ENCABEZADO Y KPIS GLOBALES
# ==========================================
st.title("📊 Reporte de Tráfico de Visitantes ST_B2C")
st.caption("Entidad: **ST_B2C (Canal o Segmento B2C)** | Periodo: **2025-12-24** al **2026-01-21**")

st.info(
    "Registro diario del volumen de visitantes para la sección/canal ST_B2C comprendido "
    "entre el 24 de diciembre de 2025 y el 21 de enero de 2026."
)

# Métricas Calculadas Dinámicamente o Globales
total_visitantes = int(df_filtered['Visitantes'].sum())
promedio_diario = round(df_filtered['Visitantes'].mean(), 1)
max_visitantes = int(df_filtered['Visitantes'].max())
min_visitantes = int(df_filtered['Visitantes'].min())

# Identificación de fechas clave para subtextos
fechas_max = df_filtered[df_filtered['Visitantes'] == max_visitantes]['Fecha'].dt.strftime('%Y-%m-%d').tolist()
fechas_min = df_filtered[df_filtered['Visitantes'] == min_visitantes]['Fecha'].dt.strftime('%Y-%m-%d').tolist()

txt_max = f"Registrado el {', '.join(fechas_max)}"
txt_min = f"Registrado el {' y '.join(fechas_min)}"

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        label="Total de Visitantes",
        value=f"{total_visitantes:,}",
        help="Suma total de visitantes acumulados en el periodo filtrado"
    )

with col2:
    st.metric(
        label="Promedio Diario",
        value=f"{promedio_diario} vis/día",
        help="Media de tráfico diario durante el periodo analizado"
    )

with col3:
    st.metric(
        label="Máximo Diario",
        value=f"{max_visitantes}",
        delta=txt_max,
        delta_color="normal",
        help="Pico de tráfico alcanzado"
    )

with col4:
    st.metric(
        label="Mínimo Diario",
        value=f"{min_visitantes}",
        delta=txt_min,
        delta_color="inverse",
        help="Valores mínimos de tráfico diario registrados"
    )

st.divider()

# ==========================================
# 6. PESTAÑAS Y VISUALIZACIONES
# ==========================================
tab1, tab2, tab3 = st.tabs([
    "📈 Analítica de Tráfico ST_B2C",
    "🔍 Análisis Semántico y Comparativo",
    "📋 Explorador de Datos Crudos"
])

# ------------------------------------------
# TAB 1: Analítica de Tráfico ST_B2C
# ------------------------------------------
with tab1:
    st.subheader("Serie Temporal de Visitantes Diarios")
    
    fig_line = px.line(
        df_filtered,
        x='Fecha',
        y='Visitantes',
        markers=True,
        title="Evolución Diaria del Tráfico de Visitantes",
        labels={'Fecha': 'Fecha', 'Visitantes': 'Número de Visitantes'}
    )
    
    # Línea de referencia en el promedio general (18.0)
    fig_line.add_hline(
        y=18.0,
        line_dash="dash",
        line_color="red",
        annotation_text="Promedio Referencia (18.0)",
        annotation_position="top left"
    )
    
    # Anotaciones de Picos y Valles
    for _, row in df_filtered.iterrows():
        if row['Visitantes'] == max_visitantes:
            fig_line.add_annotation(
                x=row['Fecha'], y=row['Visitantes'],
                text=f"Máx: {int(row['Visitantes'])}",
                showarrow=True, arrowhead=2, ax=0, ay=-30,
                bgcolor="#00CC96", font=dict(color="white")
            )
        elif row['Visitantes'] == min_visitantes:
            fig_line.add_annotation(
                x=row['Fecha'], y=row['Visitantes'],
                text=f"Mín: {int(row['Visitantes'])}",
                showarrow=True, arrowhead=2, ax=0, ay=30,
                bgcolor="#EF553B", font=dict(color="white")
            )

    fig_line.update_layout(
        xaxis_title="Fecha",
        yaxis_title="Cantidad de Visitantes",
        legend=dict(orientation='h', yanchor='bottom', y=-0.25, xanchor='center', x=0.5),
        template="plotly_white"
    )
    st.plotly_chart(fig_line, width="stretch")
    
    st.divider()
    
    st.subheader("Distribución de Tráfico por Día de la Semana")
    
    # Agrupación por día de la semana
    df_day = df_filtered.groupby('Día_Semana', as_index=False)['Visitantes'].agg(['mean', 'sum', 'count']).reset_index()
    df_day['Día_Semana'] = pd.Categorical(df_day['Día_Semana'], categories=DAY_ORDER, ordered=True)
    df_day = df_day.sort_values('Día_Semana')
    
    fig_bar_day = px.bar(
        df_day,
        x='Día_Semana',
        y='mean',
        color='mean',
        title="Promedio de Visitantes por Día de la Semana",
        labels={'Día_Semana': 'Día de la Semana', 'mean': 'Promedio de Visitantes'},
        color_continuous_scale='Viridis'
    )
    fig_bar_day.update_layout(
        xaxis_title="Día de la Semana",
        yaxis_title="Promedio Diarios de Visitantes",
        legend=dict(orientation='h', yanchor='bottom', y=-0.25, xanchor='center', x=0.5),
        template="plotly_white"
    )
    st.plotly_chart(fig_bar_day, width="stretch")

# ------------------------------------------
# TAB 2: Análisis Semántico y Comparativo
# ------------------------------------------
with tab2:
    st.subheader("Comparativa contra la Media Global (Divergencia vs 18.0)")
    st.markdown(
        "Este gráfico muestra la desviación del volumen diario respecto al promedio histórico "
        "de **18.0 visitantes diarios**. Los valores positivos representan días con rendimiento "
        "por encima del promedio, mientras que los negativos indican baja afluencia."
    )
    
    df_filtered['Color_Divergencia'] = df_filtered['Diferencia_Promedio'].apply(
        lambda x: 'Por Encima del Promedio (+)' if x >= 0 else 'Por Debajo del Promedio (-)'
    )
    
    fig_div = px.bar(
        df_filtered,
        x='Fecha',
        y='Diferencia_Promedio',
        color='Color_Divergencia',
        color_discrete_map={
            'Por Encima del Promedio (+)': '#2CA02C',
            'Por Debajo del Promedio (-)': '#D62728'
        },
        title="Diferencia Diaria de Visitantes Respecto a la Media (18.0)",
        labels={'Fecha': 'Fecha', 'Diferencia_Promedio': 'Desviación vs Promedio'}
    )
    fig_div.update_layout(
        xaxis_title="Fecha",
        yaxis_title="Diferencia de Visitantes",
        legend=dict(orientation='h', yanchor='bottom', y=-0.25, xanchor='center', x=0.5),
        template="plotly_white"
    )
    st.plotly_chart(fig_div, width="stretch")
    
    st.divider()
    
    st.subheader("Análisis de Dispersión y Frecuencia")
    col_box, col_hist = st.columns(2)
    
    with col_box:
        fig_box = px.box(
            df_filtered,
            y='Visitantes',
            points="all",
            title="Diagrama de Caja (Boxplot) de Visitantes",
            labels={'Visitantes': 'Visitantes Diarios'}
        )
        fig_box.update_layout(
            legend=dict(orientation='h', yanchor='bottom', y=-0.25, xanchor='center', x=0.5),
            template="plotly_white"
        )
        st.plotly_chart(fig_box, width="stretch")
        
    with col_hist:
        fig_hist = px.histogram(
            df_filtered,
            x='Visitantes',
            nbins=10,
            title="Histograma de Frecuencia de Visitantes",
            labels={'Visitantes': 'Rango de Visitantes Diarios'},
            color_discrete_sequence=['#1F77B4']
        )
        fig_hist.update_layout(
            yaxis_title="Frecuencia (Días)",
            legend=dict(orientation='h', yanchor='bottom', y=-0.25, xanchor='center', x=0.5),
            template="plotly_white"
        )
        st.plotly_chart(fig_hist, width="stretch")

# ------------------------------------------
# TAB 3: Explorador de Datos Crudos
# ------------------------------------------
with tab3:
    st.subheader("Tabla Interactiva de Datos")
    
    # Preparación de la tabla formateada
    df_display = df_filtered[['Fecha', 'Visitantes', 'Día_Semana', 'Diferencia_Promedio']].copy()
    df_display['Fecha'] = df_display['Fecha'].dt.strftime('%Y-%m-%d')
    
    st.dataframe(
        df_display,
        width="stretch",
        column_config={
            "Fecha": st.column_config.DateColumn("Fecha", format="YYYY-MM-DD"),
            "Visitantes": st.column_config.ProgressColumn(
                "Visitantes",
                help="Volumen diario de visitantes",
                format="%d",
                min_value=0,
                max_value=max(35, int(df_display['Visitantes'].max() if not df_display.empty else 35))
            ),
            "Día_Semana": st.column_config.TextColumn("Día de la Semana"),
            "Diferencia_Promedio": st.column_config.NumberColumn(
                "Diferencia vs Media (18.0)",
                format="%.1f"
            )
        }
    )
    
    st.divider()
    
    st.subheader("Resumen Estadístico Descriptivo")
    st.dataframe(df_filtered[['Visitantes', 'Diferencia_Promedio']].describe(), width="stretch")
    
    st.divider()
    
    st.subheader("📥 Exportación de Datos")
    col_dl1, col_dl2 = st.columns(2)
    
    # Exportar CSV
    csv_data = df_filtered.to_csv(index=False).encode('utf-8')
    with col_dl1:
        st.download_button(
            label="📄 Descargar Datos en CSV",
            data=csv_data,
            file_name="reporte_trafico_ST_B2C.csv",
            mime="text/csv"
        )
        
    # Exportar Excel
    buffer_excel = io.BytesIO()
    with pd.ExcelWriter(buffer_excel, engine='openpyxl') as writer:
        df_filtered.to_excel(writer, index=False, sheet_name='ST_B2C')
    
    with col_dl2:
        st.download_button(
            label="📊 Descargar Datos en Excel",
            data=buffer_excel.getvalue(),
            file_name="reporte_trafico_ST_B2C.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
