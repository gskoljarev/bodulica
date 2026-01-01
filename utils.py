import configparser
import json
import re
import time
from urllib.request import Request, urlopen

from babel.dates import format_datetime
from dateutil import parser


# constants
# ---------

# hyphen variants + minus + normal hyphen
DASHES = "\u2010\u2011\u2012\u2013\u2014\u2212-"

_dash_re = re.compile(f"[{re.escape(DASHES)}]")
_ws_re = re.compile(r"\s+")
_space_around_dash_re = re.compile(r"\s*-\s*")


# load configuration
# ------------------

config = configparser.ConfigParser()
config.read("config.ini")

mailing_config = config['MAILING']
MAIL_ENABLED = mailing_config.getboolean('MailEnabled')
MAIL_API_URL = mailing_config.get('MailAPIURL')
MAIL_API_TOKEN = mailing_config.get('MailAPIToken')
MAIL_SENDER_EMAIL = mailing_config.get('MailSenderEmail')
MAIL_SENDER_NAME = mailing_config.get('MailSenderName')


# mailing
# -------

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
    Sends emails via the Brevo service (formerly SendInBlue).

    https://www.brevo.com
    """
    if MAIL_ENABLED:
        payload = construct_request_payload(emails, subject, body)
        data = str(json.dumps(payload)).encode('utf-8')
        request = Request(f'{MAIL_API_URL}', data=data, method='POST')
        request.add_header('api-key', MAIL_API_TOKEN)
        request.add_header('Content-Type', 'application/json')
        time.sleep(0.5)
        urlopen(request)


def get_email_footer():
    return '<br><p>---</p>'\
        '<a href="https://skoljarev.com/bodulica/">'\
        'https://skoljarev.com/bodulica/</a>'


# string utils
# ------------

def normalize_for_match(s: str) -> str:
    # Normalize common copy/paste whitespace
    s = s.replace("\u00A0", " ")  # NBSP -> space

    # Normalize all dash-like characters to "-"
    s = _dash_re.sub("-", s)

    # Collapse whitespace runs
    s = _ws_re.sub(" ", s).strip()

    # Remove spaces around dashes so all boundaries become just "-"
    s = _space_around_dash_re.sub("-", s)

    # Case-insensitive (Unicode-aware)
    return s.casefold()


def contains_variant(text: str, canonical: str) -> bool:
    return normalize_for_match(canonical) in normalize_for_match(text)


# misc
# ----

def get_weekday_in_lang(date_str, lang):
    dt = parser.parse(date_str)
    return format_datetime(dt, "EEEE", locale=lang)


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