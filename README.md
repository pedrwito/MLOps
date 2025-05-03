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

### Componentes Propuestos a Agregar

Además de lo mencionado, se planea incorporar los siguientes elementos:

1. **Experimentación en Jupyter Notebook**  
   - Realizar un experimento inicial para determinar el primer modelo ganador, probando diversas arquitecturas y estrategias de búsqueda de hiperparámetros.  
   - Todo el seguimiento del experimento se llevará a cabo en MLflow para tener un registro completo de las métricas y resultados.

2. **DAG para Clasificación en Batch**  
   - Agregar un DAG que procese lotes de datos para realizar la clasificación masiva de forma periódica o bajo demanda.

3. **Contenerización del Modelo de Predicción**  
   - Levantar el servicio de predicción en un contenedor Docker, con la configuración necesaria de networking y gestión de recursos.

4. **Exposición del Modelo a través de API REST**  
   - Implementar una API REST que exponga endpoints para la clasificación individual, consulta del estado del modelo y métricas de rendimiento.  
   - Documentación automática mediante herramientas como Swagger/OpenAPI.

5. **DAG para Monitoreo del Rendimiento**  
   - Un DAG adicional que se ejecute semanalmente, junto al DAG de reentrenamiento, para evaluar el desempeño del modelo en producción.  
   - Este DAG se encargará de detectar degradación (drift) en los datos, evaluar la evolución de las métricas y, en consecuencia, determinar la necesidad de ajustes o reentrenamientos adicionales.

## Registro y Monitoreo

El sistema cuenta con un exhaustivo registro de información en MLflow:

- **Datos de Entrada**:  
  - Estadísticas descriptivas, distribuciones de features, detección de outliers y porcentaje de valores faltantes.

- **Rendimiento del Modelo**:  
  - Métricas de clasificación, matriz de confusión, curvas ROC/PR y análisis de errores.

- **Monitoreo Operacional**:  
  - Tiempos de respuesta, uso de recursos, tasa de errores y latencia de predicciones.

Este monitoreo no solo respalda el proceso de entrenamiento y despliegue, sino que también permite evaluar la evolución de los datos y el desempeño del modelo a lo largo del tiempo, facilitando la identificación de momentos críticos que indiquen la necesidad de ajustes.

## Preguntas al Profesor

Para afinar detalles y determinar el enfoque más adecuado en ciertos aspectos, se plantean las siguientes preguntas:

- **Sobre el Feature Engineering:**  
  - ¿Es recomendable agregar un experimento específico para el feature engineering?  
  - ¿Resulta mejor separar este análisis en un notebook independiente o integrarlo en el flujo de experimentación actual?  
  - En cuanto a las variables a loguear, se plantea registrar la descripción de los datos (métricas estadísticas, tipo de dato, porcentaje de valores faltantes) y generar gráficos de histogramas para visualizar distribuciones. ¿Les parece adecuado este enfoque?

- **Sobre el Logueo de Métricas en Nuevos Datos:**  
  - Al traer datos nuevos a través de los DAGs de EL o LT, ¿considera conveniente volver a registrar ciertas métricas del dataset?  
  - La idea es poder evaluar la evolución de los datos en el tiempo para detectar cambios en la distribución o señales de degradación en el desempeño del modelo, lo que facilitaría la toma de decisiones para reentrenamientos o ajustes en la arquitectura. ¿Cuál es su opinión al respecto?

---

Este documento detalla tanto la infraestructura actual como las mejoras proyectadas, resaltando la necesidad de un monitoreo continuo y el registro sistemático en MLflow para tomar decisiones informadas acerca de la evolución y mantenimiento del modelo. Se agradece cualquier comentario o sugerencia que permita afinar estos enfoques y lograr una implementación robusta y eficaz.
