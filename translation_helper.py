import boto3
import json
import logging
import os

logger = logging.getLogger()
logger.setLevel(logging.INFO)

lambda_client = boto3.client("lambda")


def handle_message_translation(message, user_id):
    payload = {
        "message": message,
        "user_id": user_id,
        "source": "agent"
    }
    response = lambda_client.invoke(FunctionName=os.environ.get("translation_service_arn"),
                                    InvocationType="RequestResponse",
                                    Payload=json.dumps(payload))
    response = json.load(response.get("Payload"))
    logger.debug(f"Response of translation service is: {response}")
    
    return response.get("translated_message")