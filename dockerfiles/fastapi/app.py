import json
import pickle
import boto3
import mlflow

import numpy as np
import pandas as pd

from typing import Literal, List
from fastapi import FastAPI, Body, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from typing_extensions import Annotated


def load_model(model_name: str, alias: str):
    """
    Load a trained model and associated data dictionary.

    This function attempts to load a trained model specified by its name and alias. If the model is not found in the
    MLflow registry, it loads the default model from a file. Additionally, it loads information about the ETL pipeline
    from an S3 bucket. If the data dictionary is not found in the S3 bucket, it loads it from a local file.

    :param model_name: The name of the model.
    :param alias: The alias of the model version.
    :return: A tuple containing the loaded model, its version, and the data dictionary.
    """

    try:
        # Load the trained model from MLflow
        mlflow.set_tracking_uri('http://mlflow:5000')
        client_mlflow = mlflow.MlflowClient()

        # First look for the model registered with specific tags
        try:
            # Try to get directly by the model name
            model_data_mlflow = client_mlflow.get_registered_model(model_name)
            latest_version = model_data_mlflow.latest_versions[0].version
            model_ml = mlflow.sklearn.load_model(f"models:/{model_name}/{latest_version}")
            version_model_ml = int(latest_version)
            print(f"Loaded model {model_name} version {latest_version}")
        except:
            # Try to find the champion model by searching experiments
            experiments = client_mlflow.search_experiments()
            found_model = False
            
            for exp in experiments:
                # Look for runs tagged as champion
                runs = client_mlflow.search_runs(
                    experiment_ids=[exp.experiment_id],
                    filter_string="tags.model_status = 'champion'",
                    order_by=["attribute.start_time DESC"],
                    max_results=1
                )
                
                if len(runs) > 0:
                    run_id = runs[0].info.run_id
                    model_ml = mlflow.sklearn.load_model(f"runs:/{run_id}/LogReg_Grif")
                    version_model_ml = 1
                    found_model = True
                    print(f"Loaded champion model from run {run_id}")
                    break
            
            if not found_model:
                raise Exception("No champion model found in MLflow")
            
    except Exception as e:
        print(f"Error loading from MLflow: {str(e)}")
        # If there is no registry in MLflow, open the default model
        file_ml = open('/app/files/model.pkl', 'rb')
        model_ml = pickle.load(file_ml)
        file_ml.close()
        version_model_ml = 0
        print("Loaded default model from file")

    try:
        # Load information of the ETL pipeline from S3
        s3 = boto3.client('s3', endpoint_url='http://minio:9000', 
                         aws_access_key_id='minio', 
                         aws_secret_access_key='minio123')

        s3.head_object(Bucket='data', Key='data_info/data.json')
        result_s3 = s3.get_object(Bucket='data', Key='data_info/data.json')
        text_s3 = result_s3["Body"].read().decode()
        data_dictionary = json.loads(text_s3)

        data_dictionary["standard_scaler_mean"] = np.array(data_dictionary["standard_scaler_mean"])
        data_dictionary["standard_scaler_std"] = np.array(data_dictionary["standard_scaler_std"])
    except Exception as e:
        print(f"Error loading from S3: {str(e)}")
        # If data dictionary is not found in S3, load it from local file
        file_s3 = open('/app/files/data.json', 'r')
        data_dictionary = json.load(file_s3)
        file_s3.close()
        data_dictionary["standard_scaler_mean"] = np.array(data_dictionary["standard_scaler_mean"])
        data_dictionary["standard_scaler_std"] = np.array(data_dictionary["standard_scaler_std"])
        print("Loaded data dictionary from local file")

    return model_ml, version_model_ml, data_dictionary


