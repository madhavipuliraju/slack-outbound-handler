import json
import logging
import os
import boto3
from datetime import datetime
from db_helper import get_creds
from slack_helper import send_message_to_slack, send_file_to_slack, send_block_message_to_slack
from haptik_helper import get_chat_transcripts
from translation_helper import handle_message_translation
from profiler import profile
from kendra_helper import search_kendra
# from bs4 import BeautifulSoup

logger = logging.getLogger()
logger.setLevel(logging.INFO)


lambda_client = boto3.client("lambda")

db_service = boto3.resource("dynamodb")
user_mapping_table = db_service.Table(os.environ.get('slack_mapping_table'))
client_mapping_table = db_service.Table(os.environ.get('client_mapping_table'))


@profile
def lambda_handler(event, context):
    """
    Analyzes the event and sends the message to user in slack
    """
    client_id = event.get("client_id")
    itsm = event.get("itsm")
    user_id = event.get("user")
    payload = event.get("body")

    creds = get_creds(client_id)

    event_name = payload.get('event_name', "")
    is_automated = payload.get("agent", {}).get("is_automated")
    
    user_response = client_mapping_table.get_item(Key={"client_id": client_id})
    if "Item" in user_response:
        is_translation = user_response.get("Item", {}).get("is_translation", "")
    else:
        logger.info(f"Items not found for the client:   {client_id}")

    if 'webhook_conversation_complete' in event_name:
        logger.info("Received Conversation completed event")
        handle_resolution_event(is_translation, creds, payload, user_id,
                                is_automated, itsm, client_id)
    elif "message" in event_name:
        logger.info("Received Message event")
        handle_message_event(is_translation, creds, payload, user_id,
                             is_automated, itsm, client_id)
    elif "chat_pinned" in event_name:
        logger.info("Received Chat Pinned event")
        handle_pinned_event(is_translation, creds, payload, user_id)
    else:
        logger.info(f"Received Unsupported event: {event_name}")

    return {
        'statusCode': 200,
        'body': json.dumps('Hello from Lambda!')
    }


def handle_pinned_event(is_translation, creds, payload, user_id):
    """
    Posts a message in the chat window that a user has entered the conversation
    """
    try:
        agent_name = payload.get("agent", {}).get("name").title()
    except AttributeError:
        agent_name = "IT Agent"
    message = f"----- *{agent_name} has entered the conversation* -----"

    if is_translation:
        logger.info("is_translation is True. Translation function is called")
        message = handle_message_translation(message, user_id)
    data = {
        "channel": user_id.split("_")[1],
        "text": message
    }
    response = user_mapping_table.get_item(Key={"user_id": user_id})

    if "Item" in response:
        im_channel = response.get("Item", {}).get("im_channel")
        if im_channel:
            logger.info("Found IM channel ID for sending the message as agent")
            response = send_message_to_slack(creds, im_channel,
                                             message, True, agent_name)
            store_message_in_DB(message, user_id, agent_name)
        else:
            logger.info("IM channel ID doesn't exist for agent chat")
            response = send_message_to_slack(creds, user_id.split("_")[1],
                                             message, False, "")
            store_message_in_DB(message, user_id, "BOT")
        user_mapping_table.update_item(
            Key={"user_id": user_id},
            UpdateExpression="set agent_name=:a",
            ExpressionAttributeValues={
                ":a": agent_name
            })
    else:
        logger.error(f"Couldn't find the user:{user_id} in DB")
        response = send_message_to_slack(
            creds, user_id.split("_")[1], message, False, "")
        store_message_in_DB(message, user_id, "BOT")


