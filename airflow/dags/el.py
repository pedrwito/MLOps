import datetime

from airflow.decorators import dag, task

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
        requirements=["ucimlrepo==0.0.3",
                      "awswrangler==3.6.0"],
        system_site_packages=True
    )
    def get_data():
        """
        Load the raw data from kaggle repository
        """
        import awswrangler as wr
        from ucimlrepo import fetch_ucirepo
        from airflow.models import Variable
        
        # fetch dataset
        heart_disease = fetch_ucirepo(id=45)

        data_path = "s3://data/raw/star_classification.csv"
        dataframe = heart_disease.data.original

        target_col = Variable.get("target_col_heart")

        # Replace level of heart decease to just distinguish presence 
        # (values 1,2,3,4) from absence (value 0).
        dataframe.loc[dataframe[target_col] > 0, target_col] = 1

        wr.s3.to_csv(df=dataframe,
                     path=data_path,
                     index=False)


    @task.virtualenv(
        task_id="remove_features",
        requirements=["awswrangler==3.6.0"],
        system_site_packages=True
    )
    def remove_features():
        """
        Removes useless features 
        """

        import awswrangler as wr
        import pandas as pd
        import numpy as np


        data_original_path = "s3://data/raw/star_classification.csv"
        data_end_path = "s3://data/raw/star_classification_filtered.csv"
        data_raw = wr.s3.read_csv(data_original_path)

        data = data_raw.drop(['rerun_ID', 'spec_obj_ID', 'obj_ID', 'run_ID','fiber_ID','plate','field_ID','cam_col'], axis=1)

        wr.s3.to_csv(df=data,
                path=data_end_path,
                index=False)
        

    get_data() >> remove_features()


dag = process_el_star_data()