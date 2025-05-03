import datetime
import logging
from typing import Dict, Any

from airflow.decorators import dag, task
from airflow.models import Variable
from airflow.exceptions import AirflowException

markdown_text = """
### EL Process for Star Classification

This DAG extracts information from the original CSV file stored in the kaggle repository https://www.kaggle.com/datasets/fedesoriano/stellar-classification-dataset-sdss17.
It extracts the data and stores it into an S3 bucket.
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
    "pandas==2.1.0",
    "numpy==1.24.3",
    "kaggle==1.5.16"
]

@dag(
    dag_id="el_star_classification_data",
    description="EL process for star classification data, retrieving it from kaggle and loading it into s3",
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
    def get_data() -> Dict[str, Any]:
        """
        Load the raw data from kaggle repository
        """
        import awswrangler as wr
        import pandas as pd
        import os
        from kaggle.api.kaggle_api_extended import KaggleApi
        
        try:
            # Get configuration from Airflow variables
            s3_bucket = Variable.get("s3_bucket", "data")
            raw_data_path = f"s3://{s3_bucket}/raw/star_classification.csv"
            
            # Initialize Kaggle API
            api = KaggleApi()
            api.authenticate()
            
            # Download dataset
            api.dataset_download_files(
                'fedesoriano/stellar-classification-dataset-sdss17',
                path='/tmp',
                unzip=True
            )
            
            # Read the downloaded CSV
            dataframe = pd.read_csv('/tmp/star_classification.csv')
            
            # Basic data validation
            if dataframe.empty:
                raise AirflowException("Downloaded dataset is empty")
            
            required_columns = ['class', 'alpha', 'delta', 'u', 'g', 'r', 'i', 'z']
            missing_columns = [col for col in required_columns if col not in dataframe.columns]
            if missing_columns:
                raise AirflowException(f"Missing required columns: {missing_columns}")
            
            # Save to S3
            wr.s3.to_csv(
                df=dataframe,
                path=raw_data_path,
                index=False
            )
            
            return {"status": "success", "rows": len(dataframe)}
            
        except Exception as e:
            logging.error(f"Error in get_data task: {str(e)}")
            raise AirflowException(f"Failed to get data: {str(e)}")

    @task.virtualenv(
        task_id="remove_features",
        requirements=COMMON_REQUIREMENTS,
        system_site_packages=True
    )
    def remove_features() -> Dict[str, Any]:
        """
        Removes useless features and performs data cleaning
        """
        import awswrangler as wr
        import pandas as pd
        import numpy as np
        
        try:
            # Get configuration from Airflow variables
            s3_bucket = Variable.get("s3_bucket", "data")
            data_original_path = f"s3://{s3_bucket}/raw/star_classification.csv"
            data_end_path = f"s3://{s3_bucket}/raw/star_classification_filtered.csv"
            
            # Read data
            data_raw = wr.s3.read_csv(data_original_path)
            
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
                index=False
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