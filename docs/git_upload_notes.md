# Notas para subir el repositorio a GitHub

Este archivo documenta las decisiones tomadas para evitar subir datos grandes o sensibles
al repositorio remoto y contiene los comandos usados para inicializar el repositorio local.

Archivos/carpetas excluidos (por `.gitignore`):

- `data/raw/`, `data/processed/`, `data/external/` (se preservan solo `.gitkeep` cuando exista)
- `outputs/figures/*`, `outputs/models/*`, `outputs/reports/*` (solo `.gitkeep` permitidos)
- entornos virtuales: `env/`, `.venv/`, etc.
- archivos binarios y raster: `*.tif`, `*.shp`, `*.gpkg`, etc.
- modelos: `*.pkl`, `*.h5`, `*.pt`, `*.pth`, `*.joblib`
- archivos de configuración local: `.env`

Comandos recomendados para inicializar y subir (PowerShell):

```powershell
cd C:\Users\Carloto\Desktop\laboratorio_integrador
git init
# opcional: configurar nombre/email local para este repo
git config user.name "Tu Nombre"
git config user.email "tu@ejemplo.com"

# Añade .gitignore y commitea primero para que las exclusiones se respeten
git add .gitignore
git commit -m "Add .gitignore"

# Añade todos los archivos no ignorados
git add -A
git commit -m "Initial commit: add project files per guide"

# Crear repo remoto en GitHub (puede hacerse vía web), luego:
# git remote add origin https://github.com/usuario/nombre-repo.git
# git branch -M main
# git push -u origin main
```

Si archivo(s) grandes o sensibles ya quedaron rastreados por accidente, use:

```powershell
# Eliminar del índice pero mantener en disco
git rm --cached path/to/file
git commit -m "Remove large file from index"

# Para reescribir el historial remoto (avanzado), usar filter-repo o BFG (documentar antes de usar)
```

Contacto: mantenga esta copia en `docs/` y compárala con su equipo para evitar subir datos.
