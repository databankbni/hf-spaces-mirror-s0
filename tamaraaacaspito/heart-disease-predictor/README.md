---
title: Heart Disease Predictor
emoji: 📊
colorFrom: purple
colorTo: yellow
sdk: gradio
python_version: '3.10'
app_file: app.py
pinned: false
license: mit
---

# Sistema Inteligente de Evaluación de Riesgo Cardíaco 🫀

Este es un proyecto académico de Aprendizaje Estadístico para la **UPAO** que predice el riesgo de padecer una enfermedad cardíaca a partir de datos clínicos del paciente.

## 🚀 Tecnologías Utilizadas
* **Backend y UI:** [Gradio](https://gradio.app/) para generar una interfaz web interactiva desde Python.
* **Machine Learning:** Modelo `Random Forest` entrenado con `scikit-learn`.
* **Dataset:** Cleveland Heart Disease Dataset (UCI Machine Learning Repository).
* **Entorno de ejecución:** Python 3.10

## 📊 Detalles del Modelo
* **Algoritmo:** Random Forest Classifier.
* **Métrica Principal (Recall):** 92.9% en la clase de riesgo (priorizando no dejar escapar pacientes enfermos, falsos negativos).
* **Umbral de Decisión:** Ajustado manualmente a `0.374` para obtener la máxima sensibilidad clínica.

## 💻 Instalación y Ejecución Local

1. Clona este repositorio o descarga los archivos.
2. Instala las dependencias necesarias:
   ```bash
   pip install -r requirements.txt
   ```
3. Ejecuta la aplicación:
   ```bash
   python app.py
   ```
4. Abre tu navegador en la dirección que indique la terminal (usualmente `http://127.0.0.1:7860`).

---

## ☁️ Despliegue en Hugging Face Spaces

La aplicación está desplegada en [Hugging Face Spaces](https://huggingface.co/spaces). A continuación se explica cómo se configuró y subió correctamente.

### 1. Configuración del Entorno (El bloque YAML)
Hugging Face utiliza el bloque de configuración (YAML) que se encuentra al inicio de este `README.md`. 
* Se especificó `python_version: '3.10'` para asegurar compatibilidad con las librerías científicas como `scikit-learn`. Si se usan versiones muy nuevas (como 3.13), el contenedor puede quedarse trabado en *Starting* por falta de binarios.
* Se delegó la versión de `sdk` (Gradio) al archivo `requirements.txt` para evitar conflictos de versiones inexistentes.

### 2. Cómo subir actualizaciones al repositorio
Para actualizar la aplicación web, solo debes hacer *commit* de tus cambios localmente y enviarlos al remoto configurado para Hugging Face (`hugginface`):

```bash
# Agregar todos los cambios realizados
git add .

# Hacer el commit de los cambios
git commit -m "Descripción de la actualización"

# Subir los cambios a la rama main de Hugging Face
git push hugginface main
```
*Al ejecutar el comando `push`, Hugging Face detectará automáticamente el cambio, volverá a instalar las dependencias (Rebuild) y reiniciará tu app en cuestión de minutos.*
