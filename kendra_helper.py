import boto3
import os
import logging

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

kendra = boto3.client('kendra')

def search_kendra(query):
    index_id = os.environ.get('index_id')
    response=kendra.query(QueryText = query, IndexId = index_id)
    logger.debug(f"Kendra Response for the query: {query} is:\n{response}")
    answer = ""
    link = ""
    for query_result in response['ResultItems']:
        if query_result['Type']=='ANSWER':
            answer = query_result['DocumentExcerpt']['Text']

        if query_result['Type']=='DOCUMENT':
            document_text = query_result['DocumentExcerpt']['Text']
            link = query_result["DocumentURI"]
            break
    if answer == '':
        if link == '':
            message = "Couldn't find the results for the given query, kindly try changing your phrase a bit"
        else:
            message = " ".join(document_text.split())
    else:
        message  = " ".join(answer.split())
    
    return message, link