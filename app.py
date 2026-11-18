import io
import pandas as pd
import plotly.express as px
import streamlit as st

# 1. Configuración de la página (DEBE ser la primera llamada de Streamlit)
st.set_page_config(page_title="Reporte de Visitantes B2C", layout="wide")

# 2. Datos embebidos por defecto
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
    {"Fecha": "2025-12-24 00:00:00", "Visitantes": 14},
]

# 3. Carga de datos y Sidebar File Uploader
st.sidebar.header("📁 Carga de Datos")
uploaded_file = st.sidebar.file_uploader(
    "Subir archivo personalizado", type=["csv", "xlsx"]
)

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith(".csv"):
            df_raw = pd.read_csv(uploaded_file)
        else:
            df_raw = pd.read_excel(uploaded_file)
    except Exception as e:
        st.sidebar.error(f"Error al leer el archivo: {e}")
        df_raw = pd.DataFrame(DEFAULT_RECORDS)
else:
    df_raw = pd.DataFrame(DEFAULT_RECORDS)

# Validaciones defensivas y preparación de datos
if "Fecha" not in df_raw.columns or "Visitantes" not in df_raw.columns:
    st.error(
        "El conjunto de datos debe incluir obligatoriamente las columnas"
        " 'Fecha' y 'Visitantes'."
    )
    st.stop()

df = df_raw.copy()
df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
df["Visitantes"] = pd.to_numeric(df["Visitantes"], errors="coerce")
df = df.dropna(subset=["Fecha", "Visitantes"])

if df.empty:
    st.error("No hay registros válidos para procesar.")
    st.stop()

df = df.sort_values(by="Fecha", ascending=True).reset_index(drop=True)

# Mapeo de día de la semana
dias_map = {
    0: "Lunes",
    1: "Martes",
    2: "Miércoles",
    3: "Jueves",
    4: "Viernes",
    5: "Sábado",
    6: "Domingo",
}
df["Día"] = df["Fecha"].dt.weekday.map(dias_map)

# 4. Encabezado Principal y Metadatos
st.title("Reporte de Visitantes B2C")
st.caption("Tráfico de Visitantes - Canal B2C (ST_B2C)")

with st.expander("ℹ️ Resumen Ejecutivo y Alcance del Reporte"):
    st.write(
        "Registro diario del volumen de visitantes en la pestaña ST_B2C"
        " abarcando desde finales de diciembre de 2025 hasta la tercera semana"
        " de enero de 2026."
    )
    st.write(
        "**Rango de Fechas Oficial del Reporte:** 2025-12-24 al 2026-01-21"
    )

# 5. Barra Lateral de Filtros Interactivos
st.sidebar.header("🔍 Filtros de Segmentación")

min_date = df["Fecha"].min().date()
max_date = df["Fecha"].max().date()

date_range = st.sidebar.date_input(
    "Seleccionar Rango de Fechas",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
)

min_vis = int(df["Visitantes"].min())
max_vis = int(df["Visitantes"].max())

vis_range = st.sidebar.slider(
    "Filtrar por Rango de Visitantes",
    min_value=min_vis,
    max_value=max_vis,
    value=(min_vis, max_vis),
)

dias_disponibles = [
    "Lunes",
    "Martes",
    "Miércoles",
    "Jueves",
    "Viernes",
    "Sábado",
    "Domingo",
]
dias_seleccionados = st.sidebar.multiselect(
    "Días de la Semana",
    options=dias_disponibles,
    default=dias_disponibles,
)

# Aplicación de Filtros
if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    start_date, end_date = date_range
    df_filtrado = df[
        (df["Fecha"].dt.date >= start_date) & (df["Fecha"].dt.date <= end_date)
    ]
else:
    df_filtrado = df.copy()

df_filtrado = df_filtrado[
    (df_filtrado["Visitantes"] >= vis_range[0])
    & (df_filtrado["Visitantes"] <= vis_range[1])
]

df_filtrado = df_filtrado[df_filtrado["Día"].isin(dias_seleccionados)]

