import datetime
import logging

from airflow.decorators import dag, task
from airflow.models import Variable
from airflow.exceptions import AirflowException

markdown_text = """
### EL Process for Star Classification

This DAG processes the star classification data stored in S3 (Minio).
It reads the data from raw bucket and performs feature selection and cleaning.
"""

default_args = {
    'owner': "ML Models and something more Inc.",
    'depends_on_past': False,
    'schedule_interval': None,
    'retries': 1,
    'retry_delay': datetime.timedelta(minutes=5),
    'dagrun_timeout': datetime.timedelta(minutes=15)
}

# Common requirements for all tasks
COMMON_REQUIREMENTS = [
    "awswrangler==3.6.0",
    "pandas==1.5.3",
    "numpy==1.24.3",
    "boto3==1.34.0"
]

@dag(
    dag_id="el_star_classification_data",
    description="EL process for star classification data from S3",
    doc_md=markdown_text,
    tags=["EL", "Star Classification"],
    default_args=default_args,
    catchup=False,
)
def process_el_star_data():

    @task.virtualenv(
        task_id="obtain_original_data",
        requirements=COMMON_REQUIREMENTS,
        system_site_packages=True
    )
    def get_data():
        """
        Load the raw data from S3
        """
        import awswrangler as wr
        import pandas as pd
        import boto3
        import logging
        from airflow.models import Variable
        from airflow.exceptions import AirflowException
        
        try:
            # Get configuration from Airflow variables
            s3_bucket = Variable.get("s3_bucket", "data")
            raw_data_path = f"s3://{s3_bucket}/raw/star_classification.csv"
            
            # Configure S3 endpoint for Minio
            boto3_session = boto3.Session()
            s3_client = boto3_session.client(
                service_name='s3',
                endpoint_url='http://minio:9000',
                aws_access_key_id='minio',
                aws_secret_access_key='minio123'
            )
            
            # Read directly from S3
            dataframe = wr.s3.read_csv(
                path=raw_data_path,
                boto3_session=boto3_session
            )
            
            # Basic data validation
            if dataframe.empty:
                raise AirflowException("Dataset is empty")
            
            required_columns = ['class', 'alpha', 'delta', 'u', 'g', 'r', 'i', 'z']
            missing_columns = [col for col in required_columns if col not in dataframe.columns]
            if missing_columns:
                raise AirflowException(f"Missing required columns: {missing_columns}")
            
            # Log success
            return {"status": "success", "rows": len(dataframe)}
            
        except Exception as e:
            logging.error(f"Error in get_data task: {str(e)}")
            raise AirflowException(f"Failed to get data: {str(e)}")

    @task.virtualenv(
        task_id="remove_features",
        requirements=COMMON_REQUIREMENTS,
        system_site_packages=True
    )
    def remove_features():
        """
        Removes useless features and performs data cleaning
        """
        import awswrangler as wr
        import pandas as pd
        import numpy as np
        import boto3
        import logging
        from airflow.models import Variable
        from airflow.exceptions import AirflowException
        
        try:
            # Get configuration from Airflow variables
            s3_bucket = Variable.get("s3_bucket", "data")
            data_original_path = f"s3://{s3_bucket}/raw/star_classification.csv"
            data_end_path = f"s3://{s3_bucket}/raw/star_classification_filtered.csv"
            
            # Configure S3 endpoint for Minio
            boto3_session = boto3.Session()
            s3_client = boto3_session.client(
                service_name='s3',
                endpoint_url='http://minio:9000',
                aws_access_key_id='minio',
                aws_secret_access_key='minio123'
            )
            
            # Read data
            data_raw = wr.s3.read_csv(
                path=data_original_path,
                boto3_session=boto3_session
            )
            
            # Remove unnecessary columns
            columns_to_remove = [
                'rerun_ID', 'spec_obj_ID', 'obj_ID', 'run_ID',
                'fiber_ID', 'plate', 'field_ID', 'cam_col'
            ]
            data = data_raw.drop(columns_to_remove, axis=1)
            
            # Basic data cleaning
            data = data.dropna()  # Remove rows with missing values
            
            # Save processed data
            wr.s3.to_csv(
                df=data,
                path=data_end_path,
                index=False,
                boto3_session=boto3_session
            )
            
            return {
                "status": "success",
                "original_rows": len(data_raw),
                "processed_rows": len(data)
            }
            
        except Exception as e:
            logging.error(f"Error in remove_features task: {str(e)}")
            raise AirflowException(f"Failed to process features: {str(e)}")

    # Define task dependencies
    get_data() >> remove_features()

dag = process_el_star_data()