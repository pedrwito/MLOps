import datetime
import logging
from typing import Dict, Any

from airflow.decorators import dag, task
from airflow.models import Variable
from airflow.exceptions import AirflowException

markdown_text = """
### Re-Train the Model for Star Classification

This DAG re-trains the model based on new data, tests the previous model, and put in production the new one 
if it performs better than the old one. It uses the accuracy to evaluate the model with the test data.

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
    dag_id="retrain_the_model",
    description="Re-train the model based on new data, tests the previous model, and put in production the new one if "
                "it performs better than the old one",
    doc_md=markdown_text,
    tags=["Re-Train", "Star Classification"],
    default_args=default_args,
    catchup=False,
)
def processing_dag():
    # Get variables from Airflow
    s3_bucket = Variable.get("s3_bucket", "data")
    mlflow_uri = Variable.get("mlflow_tracking_uri", "http://mlflow:5000")

    @task.virtualenv(
        task_id="train_the_challenger_model",
        requirements=[
            "setuptools",
            "scikit-learn==1.2.2",
            "mlflow==2.9.2",
            "awswrangler==3.6.0",
            "boto3==1.34.0",
            "pandas==1.5.3",
            "numpy==1.24.3"
        ],
        system_site_packages=True
    )
    def train_the_challenger_model(s3_bucket, mlflow_uri):
        import datetime
        import logging
        import mlflow
        import pandas as pd
        import awswrangler as wr
        import boto3
        from airflow.exceptions import AirflowException

        from sklearn.base import clone
        from sklearn.metrics import accuracy_score, precision_score, recall_score, classification_report
        from mlflow.models import infer_signature

        try:
            mlflow.set_tracking_uri(mlflow_uri)

            # Configure S3 endpoint for Minio
            boto3_session = boto3.Session()
            s3_client = boto3_session.client(
                service_name='s3',
                endpoint_url='http://minio:9000',
                aws_access_key_id='minio',
                aws_secret_access_key='minio123'
            )

            def load_the_champion_model():
                logging.info("Loading champion model from MLflow")
                
                # Get the model name used in MLflow
                model_name = "star_classification_model"
                
                # Get the experiment
                experiment = mlflow.set_experiment("Star Classification")
                
                # Search for the latest run tagged as champion
                runs = mlflow.search_runs(
                    experiment_ids=[experiment.experiment_id],
                    filter_string="tags.model_status = 'champion'",
                    order_by=["attribute.start_time DESC"],
                    max_results=1
                )
                
                if len(runs) == 0:
                    # Try to look in the LogReg_Grif experiment
                    other_experiment = mlflow.set_experiment("LogReg_Grif")
                    runs = mlflow.search_runs(
                        experiment_ids=[other_experiment.experiment_id],
                        order_by=["attribute.start_time DESC"],
                        max_results=1
                    )
                    
                if len(runs) == 0:
                    raise Exception("No model found in MLflow")
                
                run_id = runs.iloc[0].run_id
                
                # Load the model from the run
                champion_version = mlflow.sklearn.load_model(f"runs:/{run_id}/LogReg_Grif")
                logging.info(f"Successfully loaded champion model: {type(champion_version).__name__} from run {run_id}")

                return champion_version, run_id

            def load_the_train_test_data():
                logging.info("Loading training and test data from S3")
                X_train = wr.s3.read_csv(f"s3://{s3_bucket}/processed/X_train.csv", boto3_session=boto3_session)
                y_train = wr.s3.read_csv(f"s3://{s3_bucket}/processed/y_train.csv", boto3_session=boto3_session)
                X_test = wr.s3.read_csv(f"s3://{s3_bucket}/processed/X_test.csv", boto3_session=boto3_session)
                y_test = wr.s3.read_csv(f"s3://{s3_bucket}/processed/y_test.csv", boto3_session=boto3_session)
                logging.info(f"Successfully loaded data. X_train shape: {X_train.shape}")

                return X_train, y_train, X_test, y_test

            def register_model_with_metrics(model, X_test, y_test, is_challenger=True):
                logging.info(f"Tracking experiment in MLflow")
                # Track the experiment
                experiment = mlflow.set_experiment("Star Classification")

                # Make predictions
                y_pred = model.predict(X_test)
                y_pred_proba = model.predict_proba(X_test) if hasattr(model, "predict_proba") else None
                
                # Calculate metrics
                accuracy = accuracy_score(y_test.to_numpy().ravel(), y_pred)
                precision = precision_score(y_test.to_numpy().ravel(), y_pred, average='weighted')
                recall = recall_score(y_test.to_numpy().ravel(), y_pred, average='weighted')
                
                # Get detailed metrics by class
                report = classification_report(y_test.to_numpy().ravel(), y_pred, output_dict=True)
                class_labels = [k for k in report.keys() if k not in ('accuracy', 'macro avg', 'weighted avg')]
                
                run_name = 'Challenger_model' if is_challenger else 'Champion_model'
                
                # Start MLflow run
                with mlflow.start_run(run_name=run_name, experiment_id=experiment.experiment_id) as run:
                    # Log parameters
                    params = model.get_params()
                    params["model"] = type(model).__name__
                    mlflow.log_params(params)
                    
                    # Log model status tag
                    if is_challenger:
                        mlflow.set_tag("model_status", "challenger")
                    else:
                        mlflow.set_tag("model_status", "champion")
                    
                    # Log metrics
                    metrics = {
                        'accuracy': accuracy,
                        'precision': precision,
                        'recall': recall
                    }
                    
                    # Add class-specific metrics
                    for cls in class_labels:
                        metrics[f'precision_class_{cls}'] = report[cls]['precision']
                        metrics[f'recall_class_{cls}'] = report[cls]['recall']
                    
                    mlflow.log_metrics(metrics)
                    
                    # Log model
                    signature = infer_signature(X_test, y_pred)
                    
                    mlflow.sklearn.log_model(
                        sk_model=model,
                        artifact_path="LogReg_Grif",
                        signature=signature,
                        registered_model_name="star_classification_model"
                    )
                    
                    return run.info.run_id, accuracy

            # Load the champion model
            champion_model, champion_run_id = load_the_champion_model()

            # Clone the model
            challenger_model = clone(champion_model)

            # Load the dataset
            X_train, y_train, X_test, y_test = load_the_train_test_data()

            # Fit the training model
            logging.info("Training challenger model")
            challenger_model.fit(X_train, y_train.to_numpy().ravel())

            # Register champion model with its metrics (if not already done)
            champion_run_id, champion_accuracy = register_model_with_metrics(
                champion_model, X_test, y_test, is_challenger=False
            )
            
            # Register challenger model with its metrics
            challenger_run_id, challenger_accuracy = register_model_with_metrics(
                challenger_model, X_test, y_test, is_challenger=True
            )
            
            return {
                "status": "success", 
                "champion_run_id": champion_run_id,
                "challenger_run_id": challenger_run_id,
                "champion_accuracy": champion_accuracy,
                "challenger_accuracy": challenger_accuracy
            }
            
        except Exception as e:
            logging.error(f"Error in train_the_challenger_model: {str(e)}")
            raise AirflowException(f"Failed to train challenger model: {str(e)}")


    @task.virtualenv(
        task_id="evaluate_champion_challenger",
        requirements=[
            "setuptools",
            "scikit-learn==1.2.2",
            "mlflow==2.9.2",
            "awswrangler==3.6.0",
            "boto3==1.34.0",
            "pandas==1.5.3",
            "numpy==1.24.3"
        ],
        system_site_packages=True
    )
    def evaluate_champion_challenger(prev_results, mlflow_uri):
        import logging
        import mlflow
        import pandas as pd
        import boto3
        from airflow.exceptions import AirflowException

        from sklearn.metrics import accuracy_score

        try:
            mlflow.set_tracking_uri(mlflow_uri)
            
            # Use the previous results directly
            if prev_results and 'champion_accuracy' in prev_results and 'challenger_accuracy' in prev_results:
                champion_accuracy = prev_results['champion_accuracy']
                challenger_accuracy = prev_results['challenger_accuracy']
                champion_run_id = prev_results['champion_run_id']
                challenger_run_id = prev_results['challenger_run_id']
                
                logging.info(f"Champion model accuracy: {champion_accuracy}")
                logging.info(f"Challenger model accuracy: {challenger_accuracy}")
                
                # Determine the winner
                if challenger_accuracy > champion_accuracy:
                    winner = "Challenger"
                    logging.info(f"Winner is Challenger with accuracy: {challenger_accuracy}")
                    
                    # Update the model status tags
                    client = mlflow.MlflowClient()
                    client.set_tag(champion_run_id, "model_status", "archived")
                    client.set_tag(challenger_run_id, "model_status", "champion")
                else:
                    winner = "Champion"
                    logging.info(f"Winner is Champion with accuracy: {champion_accuracy}")
                    
                    # Archive the challenger
                    client = mlflow.MlflowClient()
                    client.set_tag(challenger_run_id, "model_status", "archived")
                
                experiment = mlflow.set_experiment("Star Classification")
                
                # Log comparison results
                with mlflow.start_run(run_name="Model_Comparison", experiment_id=experiment.experiment_id) as run:
                    mlflow.log_param("champion_run_id", champion_run_id)
                    mlflow.log_param("challenger_run_id", challenger_run_id)
                    mlflow.log_metric("champion_accuracy", champion_accuracy)
                    mlflow.log_metric("challenger_accuracy", challenger_accuracy)
                    mlflow.log_param("winner", winner)
                
                return {
                    "status": "success", 
                    "champion_accuracy": champion_accuracy,
                    "challenger_accuracy": challenger_accuracy,
                    "winner": winner
                }
            else:
                raise Exception("Could not get accuracy metrics from previous task")
            
        except Exception as e:
            logging.error(f"Error in evaluate_champion_challenger: {str(e)}")
            raise AirflowException(f"Failed to evaluate models: {str(e)}")

    # Pass variables to the task
    train_result = train_the_challenger_model(s3_bucket, mlflow_uri)
    evaluate_champion_challenger(train_result, mlflow_uri)


dag = processing_dag()
