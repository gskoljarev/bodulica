import configparser
import json
from urllib.request import Request, urlopen


# load configuration
# ------------------

config = configparser.ConfigParser()
config.read("config.ini")


# set constants
# -------------

mailing_config = config['MAILING']
MAIL_API_URL = mailing_config['MailAPIURL']
MAIL_API_TOKEN = mailing_config['MailAPIToken']


def construct_request_payload(emails, subject, body):
    payload = dict()
    # sender
    payload["sender"] = {
        "email": "gskoljarev@gmail.com",
        "name": "Bodulica App"
    }
    # to
    first_email = emails.pop()
    payload["to"] = [{"email": first_email}]
    # bcc
    if len(emails) > 0:
        first_email = emails.pop()
        bcc_list = []
        for email in emails:
            bcc_list.append({"email": email})
        if bcc_list:
            payload["bcc"] = bcc_list
    # subject & body
    payload["subject"] = f"[Bodulica] {subject}"
    payload["htmlContent"] = body

    return payload


def send_email(emails, subject, body):
    """
    Sends emails via SendInBlue service.
    """
    payload = construct_request_payload(emails, subject, body)
    data = str(json.dumps(payload)).encode('utf-8')
    request = Request(f'{MAIL_API_URL}', data=data, method='POST')
    request.add_header('api-key', MAIL_API_TOKEN)
    request.add_header('Content-Type', 'application/json')
    urlopen(request)