def handle_message_event(is_translation, creds, payload, user_id, is_automated, itsm, client_id):
    """
    Handles incoming message event
    """
    logger.info("Handling Message event")
    message = payload.get("message", {}).get("body", {}).get("text", "")
    # is_html =bool(BeautifulSoup(message, "html.parser").find())
    message_type = payload.get("message", {}).get("body", {}).get("type", "")
    agent_name = "IT Agent"
    response = user_mapping_table.get_item(Key={"user_id": user_id})
    email = response.get("Item", {}).get("email")
    query = response.get("Item", {}).get("latest_message")
    im_channel = response.get("Item", {}).get("im_channel")
    
    # if is_html:
    #     message = message.replace("<br>", "\n")
    #     message = message.replace("<strong>","\033[1m")
    #     message = message.replace("</strong>","\033[0m")
    
    item_list = []
    logger.info(response)
    if 'BOT BREAK' in message or payload.get("message", {}).get("body", {}).get("data", {}).get("intents"):
        item_json = {
                        "type":"button",
                        "text":{
                            "type":"plain_text",
                            "text": "Talk to an agent 💬"
                        },
                        "value":"Talk to an agent 💬"
                    }
        item_list.append(item_json)
        disambiguation_list = payload.get("message", {}).get("body", {}).get("data", {}).get("intents", [])
        for Item in disambiguation_list:
            item_json = {
                        "type":"button",
                        "text":{
                            "type":"plain_text",
                            "text": f"{Item} 💬"
                        },
                        "value":Item
                    }
            item_list.append(item_json)
        return handle_kendra_search(item_list, query, creds, user_id, agent_name, im_channel)
    if "Item" in response:
        try:
            im_channel = response.get("Item", {}).get("im_channel")
            agent_name = response.get("Item", {}).get("agent_name").title()
        except AttributeError:
            agent_name = "IT Agent"
    else:
        im_channel = ""
        agent_name = "IT Agent"

    if 'BUTTON' in message_type:
        message_url_items = payload.get("message", {}).get(
            "body", {}).get("data", {}).get("items", [{}])
        for Item in message_url_items:
            thumb_url = Item.get("payload", {}).get("url", "")
            actionable_text = Item.get("actionable_text", "")
            uri = Item.get("uri", "")
            item_type = Item.get("type", "")
            item_message = Item.get("payload", {}).get("message", "")
            is_agent = bool(im_channel) if not is_automated else False
            if item_type.lower() == "app_action" and uri.lower() == "link":
                if ".pdf" in thumb_url or ".docx" in thumb_url:
                    if is_agent:
                        item_json = {
                            "type":"button",
                            "text":{
                                "type":"plain_text",
                                "text": f"{actionable_text} 📎"
                            },
                            "url": thumb_url
                        }
                        item_list.append(item_json)
                        store_message_in_DB("ATTACHMENT", user_id, agent_name)
                    else:
                        item_json = {
                            "type":"button",
                            "text":{
                                "type":"plain_text",
                                "text": f"{actionable_text} 📎"
                            },
                            "url": thumb_url
                        }
                        item_list.append(item_json)
                        store_message_in_DB("ATTACHMENT", user_id, "BOT")
                    if ".pdf" in thumb_url:
                        file_type = "pdf"
                    else:
                        file_type = "docx"
                    ticket_attachment_invoke(file_type, itsm, user_id, client_id, email, actionable_text, thumb_url)
                else:
                    item_json = {
                            "type":"button",
                            "text":{
                                "type":"plain_text",
                                "text": f"{actionable_text} 🔗"
                            },
                            "url": thumb_url
                        }
                    item_list.append(item_json)
            elif item_type.lower() == "text_only":
                item_json = {
                        "type":"button",
                        "text":{
                            "type":"plain_text",
                            "text": f"{actionable_text} 💬"
                        },
                        "value":item_message
                    }
                item_list.append(item_json)

        if message:
            message = message
        else:
            # message = f"You can use this URL to download the file."
            message = "You can click the below button to download the file."
        # if thumb_url:
        #     data = button_payload(user_id.split("_")[1], message, item_list)

    if "CAROUSEL" in message_type:
        logger.info("Incoming Attachment Detected")
        attachment_items = payload.get("message", {}).get(
            "body", {}).get("data", {}).get("items", [])
        is_agent = bool(im_channel) if not is_automated else False
        for files in attachment_items:
            thumb_url = files.get("thumbnail", {}).get("image", "")
            text = files.get("title", "")
            if is_agent:
                send_file_to_slack(creds, im_channel, text,
                                   thumb_url, True, agent_name)
                store_message_in_DB("IMAGE", user_id, agent_name)
            else:
                send_file_to_slack(creds, user_id.split("_")[1],
                                   text, thumb_url, False, "")
                store_message_in_DB("IMAGE", user_id, "BOT")
            ticket_attachment_invoke("png", itsm, user_id, client_id, email, text, thumb_url)
        return

    if is_translation:
        logger.info("is_translation is True. Translation function is called")
        message = handle_message_translation(message, user_id)
    if not is_automated:
        logger.info("Sending message as Agent")
        if im_channel:
            logger.info("Found IM channel ID for sending the message as agent")
            response = send_message_to_slack(
                    creds, im_channel, message, True, agent_name)
            if item_list:
                response = send_block_message_to_slack(
                    item_list, creds, im_channel, message, True, agent_name)
            store_message_in_DB(message, user_id, agent_name)
        else:
            logger.info("IM channel ID doesn't exist for agent chat")
            response = send_message_to_slack(
                    creds, user_id.split("_")[1], message, False, "")
            if item_list:
                response = send_block_message_to_slack(
                item_list, creds, user_id.split("_")[1], message, False, "")
            store_message_in_DB(message, user_id, "BOT")
    else:
        logger.info("Received Automated message sending in the DM as bot")
        response = send_message_to_slack(
                creds, user_id.split("_")[1], message, False, "")
        if item_list:
                response = send_block_message_to_slack(
                item_list, creds, user_id.split("_")[1], message, False, "")  
        store_message_in_DB(message, user_id, "BOT")

    if not im_channel and response:
        logger.info(
            "IM Channel ID was not available adding it to the DB from response")
        user_mapping_table.update_item(Key={"user_id": user_id},
                                       UpdateExpression="set im_channel=:i",
                                       ExpressionAttributeValues={
                                           ":i": response.json().get("channel")
        })


