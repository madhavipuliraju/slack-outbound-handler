import json
import requests
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def send_message_to_slack(creds, channel, message, is_agent, agent_name):
    # Sends message to slack user
    url = "https://slack.com/api/chat.postMessage"
    headers = {
        'Content-Type': "application/json",
        'Authorization': creds["slack_auth"]
    }
    
    data = {
        "channel": channel,
        "text": message
    }
    
    if is_agent:
        data["username"] = agent_name
        data["icon_emoji"] = ":computer:"
    try:
        logger.info(
            f"Sending message to slack with payload:\n{data} and headers:\n{headers}")
        response = requests.request("POST", url, headers=headers, json=data)
        logger.debug(f"Response of send message to slack:\n{response.text}")
        logger.info(f"Response Status Code of send message to slack:\n{response.status_code}")
        logger.info(f"Payload of send message to slack:\n{data}")
        if response.status_code == 200:
            return response
        else:
            raise Exception(
                f"[UNEXPECTED STATUS CODE: {response.status_code}]")
    except Exception as ex:
        logger.error(
            f"Encountered exception while sending message to slack:\n{ex}")

def send_block_message_to_slack(item_list, creds, channel, message, is_agent, agent_name):
    """
    Sends message to slack user
    """
    url = "https://slack.com/api/chat.postMessage"
    headers = {
        'Content-Type': "application/json",
        'Authorization': creds["slack_auth"]
    }
    
    data = {
        "channel":channel,
        "text": message,
        "blocks":[
            {
                "type":"actions",
                "block_id":"actionblock789",
                "elements": item_list
            }
        ]
    }
    
    if is_agent:
        data["username"] = agent_name
        data["icon_emoji"] = ":computer:"
    try:
        logger.info(
            f"Sending block message to slack with payload:\n{data} and headers:\n{headers}")
        response = requests.request("POST", url, headers=headers, json=data)
        logger.debug(f"Response of send block message to slack:\n{response.text}")
        logger.info(f"Response Status Code of send block message to slack:\n{response.status_code}")
        logger.info(f"Payload of send block message to slack:\n{data}")
        if response.status_code == 200:
            return response
        else:
            raise Exception(
                f"[UNEXPECTED STATUS CODE: {response.status_code}]")
    except Exception as ex:
        logger.error(
            f"Encountered exception while sending block message to slack:\n{ex}")


def send_file_to_slack(creds, channel, text, thumb_url, is_agent, agent_name):
    """
    Sends the Attachment to Slack
    """
    url = "https://slack.com/api/chat.postMessage"
    attachments = [{"text": text, "id": 1, "fallback": "",
                    "image_url": thumb_url, "thumb_url": thumb_url}]
    headers = {
        "Content-Type": "application/json",
        "Authorization": creds["slack_auth"]
    }
    data = {
        "channel": channel,
        "attachments": json.dumps(attachments)
    }
    if is_agent:
        data["username"] = agent_name
        data["icon_emoji"] = ":computer:"
    try:
        logger.info(
            f"Sending file to slack with payload:\n{data} and headers:\n{headers}")
        slack_response = requests.post(
            url, data=json.dumps(data), headers=headers)
        logger.debug(
            f"Response of send message to slack:\n{slack_response.text}")
        if slack_response.status_code == 200:
            return slack_response
        else:
            raise Exception(
                f"[UNEXPECTED STATUS CODE: {slack_response.status_code}]")
    except Exception as ex:
        logger.error(
            f"Encountered exception while sending message to slack:\n{ex}")
