import datetime
import logging

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
    dag_id="tl_star_classification_data",
    description="TL process for star classification data, separating the dataset into training and testing sets.",
    doc_md=markdown_text,
    tags=["TL", "Star Classification"],
    default_args=default_args,
    catchup=False,
)
def process_tl_star_data():

    @task.virtualenv(
        task_id="load_data",
        requirements=["ucimlrepo==0.0.3", "awswrangler==3.6.0", "boto3==1.34.0"],
        system_site_packages=True
    )
    def load_data():
        """Load raw data from S3 bucket."""
        import pandas as pd
        import awswrangler as wr
        import boto3
        import logging
        from airflow.models import Variable
        from airflow.exceptions import AirflowException
        
        try:
            s3_bucket = Variable.get("s3_bucket", "data")
            data_path = f"s3://{s3_bucket}/raw/star_classification_filtered.csv"
            
            # Configure S3 endpoint for Minio
            boto3_session = boto3.Session()
            s3_client = boto3_session.client(
                service_name='s3',
                endpoint_url='http://minio:9000',
                aws_access_key_id='minio',
                aws_secret_access_key='minio123'
            )
            
            data = wr.s3.read_csv(
                path=data_path,
                boto3_session=boto3_session
            )
            logging.info(f"Successfully loaded data with shape: {data.shape}")
            return data
        except Exception as e:
            logging.error(f"Error loading data: {str(e)}")
            raise AirflowException(f"Failed to load data: {str(e)}")

    @task.virtualenv(
        task_id="transform_data",
        requirements=["awswrangler==3.6.0", "pandas==1.5.3", "boto3==1.34.0"],
        system_site_packages=True
    )
    def transform_data(data):
        """Transform MJD to month using pure Python calculation."""
        import pandas as pd
        import logging
        import datetime
        from airflow.exceptions import AirflowException
        
        try:
            # MJD epoch is November 17, 1858
            mjd_epoch = datetime.datetime(1858, 11, 17)
            
            # Function to convert MJD to datetime
            def mjd_to_datetime(mjd):
                days = datetime.timedelta(days=mjd)
                return mjd_epoch + days
            
            # Apply conversion
            data['Month'] = data['MJD'].apply(lambda x: mjd_to_datetime(x).month)
            
            logging.info("Successfully transformed date features")
            return data
        except Exception as e:
            logging.error(f"Error transforming data: {str(e)}")
            raise AirflowException(f"Error transforming data: {str(e)}")

    @task.virtualenv(
        task_id="split_data",
        requirements=["awswrangler==3.6.0", "scikit-learn==1.0.2", "boto3==1.34.0"],
        system_site_packages=True
    )
    def split_data(data):
        """Split data into training, testing, and evaluation sets."""
        import pandas as pd
        import logging
        from sklearn.model_selection import train_test_split
        from airflow.exceptions import AirflowException
        
        try:
            # First split: separate out 90% for train+test and 10% for evaluation
            train_test_df, eval_df = train_test_split(data, test_size=0.10, random_state=42)
            
            # Second split: from the 90%, allocate 70/20 (which is approx 78/22 of the 90%)
            train_df, test_df = train_test_split(train_test_df, test_size=0.22, random_state=42)
            
            # Log the shapes of the three datasets
            logging.info(f"Training set shape: {train_df.shape}")
            logging.info(f"Testing set shape: {test_df.shape}")
            logging.info(f"Evaluation set shape: {eval_df.shape}")
            
            # Extract features and labels
            X_train = train_df.drop(['class'], axis=1)
            y_train = train_df['class'].tolist()
            
            X_test = test_df.drop(['class'], axis=1)
            y_test = test_df['class'].tolist()
            
            X_eval = eval_df.drop(['class'], axis=1)
            y_eval = eval_df['class'].tolist()
            
            # Convert DataFrames to dictionaries with lists
            X_train_dict = {col: X_train[col].tolist() for col in X_train.columns}
            X_test_dict = {col: X_test[col].tolist() for col in X_test.columns}
            X_eval_dict = {col: X_eval[col].tolist() for col in X_eval.columns}
            
            return {
                'X_train': X_train_dict,
                'y_train': y_train,
                'X_test': X_test_dict,
                'y_test': y_test,
                'X_eval': X_eval_dict,
                'y_eval': y_eval,
                'train_shape': train_df.shape,
                'test_shape': test_df.shape,
                'eval_shape': eval_df.shape
            }
        except Exception as e:
            logging.error(f"Error splitting data: {str(e)}")
            raise AirflowException(f"Error splitting data: {str(e)}")

    @task.virtualenv(
        task_id="normalize_data",
        requirements=["awswrangler==3.6.0", "scikit-learn==1.0.2", "boto3==1.34.0", "pandas==1.5.3", "numpy==1.24.3"],
        system_site_packages=True
    )
    def normalize_data(split_data_dict):
        """Normalize numerical features."""
        import pandas as pd
        import numpy as np
        import logging
        import pickle
        import base64
        from sklearn.preprocessing import StandardScaler
        from airflow.exceptions import AirflowException
        
        try:
            numerical_cols = ["alpha", "delta", "u", "g", "r", "i", "z", "redshift", "Month"]
            
            # Convert back to DataFrames
            X_train = pd.DataFrame(split_data_dict['X_train'])
            X_test = pd.DataFrame(split_data_dict['X_test'])
            X_eval = pd.DataFrame(split_data_dict['X_eval'])
            
            scaler = StandardScaler()
            X_train_norm = scaler.fit_transform(X_train[numerical_cols])
            X_test_norm = scaler.transform(X_test[numerical_cols])
            X_eval_norm = scaler.transform(X_eval[numerical_cols])
            
            # Convert back to DataFrame to preserve column names
            X_train_norm = pd.DataFrame(X_train_norm, columns=numerical_cols)
            X_test_norm = pd.DataFrame(X_test_norm, columns=numerical_cols)
            X_eval_norm = pd.DataFrame(X_eval_norm, columns=numerical_cols)
            
            # Convert to serializable format
            X_train_norm_dict = {col: X_train_norm[col].tolist() for col in X_train_norm.columns}
            X_test_norm_dict = {col: X_test_norm[col].tolist() for col in X_test_norm.columns}
            X_eval_norm_dict = {col: X_eval_norm[col].tolist() for col in X_eval_norm.columns}
            
            # Serialize the scaler using pickle and base64
            scaler_bytes = pickle.dumps(scaler)
            scaler_b64 = base64.b64encode(scaler_bytes).decode('utf-8')
            
            return {
                'X_train_norm': X_train_norm_dict,
                'X_test_norm': X_test_norm_dict,
                'X_eval_norm': X_eval_norm_dict,
                'y_train': split_data_dict['y_train'],
                'y_test': split_data_dict['y_test'],
                'y_eval': split_data_dict['y_eval'],
                'scaler_b64': scaler_b64
            }
        except Exception as e:
            logging.error(f"Error normalizing data: {str(e)}")
            raise AirflowException(f"Error normalizing data: {str(e)}")

    @task.virtualenv(
        task_id="save_data",
        requirements=["awswrangler==3.6.0", "mlflow==2.9.2", "boto3==1.34.0", "pandas==1.5.3", "scikit-learn==1.0.2"],
        system_site_packages=True
    )
    def save_data(normalized_data):
        """Save processed datasets to S3 and scaler to MLflow."""
        import pandas as pd
        import logging
        import mlflow
        import awswrangler as wr
        import boto3
        import pickle
        import base64
        from airflow.models import Variable
        from airflow.exceptions import AirflowException
        
        try:
            s3_bucket = Variable.get("s3_bucket", "data")
            base_path = f"s3://{s3_bucket}/processed"
            final_path = f"s3://{s3_bucket}/final"
            
            # Configure S3 endpoint for Minio
            boto3_session = boto3.Session()
            s3_client = boto3_session.client(
                service_name='s3',
                endpoint_url='http://minio:9000',
                aws_access_key_id='minio',
                aws_secret_access_key='minio123'
            )
            
            # Convert dictionary data back to DataFrames for saving
            X_train_norm = pd.DataFrame(normalized_data['X_train_norm'])
            X_test_norm = pd.DataFrame(normalized_data['X_test_norm'])
            X_eval_norm = pd.DataFrame(normalized_data['X_eval_norm'])
            
            y_train = pd.DataFrame(normalized_data['y_train'], columns=['class'])
            y_test = pd.DataFrame(normalized_data['y_test'], columns=['class'])
            y_eval = pd.DataFrame(normalized_data['y_eval'], columns=['class'])
            
            # Save normalized datasets to processed folder
            wr.s3.to_csv(
                df=X_train_norm,
                path=f"{base_path}/X_train.csv",
                index=False,
                boto3_session=boto3_session
            )
            wr.s3.to_csv(
                df=X_test_norm,
                path=f"{base_path}/X_test.csv",
                index=False,
                boto3_session=boto3_session
            )
            wr.s3.to_csv(
                df=X_eval_norm,
                path=f"{base_path}/X_eval.csv",
                index=False,
                boto3_session=boto3_session
            )
            wr.s3.to_csv(
                df=y_train,
                path=f"{base_path}/y_train.csv",
                index=False,
                boto3_session=boto3_session
            )
            wr.s3.to_csv(
                df=y_test,
                path=f"{base_path}/y_test.csv",
                index=False,
                boto3_session=boto3_session
            )
            wr.s3.to_csv(
                df=y_eval,
                path=f"{base_path}/y_eval.csv",
                index=False,
                boto3_session=boto3_session
            )
            
            # Also save the test and evaluation data to final folder for easier access
            wr.s3.to_csv(
                df=X_test_norm,
                path=f"{final_path}/test/h_X_test.csv",
                index=False,
                boto3_session=boto3_session
            )
            wr.s3.to_csv(
                df=y_test,
                path=f"{final_path}/test/y_test.csv",
                index=False,
                boto3_session=boto3_session
            )
            wr.s3.to_csv(
                df=X_eval_norm,
                path=f"{final_path}/eval/X_eval.csv",
                index=False,
                boto3_session=boto3_session
            )
            wr.s3.to_csv(
                df=y_eval,
                path=f"{final_path}/eval/y_eval.csv",
                index=False,
                boto3_session=boto3_session
            )
            
            # Decode the scaler from base64
            scaler_bytes = base64.b64decode(normalized_data['scaler_b64'])
            scaler = pickle.loads(scaler_bytes)
            
            # Save scaler to MLflow
            mlflow.set_tracking_uri(Variable.get("mlflow_tracking_uri", "http://mlflow:5000"))
            mlflow.set_experiment("star_classification")
            
            with mlflow.start_run(run_name="scaler_training"):
                # Log the scaler
                mlflow.sklearn.log_model(
                    scaler,
                    "scaler",
                    registered_model_name="star_classification_scaler"
                )
                
                # Log some metrics about the scaler
                mlflow.log_metric("n_features", len(scaler.feature_names_in_))
                mlflow.log_metric("scale_mean", scaler.scale_.mean())
                mlflow.log_metric("mean_mean", scaler.mean_.mean())
                
                # Log the feature names
                mlflow.log_param("feature_names", list(scaler.feature_names_in_))
            
            logging.info("Successfully saved all processed datasets and scaler model")
        except Exception as e:
            logging.error(f"Error saving data: {str(e)}")
            raise AirflowException(f"Failed to save data: {str(e)}")

    # Define task dependencies
    data = load_data()
    transform_result = transform_data(data)
    split_result = split_data(transform_result)
    norm_result = normalize_data(split_result)
    save_data(norm_result)

dag = process_tl_star_data()