def handle_resolution_event(is_translation, creds, payload, user_id, is_automated, itsm, client_id):
    """
    Handles webhook_conversation_complete event
    """
    user_name = payload.get("user", {}).get("user_name")
    conversation_number = payload.get("data", {}).get("conversation_no")

    chat_text = get_chat_transcripts(creds, user_name, conversation_number)
    logger.debug(chat_text)

    message = "----- *This conversation is marked as completed* -----"
    
    if is_translation:
        logger.info("is_translation is True. Translation function is called")
        message = handle_message_translation(message, user_id)
    send_message_to_slack(creds, user_id.split("_")[1],
                          message, False, "")
    store_message_in_DB(message, user_id, "BOT")
    data = {
        "itsm": itsm,
        "payload": {
            "client_id": client_id,
            "source": "slack",
            "event": "TICKET_RESOLUTION",
            "user": user_id,
            "chat_history": chat_text,
            "is_automated": is_automated
        }
    }
    logger.info(f"Data being passed to ticketing function is: {data}")
    lambda_client.invoke(FunctionName=os.environ.get("ticketing_handler_arn"),
                         InvocationType="Event",
                         Payload=json.dumps(data))

def store_message_in_DB(message, user_id, agent_name):
    """
    Stores the Chat message in the DB as chat_transcript.
    """
    user_mapping_table = db_service.Table(os.environ.get('slack_mapping_table'))
    response = user_mapping_table.get_item(Key={"user_id": user_id})
    if "Item" not in response:
        logger.error(f"User: {user_id} not found in the Table")    
        return
    chat_transcript = response.get("Item", {}).get("chat_transcript")
    formatted_time = datetime.now().strftime("%H:%M:%S %d-%m-%Y")
    message = f"{formatted_time} [{agent_name}]: {message}"
    if chat_transcript:
        message = f"{chat_transcript}\n{message}"
        
    user_mapping_table.update_item(Key={"user_id": user_id},
                                UpdateExpression="set chat_transcript=:i",
                                ExpressionAttributeValues={
                                    ":i": message
                                })
    return

def ticket_attachment_invoke(file_type, itsm, user_id, client_id, email, text, thumb_url):
    ticket_data = {
        "itsm": itsm,
        "payload": {
            "event": "TICKET_ATTACHMENT",
            "source": "slack",
            "user": user_id,
            "from_haptik": True,
            "client_id": client_id,
            "email": email,
            "file_type": file_type,
            "file_name": f"{text}.{file_type}" if text else "file.{file_type}",
            "file_link": thumb_url
        }
    }

    logger.info(
        f"Data being passed to ticketing function is: {ticket_data}")
    lambda_client.invoke(FunctionName=os.environ.get("ticketing_handler_arn"),
                            InvocationType="Event",
                            Payload=json.dumps(ticket_data))
                            
                            
def handle_kendra_search(item_list: list, query: str, creds: dict, user_id: str, agent_name: str, im_channel: str):
    """
    When bot break or disamb message is sent it will query Kendra for results
    """
    message, link = search_kendra(query)
    new_list = []
    if link:
        new_list.append({
           "type":"button",
           "text":{
              "type":"plain_text",
              "text":"Visit Link 🔗"
           },
           "url":link
        })
    new_list.extend(item_list)
    logger.info(new_list)
    send_block_message_to_slack(new_list, creds, im_channel, message, False, agent_name)
    store_message_in_DB(message, user_id, agent_name)