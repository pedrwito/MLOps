import datetime
import logging

from airflow.decorators import dag, task
from airflow.models import Variable
from airflow.exceptions import AirflowException

markdown_text = """
### Weekly Evaluation of Star Classification Model

This DAG performs weekly evaluation of the production model to:
1. Detect data drift by comparing distributions of incoming data with training data
2. Evaluate model performance metrics over time
3. Determine if model retraining is necessary based on performance degradation
4. Generate reports on model health and performance trends
"""

default_args = {
    'owner': "ML Models and something more Inc.",
    'depends_on_past': False,
    'schedule_interval': '@weekly',  # Run weekly
    'retries': 1,
    'retry_delay': datetime.timedelta(minutes=5),
    'dagrun_timeout': datetime.timedelta(minutes=15)
}

@dag(
    dag_id="weekly_model_evaluation",
    description="Weekly evaluation of the production model for performance monitoring and drift detection",
    doc_md=markdown_text,
    tags=["Evaluation", "Monitoring", "Star Classification"],
    default_args=default_args,
    catchup=False,
)
def weekly_evaluation_dag():

    @task.virtualenv(
        task_id="collect_recent_data",
        requirements=["awswrangler==3.6.0", "pandas==2.1.0"],
        system_site_packages=True
    )
    def collect_recent_data():
        import awswrangler as wr
        import pandas as pd
        from datetime import datetime, timedelta
        
        try:
            logging.info("Collecting recent data for evaluation")
            s3_bucket = Variable.get("s3_bucket", "data")
            
            # Get last week's data
            today = datetime.now()
            last_week = today - timedelta(days=7)
            last_week_str = last_week.strftime("%Y-%m-%d")
            
            # In a real scenario, we would filter data by date
            # For this example, we'll use the test data to simulate recent data
            recent_data_path = f"s3://{s3_bucket}/final/test/h_X_test.csv"
            recent_labels_path = f"s3://{s3_bucket}/final/test/y_test.csv"
            
            recent_data = wr.s3.read_csv(recent_data_path)
            recent_labels = wr.s3.read_csv(recent_labels_path)
            
            # Save recent data to a temporary location for the evaluation
            temp_path = f"s3://{s3_bucket}/temp/weekly_evaluation/{today.strftime('%Y-%m-%d')}"
            wr.s3.to_csv(recent_data, f"{temp_path}/recent_data.csv", index=False)
            wr.s3.to_csv(recent_labels, f"{temp_path}/recent_labels.csv", index=False)
            
            logging.info(f"Successfully collected recent data with shape: {recent_data.shape}")
            
            return {
                "status": "success",
                "data_path": f"{temp_path}/recent_data.csv",
                "labels_path": f"{temp_path}/recent_labels.csv",
                "rows": len(recent_data)
            }
            
        except Exception as e:
            logging.error(f"Error collecting recent data: {str(e)}")
            raise AirflowException(f"Failed to collect recent data: {str(e)}")

    @task.virtualenv(
        task_id="detect_data_drift",
        requirements=["scikit-learn==1.3.2", "awswrangler==3.6.0", "scipy==1.12.0"],
        system_site_packages=True
    )
    def detect_data_drift(collect_data_result):
        import awswrangler as wr
        import pandas as pd
        import numpy as np
        from scipy import stats
        
        try:
            logging.info("Detecting data drift")
            s3_bucket = Variable.get("s3_bucket", "data")
            
            # Get paths from previous task
            recent_data_path = collect_data_result["data_path"]
            
            # Load recent data and training data for comparison
            recent_data = wr.s3.read_csv(recent_data_path)
            training_data = wr.s3.read_csv(f"s3://{s3_bucket}/final/train/X_train.csv")
            
            # Calculate drift metrics using KS test for each numerical feature
            numerical_features = ["alpha", "delta", "u", "g", "r", "i", "z", "redshift"]
            drift_results = {}
            drift_detected = False
            
            for feature in numerical_features:
                if feature in recent_data.columns and feature in training_data.columns:
                    # Perform Kolmogorov-Smirnov test
                    ks_stat, p_value = stats.ks_2samp(
                        recent_data[feature].dropna(), 
                        training_data[feature].dropna()
                    )
                    
                    # Record results
                    drift_results[feature] = {
                        "ks_statistic": float(ks_stat),
                        "p_value": float(p_value),
                        "drift_detected": p_value < 0.05  # Significance level
                    }
                    
                    if p_value < 0.05:
                        drift_detected = True
                        logging.warning(f"Drift detected in feature {feature}: p-value={p_value}")
            
            # Save drift results
            drift_results_df = pd.DataFrame([
                {"feature": k, "ks_statistic": v["ks_statistic"], 
                 "p_value": v["p_value"], "drift_detected": v["drift_detected"]}
                for k, v in drift_results.items()
            ])
            
            report_date = collect_data_path = collect_data_result["data_path"].split("/")[-2]
            drift_report_path = f"s3://{s3_bucket}/reports/drift/{report_date}/drift_results.csv"
            wr.s3.to_csv(drift_results_df, drift_report_path, index=False)
            
            logging.info(f"Data drift analysis completed. Overall drift detected: {drift_detected}")
            
            return {
                "status": "success",
                "drift_detected": drift_detected,
                "drift_report_path": drift_report_path,
                "features_with_drift": [k for k, v in drift_results.items() if v["drift_detected"]]
            }
            
        except Exception as e:
            logging.error(f"Error detecting data drift: {str(e)}")
            raise AirflowException(f"Failed to detect data drift: {str(e)}")

    @task.virtualenv(
        task_id="evaluate_model_performance",
        requirements=["scikit-learn==1.3.2", "mlflow==2.10.2", "awswrangler==3.6.0"],
        system_site_packages=True
    )
    def evaluate_model_performance(collect_data_result):
        import mlflow
        import awswrangler as wr
        import pandas as pd
        from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix
        
        try:
            logging.info("Evaluating model performance")
            s3_bucket = Variable.get("s3_bucket", "data")
            mlflow_uri = Variable.get("mlflow_tracking_uri", "http://mlflow:5000")
            mlflow.set_tracking_uri(mlflow_uri)
            
            # Get paths from previous task
            recent_data_path = collect_data_result["data_path"]
            recent_labels_path = collect_data_result["labels_path"]
            
            # Load data
            X_recent = wr.s3.read_csv(recent_data_path)
            y_recent = wr.s3.read_csv(recent_labels_path)
            
            # Load production model
            model_name = "star_classification_model_prod"
            client = mlflow.MlflowClient()
            model_data = client.get_model_version_by_alias(model_name, "champion")
            model = mlflow.sklearn.load_model(model_data.source)
            
            # Make predictions
            y_pred = model.predict(X_recent)
            
            # Calculate metrics
            metrics = {
                "accuracy": float(accuracy_score(y_recent, y_pred)),
                "precision_macro": float(precision_score(y_recent, y_pred, average='macro')),
                "recall_macro": float(recall_score(y_recent, y_pred, average='macro')),
                "f1_macro": float(f1_score(y_recent, y_pred, average='macro'))
            }
            
            # Log to MLflow
            experiment = mlflow.set_experiment("Star Classification Monitoring")
            with mlflow.start_run(run_name=f"weekly_evaluation_{datetime.datetime.now().strftime('%Y%m%d')}",
                                 experiment_id=experiment.experiment_id):
                # Log performance metrics
                for metric_name, metric_value in metrics.items():
                    mlflow.log_metric(metric_name, metric_value)
                
                # Get performance threshold from variable or use default
                performance_threshold = float(Variable.get("model_performance_threshold", "0.8"))
                
                # Log evaluation result
                performance_warning = metrics["accuracy"] < performance_threshold
                mlflow.log_param("performance_warning", performance_warning)
                
                if performance_warning:
                    logging.warning(f"Model performance below threshold: {metrics['accuracy']} < {performance_threshold}")
                
                # Create confusion matrix and log as a figure
                cm = confusion_matrix(y_recent, y_pred)
                cm_df = pd.DataFrame(cm)
                cm_path = f"/tmp/confusion_matrix.csv"
                cm_df.to_csv(cm_path, index=False)
                mlflow.log_artifact(cm_path)
            
            # Save metrics to S3
            report_date = collect_data_path = collect_data_result["data_path"].split("/")[-2]
            metrics_df = pd.DataFrame([metrics])
            metrics_path = f"s3://{s3_bucket}/reports/performance/{report_date}/metrics.csv"
            wr.s3.to_csv(metrics_df, metrics_path, index=False)
            
            logging.info(f"Model evaluation completed. Accuracy: {metrics['accuracy']}")
            
            return {
                "status": "success",
                "metrics": metrics,
                "metrics_path": metrics_path,
                "performance_warning": performance_warning
            }
            
        except Exception as e:
            logging.error(f"Error evaluating model performance: {str(e)}")
            raise AirflowException(f"Failed to evaluate model performance: {str(e)}")

    @task.virtualenv(
        task_id="generate_evaluation_report",
        requirements=["awswrangler==3.6.0", "pandas==2.1.0"],
        system_site_packages=True
    )
    def generate_evaluation_report(drift_result, performance_result):
        import awswrangler as wr
        import pandas as pd
        import json
        from datetime import datetime
        
        try:
            logging.info("Generating evaluation report")
            s3_bucket = Variable.get("s3_bucket", "data")
            
            # Determine if retraining is recommended
            retraining_recommended = (
                drift_result["drift_detected"] or 
                performance_result["performance_warning"]
            )
            
            # Create report
            report = {
                "evaluation_date": datetime.now().strftime("%Y-%m-%d"),
                "model_name": "star_classification_model_prod",
                "drift_detected": drift_result["drift_detected"],
                "features_with_drift": drift_result["features_with_drift"],
                "performance_metrics": performance_result["metrics"],
                "performance_warning": performance_result["performance_warning"],
                "retraining_recommended": retraining_recommended
            }
            
            # Save report to S3
            report_date = datetime.now().strftime("%Y-%m-%d")
            report_path = f"s3://{s3_bucket}/reports/weekly/{report_date}/evaluation_summary.json"
            
            # Convert to DataFrame for S3 storage
            report_df = pd.DataFrame([report])
            wr.s3.to_csv(report_df, report_path.replace(".json", ".csv"), index=False)
            
            # If retraining is recommended, create a flag file
            if retraining_recommended:
                flag_path = f"s3://{s3_bucket}/triggers/retrain_required_{report_date}.flag"
                wr.s3.to_csv(
                    pd.DataFrame([{"reason": "drift_detected" if drift_result["drift_detected"] else "performance_degradation"}]),
                    flag_path,
                    index=False
                )
                logging.warning(f"Retraining recommended! Flag created at {flag_path}")
            
            logging.info(f"Evaluation report generated. Retraining recommended: {retraining_recommended}")
            
            return {
                "status": "success",
                "report_path": report_path,
                "retraining_recommended": retraining_recommended
            }
            
        except Exception as e:
            logging.error(f"Error generating evaluation report: {str(e)}")
            raise AirflowException(f"Failed to generate evaluation report: {str(e)}")
    
    # Define task dependencies
    collect_data = collect_recent_data()
    drift_result = detect_data_drift(collect_data)
    performance_result = evaluate_model_performance(collect_data)
    generate_evaluation_report(drift_result, performance_result)

dag = weekly_evaluation_dag()
