# Implementación de un Modelo Productivo para Detección Estelar

##Integrantes: 

*   Pedro Lucas Barrera - a1801
*   Lautaro Gabriel Medina - a1813

En este trabajo se realizará la implementación de un modelo productivo para la empresa **ML Models and something more Inc.** enfocado en la detección categórica para determinar si el objeto detectado por un telescopio corresponde a una **estrella**, **galaxia** o **quásar**. 
Para esto se utiliza el dataset de clasificación estelar **Stellar Classification Dataset SDSS17** disponible en [@https://www.kaggle.com/datasets/fedesoriano/stellar-classification-dataset-sdss17](https://www.kaggle.com/datasets/fedesoriano/stellar-classification-dataset-sdss17).
La detección se basa en un modelo de clasificación entrenado para asignar cada objeto a una de estas tres categorías. Se simula la obtención de nuevos datos cada semana y se prueba el reentrenamiento del modelo en cada ciclo para evaluar mejoras basadas en la métrica de accuracy.

## Arquitectura del Sistema

El sistema se despliega utilizando una arquitectura de microservicios, implementada y orquestada en contenedores Docker, lo que permite una mayor flexibilidad, escalabilidad y aislamiento de cada componente.

### Componentes Actuales

Actualmente se han implementado los siguientes **DAGs de Apache Airflow**:

1. **Extract and Load (EL)**  
   - Obtención de datos astronómicos desde las fuentes y almacenamiento en el bucket `s3://data`.  
   - Se ejecuta semanalmente para simular la llegada de nuevos datos observacionales.

2. **Load and Transform (LT)**  
   - Preprocesamiento de los datos: normalización, generación de features derivados, limpieza y división en conjuntos de entrenamiento y prueba.

3. **Reentrenamiento y Evaluación**  
   - Entrenamiento de un nuevo modelo (challenger) con los datos más recientes.  
   - Comparación de su desempeño, basado en accuracy, con el modelo campeón actual.  
   - Si el modelo challenger supera al actual, se registra y almacena como el nuevo modelo ganador en MLflow.

4. **Experimentación en Jupyter Notebook**  
   - Realizar un experimento inicial para determinar el primer modelo ganador, probando diversas arquitecturas y estrategias de búsqueda de hiperparámetros.  
   - Todo el seguimiento del experimento se llevará a cabo en MLflow para tener un registro completo de las métricas y resultados.

5. **Exposición del Modelo a través de API REST**  
   - Implementar una API REST que exponga endpoints para la clasificación individual, consulta del estado del modelo y métricas de rendimiento.  

## Componentes del Proyecto

Este proyecto involucra los siguientes servicios y herramientas clave:

1. **Airflow: Orquesta el pipeline ETL para procesar datos de Spotify.**

2. **MLflow: Realiza el seguimiento de los experimentos de machine learning y registra los datasets.**

3. **MinIO: Proporciona almacenamiento de objetos compatible con S3 para los datos y artefactos de MLflow.**

4. **FastAPI: Expone APIs para la inferencia del modelo y la gestión de datasets.**


##  Proyecto de Orquestación y ML con Airflow, MLflow y FastAPI

Este proyecto integra varios servicios para el procesamiento de datos, entrenamiento de modelos y exposición de APIs. A continuación se detallan los componentes y sus accesos.

---

###  Componentes del Proyecto

- **Airflow**: Orquesta el pipeline ETL para procesar datos de Spotify.
- **MLflow**: Realiza el seguimiento de los experimentos de machine learning y registra los datasets.
- **MinIO**: Proporciona almacenamiento de objetos compatible con S3 para los datos y artefactos de MLflow.
- **FastAPI**: Expone APIs para inferencia de modelos y gestión de datasets.

---

###  Detalles de Acceso a los Servicios

| Servicio   | Descripción                                             | URL                                     | Credenciales                              |
|------------|---------------------------------------------------------|-----------------------------------------|-------------------------------------------|
| **Airflow**| Administra y monitorea el pipeline ETL                  | [http://localhost:8083](http://localhost:8083) | Usuario: `airflow` <br> Contraseña: `airflow` |
| **MLflow** | Seguimiento de experimentos y registro de datasets      | [http://localhost:5000](http://localhost:5006) | *Sin autenticación*                        |
| **MinIO**  | Almacenamiento de objetos para datos y artefactos       | [http://localhost:9000](http://localhost:9009) | Access Key: `minio` <br> Secret Key: `minio123` |
| **FastAPI**| API para predicción y manejo de datasets                | [http://localhost:8800/docs#/](http://localhost:8800/docs) | *Sin autenticación*                        |

---

### Requisitos

- Docker + Docker Compose
- Python 3.8 (solo para desarrollos locales si no usás Docker)
- `make` (opcional para automatizar tareas)


### Funcionamiento

Para visualizar correctamente los experimentos y tener el experimento ganador correr los archivos en el siguiente orden:

add_file_to_s3 -> ing_datos -> experimentLogReg -> experimentKnn -> DAG de EL -> DAG de TL -> opcional dag de retrain_model 
