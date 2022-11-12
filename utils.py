import configparser
import json
import time
from urllib.request import Request, urlopen


# load configuration
# ------------------

config = configparser.ConfigParser()
config.read("config.ini")


# mailing
# -------------

mailing_config = config.get('MAILING')
MAIL_ENABLED = mailing_config.getboolean('MailEnabled')
MAIL_API_URL = mailing_config.get('MailAPIURL')
MAIL_API_TOKEN = mailing_config.get('MailAPIToken')
MAIL_SENDER_EMAIL = mailing_config.get('MailSenderEmail')
MAIL_SENDER_NAME = mailing_config.get('MailSenderName')


def construct_request_payload(emails, subject, body):
    payload = dict()

    # sender
    payload["sender"] = {
        "email": MAIL_SENDER_EMAIL,
        "name": MAIL_SENDER_NAME
    }

    # to
    payload["to"] = [{"email": MAIL_SENDER_EMAIL}]

    # bcc
    if len(emails) > 0:
        bcc_list = []
        for email in emails:
            bcc_list.append({"email": email})
        payload["bcc"] = bcc_list

    # subject & body
    payload["subject"] = f"[Bodulica] {subject}"
    payload["htmlContent"] = body

    return payload


def send_email(emails, subject, body):
    """
    Sends emails via SendInBlue service.
    """
    if MAIL_ENABLED:
        payload = construct_request_payload(emails, subject, body)
        data = str(json.dumps(payload)).encode('utf-8')
        request = Request(f'{MAIL_API_URL}', data=data, method='POST')
        request.add_header('api-key', MAIL_API_TOKEN)
        request.add_header('Content-Type', 'application/json')
        time.sleep(0.5)
        urlopen(request)


def get_settlement_names_and_tags(islands, island_name):
    """
    Returns list of settlement names and tags for an island name as an input.

    - Input:
    islands: list of dictionaries
    island_name: 'ugljan'

    - Output:
    [{'name': 'ugljan', 'tags': 'ugljan'},
    {'name': 'lukoran', 'tags': 'lukoran'},
    {'name': 'sutomiscica', 'tags': 'sutomišćica'},
    {'name': 'poljana', 'tags': 'poljana'},
    {'name': 'preko', 'tags': 'preko'},
    {'name': 'kali', 'tags': 'kali'},
    {'name': 'kukljica', 'tags': 'kukljica'}]
    """
    # process
    island = next((item for item in islands if item['name'] == island_name), None)
    if island:
        settlements = island.get('settlements', [])
        if settlements:
            results = []
            for settlement in settlements:
                result = {
                    "name": settlement.get('name'),
                    "tags": settlement.get('tags'),
                }
                results.append(result)
            return results
    return []