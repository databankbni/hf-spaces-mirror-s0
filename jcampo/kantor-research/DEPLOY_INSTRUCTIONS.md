# Instrucciones de Despliegue a Hugging Face Spaces

## Preparación Local (YA HECHO ✓)

Los archivos están listos en: `C:\Users\jcamp\kantor_rag\huggingface_deploy\`

Archivos creados:
- ✓ app.py (código Gradio)
- ✓ requirements.txt
- ✓ README.md
- ✓ .gitignore
- ✓ .gitattributes

## Paso 1: Copiar Base de Datos

Necesitas copiar la carpeta `database` completa:

```powershell
# En PowerShell
xcopy "C:\Users\jcamp\kantor_rag\database" "C:\Users\jcamp\kantor_rag\huggingface_deploy\database\" /E /I
```

## Paso 2: Instalar Git LFS (si no lo tienes)

Descarga e instala desde: https://git-lfs.github.com/

O con winget:
```powershell
winget install -e --id GitHub.GitLFS
```

## Paso 3: Inicializar Repositorio

```powershell
cd C:\Users\jcamp\kantor_rag\huggingface_deploy

# Inicializar git
git init

# Configurar Git LFS para archivos grandes
git lfs install
git lfs track "*.pkl"
git lfs track "*.faiss"

# Añadir todos los archivos
git add .
git commit -m "Initial commit: Kantor Research System"
```

## Paso 4: Conectar con Hugging Face

Tu Space ya existe en: https://huggingface.co/spaces/jcampo/kantor-research

```powershell
# Añadir remote (reemplaza USERNAME por tu usuario)
git remote add origin https://huggingface.co/spaces/jcampo/kantor-research

# Forzar push (sobrescribirá el código actual con errores)
git push --force origin main
```

## Paso 5: Verificar

1. Ve a: https://huggingface.co/spaces/jcampo/kantor-research
2. Espera 2-3 minutos mientras se construye
3. La app debería estar funcionando!

## Solución de Problemas

### Si Git LFS no funciona:
Hugging Face Spaces acepta archivos hasta 50GB, así que los 165MB deberían funcionar con LFS.

### Si el build falla:
Revisa los logs en la pestaña "Logs" del Space.

### Alternativa sin Git LFS:
Puedes subir los archivos directamente desde la interfaz web de Hugging Face (más lento pero funciona).

## Credenciales

Si te pide login:
```powershell
# Usuario: tu email de Hugging Face
# Password: tu token de acceso (créalo en Settings > Access Tokens)
```

## Siguiente Paso

Una vez funcionando, actualizar UptimeRobot:
- Cambiar URL de `kantor.streamlit.app` a `https://huggingface.co/spaces/jcampo/kantor-research`
