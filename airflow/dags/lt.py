import datetime

from airflow.decorators import dag, task

markdown_text = """
### LT Process for Star Clasification

We load the raw data from S3 and process it, dropping unsured columns, transforming data, normalizing,
 splitting the data into test and train (30/70) and finally store the separate processd data into S3
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
    dag_id="lt_star_clasification_data",
    description="TL process for star classification data, separating the dataset into training and testing sets.",
    doc_md=markdown_text,
    tags=["ETL", "Star Classification"],
    default_args=default_args,
    catchup=False,
)
def process_tl_star_data():

    @task.virtualenv(
        task_id="drop_columns",
        requirements=["ucimlrepo==0.0.3",
                      "awswrangler==3.6.0"],
        system_site_packages=True
    )
    def drop_columns():
        """
        example
        """
        pass

    @task.virtualenv(
        task_id="transform_data",
        requirements=["awswrangler==3.6.0"],
        system_site_packages=True
    )
    def transform_data():
        """
        example
        """
        pass

    @task.virtualenv(
        task_id="normalize_data",
        requirements=["awswrangler==3.6.0"],
        system_site_packages=True
    )
    def normalize_data():
        """
        example
        """
        pass