def check_model():
    """
    Check for updates in the model and update if necessary.

    The function checks the model registry to see if the version of the champion model has changed. If the version
    has changed, it updates the model and the data dictionary accordingly.

    :return: None
    """

    global model
    global data_dict
    global version_model

    try:
        # First try with the registered model name
        model_name = "star_classification_model"
        
        mlflow.set_tracking_uri('http://mlflow:5000')
        client = mlflow.MlflowClient()

        # Try to get the latest model by searching for champion tag across experiments
        experiments = client.search_experiments()
        latest_champion_run_id = None
        
        for exp in experiments:
            runs = client.search_runs(
                experiment_ids=[exp.experiment_id],
                filter_string="tags.model_status = 'champion'",
                order_by=["attribute.start_time DESC"],
                max_results=1
            )
            
            if len(runs) > 0:
                latest_champion_run_id = runs[0].info.run_id
                break
        
        if latest_champion_run_id:
            # Load the new model
            new_model = mlflow.sklearn.load_model(f"runs:/{latest_champion_run_id}/LogReg_Grif")
            
            # If we have a new model (comparing by run_id)
            if latest_champion_run_id != getattr(model, "_run_id", None):
                print(f"Updating model from run {latest_champion_run_id}")
                model = new_model
                # Store run_id to check future updates
                model._run_id = latest_champion_run_id
                version_model += 1
                
                # Also reload the data dictionary
                try:
                    file_s3 = open('/app/files/data.json', 'r')
                    data_dict = json.load(file_s3)
                    file_s3.close()
                    data_dict["standard_scaler_mean"] = np.array(data_dict["standard_scaler_mean"])
                    data_dict["standard_scaler_std"] = np.array(data_dict["standard_scaler_std"])
                    print("Reloaded data dictionary")
                except Exception as e:
                    print(f"Error reloading data dictionary: {str(e)}")
        
    except Exception as e:
        print(f"Error in check_model: {str(e)}")
        # If an error occurs during the process, pass silently
        pass


class ModelInput(BaseModel):
    """
    Input schema for the star classification model.

    This class defines the input fields required by the star classification model along with their descriptions
    and validation constraints.

    :param alpha: Right ascension angle (SDSS coordinate system) in degrees.
    :param delta: Declination angle (SDSS coordinate system) in degrees.
    :param u: Ultraviolet filter in the photometric system.
    :param g: Green filter in the photometric system.
    :param r: Red filter in the photometric system.
    :param i: Near-infrared filter in the photometric system.
    :param z: Infrared filter in the photometric system.
    :param redshift: Redshift value based on the increase in wavelength.
    :param MJD: Modified Julian Date used to indicate when the astronomical data was taken.
    """

    alpha: float = Field(
        description="Right ascension angle (SDSS coordinate system) in degrees",
        ge=0,
        le=360,
    )
    delta: float = Field(
        description="Declination angle (SDSS coordinate system) in degrees",
        ge=-90,
        le=90,
    )
    u: float = Field(
        description="Ultraviolet filter in the photometric system",
    )
    g: float = Field(
        description="Green filter in the photometric system",
    )
    r: float = Field(
        description="Red filter in the photometric system",
    )
    i: float = Field(
        description="Near-infrared filter in the photometric system",
    )
    z: float = Field(
        description="Infrared filter in the photometric system",
    )
    redshift: float = Field(
        description="Redshift value based on the increase in wavelength",
        ge=0,
    )
    MJD: float = Field(
        description="Modified Julian Date used to indicate when the astronomical data was taken",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "alpha": 118.663,
                    "delta": 39.234,
                    "u": 23.87,
                    "g": 22.38,
                    "r": 20.94,
                    "i": 19.11,
                    "z": 17.32,
                    "redshift": 0.14,
                    "MJD": 51663.12
                }
            ]
        }
    }


class ModelOutput(BaseModel):
    """
    Output schema for the star classification model.

    This class defines the output fields returned by the star classification model along with their descriptions
    and possible values.

    :param class_id: Numeric ID of the predicted class (0: star, 1: galaxy, 2: quasar).
    :param class_name: Name of the predicted class ('STAR', 'GALAXY', 'QSO').
    :param probabilities: Probability distribution across all possible classes.
    """

    class_id: int = Field(
        description="Numeric ID of the predicted class (0: STAR, 1: GALAXY, 2: QSO)",
    )
    class_name: Literal["STAR", "GALAXY", "QSO"] = Field(
        description="Name of the predicted class",
    )
    probabilities: List[float] = Field(
        description="Probability distribution across all possible classes [STAR, GALAXY, QSO]",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "class_id": 1,
                    "class_name": "GALAXY",
                    "probabilities": [0.05, 0.85, 0.10]
                }
            ]
        }
    }