# Validación de DataFrame Vacío
if df_filtrado.empty:
    st.warning(
        "⚠️ No hay datos que coincidan con los filtros seleccionados. Por"
        " favor, ajusta los criterios en la barra lateral."
    )
    st.stop()

# 6. Tarjetas de Métricas (KPIs Globales / Dinámicos)
col1, col2, col3, col4 = st.columns(4)

total_acumulado = int(df_filtrado["Visitantes"].sum())
promedio_diario = round(df_filtrado["Visitantes"].mean(), 1)
maximo_diario = int(df_filtrado["Visitantes"].max())
minimo_diario = int(df_filtrado["Visitantes"].min())

fecha_max = (
    df_filtrado.loc[df_filtrado["Visitantes"].idxmax(), "Fecha"].strftime(
        "%Y-%m-%d"
    )
    if not df_filtrado.empty
    else "N/A"
)

with col1:
    st.metric(
        label="Total de Visitantes Acumulados",
        value=f"{total_acumulado:,} visitantes",
        help="Suma total de visitantes registrados en el periodo seleccionado",
    )

with col2:
    st.metric(
        label="Promedio Diario de Visitantes",
        value=f"{promedio_diario} visitantes/día",
        help="Promedio diario durante el periodo seleccionado",
    )

with col3:
    st.metric(
        label="Máximo Diario de Visitantes",
        value=f"{maximo_diario} visitantes",
        help=f"Registrado en la fecha {fecha_max}",
    )

with col4:
    st.metric(
        label="Mínimo Diario de Visitantes",
        value=f"{minimo_diario} visitantes",
        help="Valor mínimo en el rango seleccionado",
    )

st.markdown("---")

# 7. Pestañas de Navegación
tab1, tab2 = st.tabs(
    ["📊 Análisis y Tendencias B2C", "📋 Datos Crudos y Exportación"]
)

with tab1:
    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        # Gráfico 1: Evolución Temporal
        fig_line = px.line(
            df_filtrado,
            x="Fecha",
            y="Visitantes",
            markers=True,
            title="Evolución Temporal del Tráfico",
            labels={
                "Fecha": "Fecha del Registro",
                "Visitantes": "Volumen de Visitantes",
            },
        )
        fig_line.add_hline(
            y=promedio_diario,
            line_dash="dash",
            line_color="red",
            annotation_text=f"Promedio ({promedio_diario})",
            annotation_position="bottom right",
        )
        fig_line.update_layout(
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=-0.25,
                xanchor="center",
                x=0.5,
            )
        )
        st.plotly_chart(fig_line, width="stretch")

    with col_chart2:
        # Gráfico 2: Comportamiento Diario (Barras)
        fig_bar = px.bar(
            df_filtrado,
            x="Fecha",
            y="Visitantes",
            color="Visitantes",
            color_continuous_scale="Viridis",
            title="Comportamiento y Distribución Diaria",
            labels={
                "Fecha": "Fecha del Registro",
                "Visitantes": "Volumen de Visitantes",
            },
        )
        fig_bar.update_layout(
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=-0.25,
                xanchor="center",
                x=0.5,
            )
        )
        st.plotly_chart(fig_bar, width="stretch")

    # Gráfico 3: Análisis de Distribución (Box Plot)
    fig_box = px.box(
        df_filtrado,
        y="Visitantes",
        points="all",
        title="Análisis de Distribución y Dispersión (Box Plot)",
        labels={"Visitantes": "Volumen de Visitantes"},
    )
    fig_box.update_layout(
        legend=dict(
            orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5
        )
    )
    st.plotly_chart(fig_box, width="stretch")

with tab2:
    st.subheader("Visor de Datos de Tráfico B2C")

    # Configuración de Dataframe visual
    df_display = df_filtrado[["Fecha", "Día", "Visitantes"]].copy()

    st.dataframe(df_display, width="stretch")

    st.markdown("### 📈 Estadísticas Descriptivas Rápidas")
    st.write(df_filtrado["Visitantes"].describe())

    # Exportación de datos
    csv_data = df_filtrado.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Descargar Datos Filtrados (CSV)",
        data=csv_data,
        file_name="visitantes_b2c_filtrado.csv",
        mime="text/csv",
    )
