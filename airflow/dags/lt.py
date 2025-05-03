import datetime
import logging
from typing import Dict, Any

import pandas as pd
import numpy as np
from astropy.time import Time
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import awswrangler as wr
import mlflow
from airflow.decorators import dag, task
from airflow.models import Variable
from airflow.exceptions import AirflowException

markdown_text = """
### TL Process for Star Classification

This DAG performs the following steps:
1. Loads raw star classification data from S3
2. Drops unnecessary columns
3. Transforms date-related features
4. Splits data into training and testing sets
5. Normalizes numerical features
6. Saves processed datasets back to S3
"""

default_args = {
    'owner': "ML Models and something more Inc.",
    'depends_on_past': False,
    'schedule_interval': None,
    'retries': 1,
    'retry_delay': datetime.timedelta(minutes=5),
    'dagrun_timeout': datetime.timedelta(minutes=15)
}

@dag(
    dag_id="tl_star_clasification_data",
    description="TL process for star classification data, separating the dataset into training and testing sets.",
    doc_md=markdown_text,
    tags=["TL", "Star Classification"],
    default_args=default_args,
    catchup=False,
)
def process_tl_star_data():

    @task.virtualenv(
        task_id="load_data",
        requirements=["ucimlrepo==0.0.3", "awswrangler==3.6.0"],
        system_site_packages=True
    )
    def load_data() -> pd.DataFrame:
        """Load raw data from S3 bucket."""
        try:
            s3_bucket = Variable.get("s3_bucket", "data")
            data_path = f"s3://{s3_bucket}/raw/star_classification_filtered.csv"
            data = wr.s3.read_csv(data_path)
            logging.info(f"Successfully loaded data with shape: {data.shape}")
            return data
        except Exception as e:
            logging.error(f"Error loading data: {str(e)}")
            raise AirflowException(f"Failed to load data: {str(e)}")

    @task.virtualenv(
        task_id="drop_columns",
        requirements=["awswrangler==3.6.0"],
        system_site_packages=True
    )
    def drop_columns(data: pd.DataFrame) -> pd.DataFrame:
        """Drop unnecessary columns from the dataset."""
        try:
            columns_to_drop = ['run_ID', 'fiber_ID', 'plate', 'field_ID', 'cam_col',
                             'rerun_ID', 'spec_obj_ID', 'obj_ID']
            data = data.drop(columns_to_drop, axis=1)
            logging.info(f"Successfully dropped columns. New shape: {data.shape}")
            return data
        except Exception as e:
            logging.error(f"Error dropping columns: {str(e)}")
            raise

    @task.virtualenv(
        task_id="transform_data",
        requirements=["awswrangler==3.6.0", "astropy"],
        system_site_packages=True
    )
    def transform_data(data: pd.DataFrame) -> pd.DataFrame:
        """Transform date-related features."""
        try:
            data['Gregorian_Date'] = Time(data['MJD'], format='mjd').to_datetime()
            data['Month'] = data['Gregorian_Date'].dt.month
            data = data.drop(['Gregorian_Date'], axis=1)
            logging.info("Successfully transformed date features")
            return data
        except Exception as e:
            logging.error(f"Error transforming data: {str(e)}")
            raise

    @task.virtualenv(
        task_id="split_data",
        requirements=["awswrangler==3.6.0", "scikit-learn"],
        system_site_packages=True
    )
    def split_data(data: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """Split data into training and testing sets."""
        try:
            train_df, test_df = train_test_split(data, test_size=0.3, random_state=42)
            logging.info(f"Training set shape: {train_df.shape}")
            logging.info(f"Testing set shape: {test_df.shape}")
            
            X_train = train_df.drop(['class'], axis=1)
            y_train = train_df['class']
            X_test = test_df.drop(['class'], axis=1)
            y_test = test_df['class']
            
            return {
                'X_train': X_train,
                'y_train': y_train,
                'X_test': X_test,
                'y_test': y_test
            }
        except Exception as e:
            logging.error(f"Error splitting data: {str(e)}")
            raise

    @task.virtualenv(
        task_id="normalize_data",
        requirements=["awswrangler==3.6.0", "scikit-learn"],
        system_site_packages=True
    )
    def normalize_data(split_data_dict: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """Normalize numerical features."""
        try:
            numerical_cols = ["alpha", "delta", "u", "g", "r", "i", "z", "redshift", "Month"]
            
            scaler = StandardScaler()
            X_train = split_data_dict['X_train']
            X_test = split_data_dict['X_test']
            
            X_train_norm = scaler.fit_transform(X_train[numerical_cols])
            X_test_norm = scaler.transform(X_test[numerical_cols])
            
            # Convert back to DataFrame to preserve column names
            X_train_norm = pd.DataFrame(X_train_norm, columns=numerical_cols, index=X_train.index)
            X_test_norm = pd.DataFrame(X_test_norm, columns=numerical_cols, index=X_test.index)
            
            return {
                'X_train_norm': X_train_norm,
                'X_test_norm': X_test_norm,
                'y_train': split_data_dict['y_train'],
                'y_test': split_data_dict['y_test'],
                'scaler': scaler
            }
        except Exception as e:
            logging.error(f"Error normalizing data: {str(e)}")
            raise

    @task.virtualenv(
        task_id="save_data",
        requirements=["awswrangler==3.6.0", "mlflow==2.9.2"],
        system_site_packages=True
    )
    def save_data(normalized_data: Dict[str, Any]):
        """Save processed datasets to S3 and scaler to MLflow."""
        try:
            s3_bucket = Variable.get("s3_bucket", "data")
            base_path = f"s3://{s3_bucket}/processed"
            
            # Save normalized datasets
            wr.s3.to_csv(
                df=normalized_data['X_train_norm'],
                path=f"{base_path}/X_train.csv",
                index=False
            )
            wr.s3.to_csv(
                df=normalized_data['X_test_norm'],
                path=f"{base_path}/X_test.csv",
                index=False
            )
            wr.s3.to_csv(
                df=normalized_data['y_train'].to_frame(),
                path=f"{base_path}/y_train.csv",
                index=False
            )
            wr.s3.to_csv(
                df=normalized_data['y_test'].to_frame(),
                path=f"{base_path}/y_test.csv",
                index=False
            )
            
            # Save scaler to MLflow
            mlflow.set_tracking_uri(Variable.get("mlflow_tracking_uri", "http://localhost:5000"))
            mlflow.set_experiment("star_classification")
            
            with mlflow.start_run(run_name="scaler_training"):
                # Log the scaler
                mlflow.sklearn.log_model(
                    normalized_data['scaler'],
                    "scaler",
                    registered_model_name="star_classification_scaler"
                )
                
                # Log some metrics about the scaler
                mlflow.log_metric("n_features", len(normalized_data['scaler'].feature_names_in_))
                mlflow.log_metric("scale_", normalized_data['scaler'].scale_.mean())
                mlflow.log_metric("mean_", normalized_data['scaler'].mean_.mean())
                
                # Log the feature names
                mlflow.log_param("feature_names", list(normalized_data['scaler'].feature_names_in_))
            
            logging.info("Successfully saved all processed datasets and scaler model")
        except Exception as e:
            logging.error(f"Error saving data: {str(e)}")
            raise AirflowException(f"Failed to save data: {str(e)}")

    # Define task dependencies
    load_data() >> drop_columns() >> transform_data() >> split_data() >> normalize_data() >> save_data()

    return process_tl_star_data

dag = process_tl_star_data()