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

        model_data_mlflow = client_mlflow.get_model_version_by_alias(model_name, alias)
        model_ml = mlflow.sklearn.load_model(model_data_mlflow.source)
        version_model_ml = int(model_data_mlflow.version)
    except:
        # If there is no registry in MLflow, open the default model
        file_ml = open('/app/files/model.pkl', 'rb')
        model_ml = pickle.load(file_ml)
        file_ml.close()
        version_model_ml = 0

    try:
        # Load information of the ETL pipeline from S3
        s3 = boto3.client('s3')

        s3.head_object(Bucket='data', Key='data_info/data.json')
        result_s3 = s3.get_object(Bucket='data', Key='data_info/data.json')
        text_s3 = result_s3["Body"].read().decode()
        data_dictionary = json.loads(text_s3)

        data_dictionary["standard_scaler_mean"] = np.array(data_dictionary["standard_scaler_mean"])
        data_dictionary["standard_scaler_std"] = np.array(data_dictionary["standard_scaler_std"])
    except:
        # If data dictionary is not found in S3, load it from local file
        file_s3 = open('/app/files/data.json', 'r')
        data_dictionary = json.load(file_s3)
        file_s3.close()

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
        model_name = "star_classification_model_prod"
        alias = "champion"

        mlflow.set_tracking_uri('http://mlflow:5000')
        client = mlflow.MlflowClient()

        # Check in the model registry if the version of the champion has changed
        new_model_data = client.get_model_version_by_alias(model_name, alias)
        new_version_model = int(new_model_data.version)

        # If the versions are not the same
        if new_version_model != version_model:
            # Load the new model and update version and data dictionary
            model, version_model, data_dict = load_model(model_name, alias)

    except:
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
model, version_model, data_dict = load_model("star_classification_model_prod", "champion")

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
        class_id = model.predict(input_df)[0]
        
        # Get probabilities if the model supports it
        try:
            probabilities = model.predict_proba(input_df)[0].tolist()
        except:
            # If predict_proba is not available, create a simple probability distribution
            probabilities = [0.0, 0.0, 0.0]
            probabilities[class_id] = 1.0
        
        # Map class ID to class name
        class_map = {0: "STAR", 1: "GALAXY", 2: "QSO"}
        class_name = class_map.get(class_id)
        
        # Create the response
        result = ModelOutput(
            class_id=int(class_id),
            class_name=class_name,
            probabilities=probabilities
        )
        
        return jsonable_encoder(result)
    
    except Exception as e:
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
        class_ids = model.predict(input_df).tolist()
        
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
        
        # Map class IDs to class names
        class_map = {0: "STAR", 1: "GALAXY", 2: "QSO"}
        
        # Create results
        for i, class_id in enumerate(class_ids):
            results.append({
                "class_id": class_id,
                "class_name": class_map.get(class_id),
                "probabilities": all_probabilities[i]
            })
        
        return jsonable_encoder(results)
    
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Batch prediction error: {str(e)}"}
        )
