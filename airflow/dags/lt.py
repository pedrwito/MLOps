import datetime

from airflow.decorators import dag, task

markdown_text = """
### ETL Process for Heart Disease Data

This DAG extracts information from the original CSV file stored in the UCI Machine Learning Repository of the 
[Heart Disease repository](https://archive.ics.uci.edu/dataset/45/heart+disease). 
It preprocesses the data by creating dummy variables and scaling numerical features.
    
After preprocessing, the data is saved back into a S3 bucket as two separate CSV files: one for training and one for 
testing. The split between the training and testing datasets is 70/30 and they are stratified.
"""


default_args = {
    'owner': "Facundo Adrian Lucianna",
    'depends_on_past': False,
    'schedule_interval': None,
    'retries': 1,
    'retry_delay': datetime.timedelta(minutes=5),
    'dagrun_timeout': datetime.timedelta(minutes=15)
}


@dag(
    dag_id="process_etl_heart_data",
    description="ETL process for heart data, separating the dataset into training and testing sets.",
    doc_md=markdown_text,
    tags=["ETL", "Heart Disease"],
    default_args=default_args,
    catchup=False,
)
def process_etl_heart_data():

    @task.virtualenv(
        task_id="obtain_original_data",
        requirements=["ucimlrepo==0.0.3",
                      "awswrangler==3.6.0"],
        system_site_packages=True
    )
    def get_data():
        """
        Load the raw data from UCI repository
        """
        import awswrangler as wr
        from ucimlrepo import fetch_ucirepo
        from airflow.models import Variable

        # fetch dataset
        heart_disease = fetch_ucirepo(id=45)

        data_path = "s3://data/raw/heart.csv"
        dataframe = heart_disease.data.original

        target_col = Variable.get("target_col_heart")

        # Replace level of heart decease to just distinguish presence 
        # (values 1,2,3,4) from absence (value 0).
        dataframe.loc[dataframe[target_col] > 0, target_col] = 1

        wr.s3.to_csv(df=dataframe,
                     path=data_path,
                     index=False)


    @task.virtualenv(
        task_id="make_dummies_variables",
        requirements=["awswrangler==3.6.0"],
        system_site_packages=True
    )