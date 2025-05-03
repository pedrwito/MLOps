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

    @task.virtualenv(
        task_id="train_the_challenger_model",
        requirements=["scikit-learn==1.3.2",
                      "mlflow==2.10.2",
                      "awswrangler==3.6.0"],
        system_site_packages=True
    )
    def train_the_challenger_model():
        import datetime
        import mlflow
        import awswrangler as wr

        from sklearn.base import clone
        from sklearn.metrics import accuracy_score
        from mlflow.models import infer_signature

        try:
            s3_bucket = Variable.get("s3_bucket", "data")
            mlflow_uri = Variable.get("mlflow_tracking_uri", "http://mlflow:5001")
            mlflow.set_tracking_uri(mlflow_uri)

            def load_the_champion_model():
                logging.info("Loading champion model from MLflow")
                model_name = "star_classification_model_prod"
                alias = "champion"

                client = mlflow.MlflowClient()
                model_data = client.get_model_version_by_alias(model_name, alias)

                champion_version = mlflow.sklearn.load_model(model_data.source)
                logging.info(f"Successfully loaded champion model: {type(champion_version).__name__}")

                return champion_version

            def load_the_train_test_data():
                logging.info("Loading training and test data from S3")
                X_train = wr.s3.read_csv(f"s3://{s3_bucket}/final/train/X_train.csv")
                y_train = wr.s3.read_csv(f"s3://{s3_bucket}/final/train/y_train.csv")
                X_test = wr.s3.read_csv(f"s3://{s3_bucket}/final/test/h_X_test.csv")
                y_test = wr.s3.read_csv(f"s3://{s3_bucket}/final/test/y_test.csv")
                logging.info(f"Successfully loaded data. X_train shape: {X_train.shape}")

                return X_train, y_train, X_test, y_test

            def mlflow_track_experiment(model, X):
                logging.info("Tracking experiment in MLflow")
                # Track the experiment
                experiment = mlflow.set_experiment("Star Classification")

                mlflow.start_run(run_name='Challenger_run_' + datetime.datetime.today().strftime('%Y/%m/%d-%H:%M:%S"'),
                                 experiment_id=experiment.experiment_id,
                                 tags={"experiment": "challenger models", "dataset": "Star Classification"},
                                 log_system_metrics=True)

                params = model.get_params()
                params["model"] = type(model).__name__

                mlflow.log_params(params)

                # Save the artifact of the challenger model
                artifact_path = "model"

                signature = infer_signature(X, model.predict(X))

                mlflow.sklearn.log_model(
                    sk_model=model,
                    artifact_path=artifact_path,
                    signature=signature,
                    serialization_format='cloudpickle',
                    registered_model_name="star_classification_model_dev",
                    metadata={"model_data_version": 1}
                )

                # Obtain the model URI
                logging.info("Successfully tracked experiment in MLflow")
                return mlflow.get_artifact_uri(artifact_path)

            def register_challenger(model, accuracy, model_uri):
                logging.info(f"Registering challenger model with accuracy: {accuracy}")
                client = mlflow.MlflowClient()
                name = "star_classification_model_prod"

                # Save the model params as tags
                tags = model.get_params()
                tags["model"] = type(model).__name__
                tags["accuracy"] = accuracy

                # Save the version of the model
                result = client.create_model_version(
                    name=name,
                    source=model_uri,
                    run_id=model_uri.split("/")[-3],
                    tags=tags
                )

                # Save the alias as challenger
                client.set_registered_model_alias(name, "challenger", result.version)
                logging.info(f"Successfully registered challenger model as version {result.version}")

            # Load the champion model
            champion_model = load_the_champion_model()

            # Clone the model
            challenger_model = clone(champion_model)

            # Load the dataset
            X_train, y_train, X_test, y_test = load_the_train_test_data()

            # Fit the training model
            logging.info("Training challenger model")
            challenger_model.fit(X_train, y_train.to_numpy().ravel())

            # Obtain the metric of the model
            y_pred = challenger_model.predict(X_test)
            accuracy = accuracy_score(y_test.to_numpy().ravel(), y_pred)
            logging.info(f"Challenger model accuracy: {accuracy}")

            # Track the experiment
            artifact_uri = mlflow_track_experiment(challenger_model, X_train)

            # Record the model
            register_challenger(challenger_model, accuracy, artifact_uri)
            
            return {"status": "success", "accuracy": accuracy}
            
        except Exception as e:
            logging.error(f"Error in train_the_challenger_model: {str(e)}")
            raise AirflowException(f"Failed to train challenger model: {str(e)}")


    @task.virtualenv(
        task_id="evaluate_champion_challenger",
        requirements=["scikit-learn==1.3.2",
                      "mlflow==2.10.2",
                      "awswrangler==3.6.0"],
        system_site_packages=True
    )
    def evaluate_champion_challenger():
        import mlflow
        import awswrangler as wr

        from sklearn.metrics import accuracy_score

        try:
            s3_bucket = Variable.get("s3_bucket", "data")
            mlflow_uri = Variable.get("mlflow_tracking_uri", "http://mlflow:5000")
            mlflow.set_tracking_uri(mlflow_uri)

            def load_the_model(alias):
                logging.info(f"Loading model with alias: {alias}")
                model_name = "star_classification_model_prod"

                client = mlflow.MlflowClient()
                model_data = client.get_model_version_by_alias(model_name, alias)

                model = mlflow.sklearn.load_model(model_data.source)
                logging.info(f"Successfully loaded {alias} model: {type(model).__name__}")

                return model

            def load_the_test_data():
                logging.info("Loading test data")
                X_test = wr.s3.read_csv(f"s3://{s3_bucket}/final/test/heart_X_test.csv")
                y_test = wr.s3.read_csv(f"s3://{s3_bucket}/final/test/heart_y_test.csv")
                logging.info(f"Successfully loaded test data. X_test shape: {X_test.shape}")

                return X_test, y_test

            def promote_challenger(name):
                logging.info("Promoting challenger to champion")
                client = mlflow.MlflowClient()

                # Demote the champion
                client.delete_registered_model_alias(name, "champion")

                # Load the challenger from registry
                challenger_version = client.get_model_version_by_alias(name, "challenger")

                # delete the alias of challenger
                client.delete_registered_model_alias(name, "challenger")

                # Transform in champion
                client.set_registered_model_alias(name, "champion", challenger_version.version)
                logging.info(f"Successfully promoted challenger (version {challenger_version.version}) to champion")

            def demote_challenger(name):
                logging.info("Demoting challenger (keeping current champion)")
                client = mlflow.MlflowClient()

                # delete the alias of challenger
                client.delete_registered_model_alias(name, "challenger")
                logging.info("Successfully demoted challenger")

            # Load the champion model
            champion_model = load_the_model("champion")

            # Load the challenger model
            challenger_model = load_the_model("challenger")

            # Load the dataset
            X_test, y_test = load_the_test_data()

            # Obtain the metric of the models
            logging.info("Evaluating champion model")
            y_pred_champion = champion_model.predict(X_test)
            accuracy_champion = accuracy_score(y_test.to_numpy().ravel(), y_pred_champion)
            logging.info(f"Champion model accuracy: {accuracy_champion}")

            logging.info("Evaluating challenger model")
            y_pred_challenger = challenger_model.predict(X_test)
            accuracy_challenger = accuracy_score(y_test.to_numpy().ravel(), y_pred_challenger)
            logging.info(f"Challenger model accuracy: {accuracy_challenger}")

            experiment = mlflow.set_experiment("Star Classification")

            # Obtain the last experiment run_id to log the new information
            list_run = mlflow.search_runs([experiment.experiment_id], output_format="list")

            with mlflow.start_run(run_id=list_run[0].info.run_id):
                mlflow.log_metric("test_accuracy_challenger", accuracy_challenger)
                mlflow.log_metric("test_accuracy_champion", accuracy_champion)

                if accuracy_challenger > accuracy_champion:
                    winner = "Challenger"
                    mlflow.log_param("Winner", winner)
                else:
                    winner = "Champion"
                    mlflow.log_param("Winner", winner)
                    
                logging.info(f"Winner is: {winner}")

            name = "star_classification_model_prod"
            if accuracy_challenger > accuracy_champion:
                promote_challenger(name)
            else:
                demote_challenger(name)
                
            return {
                "status": "success", 
                "accuracy_champion": accuracy_champion,
                "accuracy_challenger": accuracy_challenger,
                "winner": winner
            }
            
        except Exception as e:
            logging.error(f"Error in evaluate_champion_challenger: {str(e)}")
            raise AirflowException(f"Failed to evaluate models: {str(e)}")

    train_the_challenger_model() >> evaluate_champion_challenger()


dag = processing_dag()
