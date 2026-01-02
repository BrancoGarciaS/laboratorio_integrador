import plotly.express as px
import pandas as pd

# Componente para gráficos

def variogram_plot(df, title):
    fig = px.line(
        df,
        x="distance",
        y="semivariance",
        title=title,
        markers=True
    )
    return fig


def bar_generic(df, x, y, title):
    return px.bar(df, x=x, y=y, title=title)
