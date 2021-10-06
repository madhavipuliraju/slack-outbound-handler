import json
import requests
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_chat_transcripts(creds, user_name, conversation_number):
    """
    Returns the chat transcript Text
    """
    url = "https://staging.hellohaptik.com/integration/external/v1.0/get_chat_history/"
    parameters = {
        "user_name": user_name,
        "business_id": int(creds["bot_business"]),
        "response_type": "text",
        "conversation_no": conversation_number
    }
    headers = {
        "Content-Type": "application/json",
        "client-id": creds["bot_client_id"],
        "Authorization": creds["bot_chat_auth"]
    }
    response = requests.request("GET", url, params=parameters, headers=headers)
    logging.debug(f"Response of the Chat history API:\n{response.text}")
    if response.status_code == 200:
        return response.json().get("chat_text")
    logging.error(f"Chat history API return unhandled status_code:\n{response.status_code}")
