import streamlit as st
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
from sklearn.ensemble import RandomForestRegressor
from xgboost import XGBRegressor
from sklearn.neural_network import MLPRegressor
from components.dataset import load_master
from components.sidebar import render_sidebar, sidebar_down

page = render_sidebar()

# Revisar si ya existe en session_state
if "gdf_master" not in st.session_state:
    gdf_master = load_master()
    st.success("Datos cargados correctamente desde PostGIS")
    st.session_state["gdf_master"] = gdf_master
else:
    gdf_master = st.session_state["gdf_master"]


st.header("🤖 Modelos de Machine Learning")

# Dataset cargado en session_state
df = st.session_state["gdf_master"]

# Selección de variable objetivo
target = st.selectbox(
    "Seleccione la variable objetivo:",
    ["total_personas", "num_edificios", "num_amenidades"]
)

# Selección de modelo
model_type = st.selectbox(
    "Seleccione el modelo:",
    ["Random Forest", "XGBoost", "Red Neuronal"]
)

col1, col2 = st.columns(2)

with col1:
    st.subheader("Parámetros del Modelo")

    if model_type == "Random Forest":
        n_estimators = st.slider("Número de árboles:", 10, 500, 100)
        max_depth = st.slider("Profundidad máxima:", 1, 20, 5)
        min_samples_split = st.slider("Min samples split:", 2, 20, 2)

    elif model_type == "XGBoost":
        n_estimators = st.slider("Número de árboles:", 10, 500, 100)
        learning_rate = st.slider("Learning rate:", 0.01, 0.3, 0.1)
        max_depth = st.slider("Profundidad máxima:", 1, 20, 5)

    elif model_type == "Red Neuronal":
        hidden_layer_sizes = st.selectbox("Capas ocultas:", [(50,), (100,), (100,50)])
        activation = st.selectbox("Función de activación:", ["relu", "tanh", "logistic"])
        max_iter = st.slider("Iteraciones máximas:", 100, 1000, 200)

with col2:
    st.subheader("Métricas de Rendimiento")
    # Placeholder para métricas
    r2_placeholder = st.empty()
    rmse_placeholder = st.empty()
    mae_placeholder = st.empty()

# Entrenamiento
if st.button("🚀 Entrenar Modelo"):
    with st.spinner("Entrenando modelo..."):
        # Features: todas las columnas numéricas menos la target
        X = df.select_dtypes(include=[np.number]).drop(columns=[target])
        y = df[target]

        # Train/test split
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        # Inicializar modelo según selección
        if model_type == "Random Forest":
            model = RandomForestRegressor(
                n_estimators=n_estimators,
                max_depth=max_depth,
                min_samples_split=min_samples_split,
                random_state=42
            )
        elif model_type == "XGBoost":
            model = XGBRegressor(
                n_estimators=n_estimators,
                learning_rate=learning_rate,
                max_depth=max_depth,
                random_state=42
            )
        elif model_type == "Red Neuronal":
            model = MLPRegressor(
                hidden_layer_sizes=hidden_layer_sizes,
                activation=activation,
                max_iter=max_iter,
                random_state=42
            )

        # Entrenar
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)

        # Calcular métricas
        r2 = r2_score(y_test, y_pred)
        mse = mean_squared_error(y_test, y_pred) 
        rmse = np.sqrt(mse)
        mae = mean_absolute_error(y_test, y_pred)

        # Mostrar métricas
        r2_placeholder.metric("R² Score", f"{r2:.3f}")
        rmse_placeholder.metric("RMSE", f"{rmse:.2f}")
        mae_placeholder.metric("MAE", f"{mae:.2f}")

        st.success("Modelo entrenado exitosamente!")

sidebar_down()