# Load the model before start
model, version_model, data_dict = load_model("star_classification_model", "champion")

app = FastAPI(
    title="Star Classification API",
    description="API for classifying astronomical objects as stars, galaxies, or quasars",
    version="1.0.0",
)


@app.get("/")
async def read_root():
    """
    Root endpoint providing basic information about the API.

    :return: A welcome message with information about the API.
    """
    return {
        "message": "Welcome to the Star Classification API!",
        "description": "Use this API to classify astronomical objects as stars, galaxies, or quasars.",
        "endpoints": {
            "/predict": "Send stellar data to get a classification prediction",
            "/health": "Check the health status of the API",
            "/model-info": "Get information about the current model in use"
        }
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint to verify the API is functioning properly.

    :return: A status message indicating the API is operational.
    """
    return {
        "status": "healthy",
        "model_version": version_model
    }


@app.get("/model-info")
async def model_info():
    """
    Provides information about the currently loaded model.

    :return: Details about the model version and relevant metadata.
    """
    try:
        mlflow.set_tracking_uri('http://mlflow:5000')
        client = mlflow.MlflowClient()
        model_data = client.get_model_version_by_alias("star_classification_model_prod", "champion")
        
        return {
            "model_name": "star_classification_model_prod",
            "model_version": version_model,
            "model_type": type(model).__name__,
            "creation_timestamp": model_data.creation_timestamp,
            "last_updated_timestamp": model_data.last_updated_timestamp,
            "description": "Star classification model to categorize astronomical objects",
            "input_features": ["alpha", "delta", "u", "g", "r", "i", "z", "redshift", "MJD"],
            "output_classes": ["STAR", "GALAXY", "QSO"]
        }
    except:
        return {
            "model_name": "star_classification_model_prod",
            "model_version": version_model,
            "model_type": type(model).__name__,
            "description": "Star classification model to categorize astronomical objects",
            "input_features": ["alpha", "delta", "u", "g", "r", "i", "z", "redshift", "MJD"],
            "output_classes": ["STAR", "GALAXY", "QSO"]
        }


@app.post("/predict/", response_model=ModelOutput)
def predict(
    features: Annotated[
        ModelInput,
        Body(embed=True),
    ],
    background_tasks: BackgroundTasks
):
    """
    Predict the class of an astronomical object based on input features.

    This endpoint recieves features from stellar data and returns a classification prediction (STAR, GALAXY, or QSO).

    :param features: Input features for the prediction.
    :param background_tasks: Background tasks to run after the request.
    :return: Prediction result indicating the class of the astronomical object.
    """
    # Schedule a background task to check for model updates
    background_tasks.add_task(check_model)

    try:
        # Convert the input to a pandas DataFrame
        input_df = pd.DataFrame([{
            'alpha': features.alpha,
            'delta': features.delta,
            'u': features.u,
            'g': features.g,
            'r': features.r,
            'i': features.i,
            'z': features.z,
            'redshift': features.redshift
        }])
        
        # Calculate Month from MJD if needed (similar to how it's done in the TL DAG)
        from astropy.time import Time
        mjd_date = Time(features.MJD, format='mjd').to_datetime()
        input_df['Month'] = mjd_date.month
        
        # Apply normalization using the scaler parameters from the data dictionary
        numerical_features = ["alpha", "delta", "u", "g", "r", "i", "z", "redshift", "Month"]
        for i, feature in enumerate(numerical_features):
            if feature in input_df.columns:
                input_df[feature] = (input_df[feature] - data_dict["standard_scaler_mean"][i]) / data_dict["standard_scaler_std"][i]
        
        # Make the prediction
        try:
            prediction = model.predict(input_df)[0]
            # Handle both string and int predictions
            if isinstance(prediction, str):
                if prediction == "STAR":
                    class_id = 0
                elif prediction == "GALAXY":
                    class_id = 1
                elif prediction == "QSO":
                    class_id = 2
                else:
                    class_id = int(prediction)  # Try to convert to int
                class_name = prediction
            else:
                class_id = int(prediction)
                class_map = {0: "STAR", 1: "GALAXY", 2: "QSO"}
                class_name = class_map.get(class_id, "UNKNOWN")
        except Exception as predict_error:
            print(f"Error during prediction: {str(predict_error)}")
            # Default to a simple prediction if model prediction fails
            class_id = 0
            class_name = "STAR"
        
        # Get probabilities if the model supports it
        try:
            probabilities = model.predict_proba(input_df)[0].tolist()
        except:
            # If predict_proba is not available, create a simple probability distribution
            probabilities = [0.0, 0.0, 0.0]
            probabilities[class_id] = 1.0
        
        # Create the response
        result = ModelOutput(
            class_id=class_id,
            class_name=class_name,
            probabilities=probabilities
        )
        
        return jsonable_encoder(result)
    
    except Exception as e:
        print(f"Prediction error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Prediction error: {str(e)}"}
        )


@app.post("/batch-predict/")
def batch_predict(
    features_list: List[ModelInput],
    background_tasks: BackgroundTasks
):
    """
    Predict the class of multiple astronomical objects in a batch.

    This endpoint accepts a list of stellar data entries and returns classification predictions for each.
    
    :param features_list: List of input features for batch prediction.
    :param background_tasks: Background tasks to run after the request.
    :return: List of prediction results.
    """
    # Schedule a background task to check for model updates
    background_tasks.add_task(check_model)
    
    results = []
    
    try:
        # Convert the inputs to a pandas DataFrame
        input_data = []
        for features in features_list:
            input_data.append({
                'alpha': features.alpha,
                'delta': features.delta,
                'u': features.u,
                'g': features.g,
                'r': features.r,
                'i': features.i,
                'z': features.z,
                'redshift': features.redshift,
                'MJD': features.MJD
            })
        
        input_df = pd.DataFrame(input_data)
        
        # Calculate Month from MJD
        from astropy.time import Time
        input_df['Gregorian_Date'] = Time(input_df['MJD'], format='mjd').to_datetime()
        input_df['Month'] = input_df['Gregorian_Date'].dt.month
        input_df = input_df.drop(['Gregorian_Date', 'MJD'], axis=1)
        
        # Apply normalization
        numerical_features = ["alpha", "delta", "u", "g", "r", "i", "z", "redshift", "Month"]
        for i, feature in enumerate(numerical_features):
            if feature in input_df.columns:
                input_df[feature] = (input_df[feature] - data_dict["standard_scaler_mean"][i]) / data_dict["standard_scaler_std"][i]
        
        # Make predictions
        try:
            predictions = model.predict(input_df).tolist()
            class_ids = []
            class_names = []
            
            # Handle different prediction types
            for pred in predictions:
                if isinstance(pred, str):
                    if pred == "STAR":
                        class_ids.append(0)
                    elif pred == "GALAXY":
                        class_ids.append(1)
                    elif pred == "QSO":
                        class_ids.append(2)
                    else:
                        class_ids.append(int(pred))
                    class_names.append(pred)
                else:
                    class_ids.append(int(pred))
                    class_map = {0: "STAR", 1: "GALAXY", 2: "QSO"}
                    class_names.append(class_map.get(int(pred), "UNKNOWN"))
        except Exception as predict_error:
            print(f"Error during batch prediction: {str(predict_error)}")
            # Default to simple predictions if model prediction fails
            class_ids = [0] * len(input_df)
            class_names = ["STAR"] * len(input_df)
        
        # Get probabilities if available
        try:
            all_probabilities = model.predict_proba(input_df).tolist()
        except:
            # If predict_proba is not available, create simple probability distributions
            all_probabilities = []
            for class_id in class_ids:
                probs = [0.0, 0.0, 0.0]
                probs[class_id] = 1.0
                all_probabilities.append(probs)
        
        # Create results
        for i, class_id in enumerate(class_ids):
            results.append({
                "class_id": class_id,
                "class_name": class_names[i],
                "probabilities": all_probabilities[i]
            })
        
        return jsonable_encoder(results)
    
    except Exception as e:
        print(f"Batch prediction error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Batch prediction error: {str(e)}"}
        )
