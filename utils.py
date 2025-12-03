import configparser
import json
import time
from urllib.request import Request, urlopen

# from sympy.utilities.iterables import necklaces


# load configuration
# ------------------

config = configparser.ConfigParser()
config.read("config.ini")


# mailing
# -------

mailing_config = config['MAILING']
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

def get_email_footer():
    return '<br><p>---</p>'\
        '<a href="https://skoljarev.com/bodulica/">'\
        'https://skoljarev.com/bodulica/</a>'


# string utils
# ------------

def get_substring_positions(s, substring):
    """
    Returns before and after substring positions.
    """
    index_of_occurrences = []
    final_index = []
    current_index = 0
    while True:
        current_index = s.find(substring, current_index)
        if current_index == -1:
            for i in index_of_occurrences:
                final_index.append(i)
            return final_index
        else:
            index_of_occurrences.append(current_index)
            current_index += len(substring)


def insert_into_string(s, index, character):
    string_list = list(s)
    string_list[index] = character
    return "".join(string_list)


def enumerate_with_step(items, start=0, step=2):
    for item in items:
        yield (start, item)
        start += step


# def get_multiset_permutations(s):
#     """
#     Returns string combinations with multiset permutations of spaces
#     before and after character '-' in a string.
#     """
#     results = list()
#     substring_positions = get_substring_positions(s, '-')
#     print("### substring_positions", substring_positions)
#     positions_length = len(substring_positions) * 2
#     combinations = list(necklaces(positions_length, 3))
#     print("### combinations", combinations)

#     for number_spaces in combinations:
#         generated_string = s
#         for i, position in enumerate(substring_positions):
#             spaces = ''
#             for item in range(0, number_spaces, 2):
#                 spaces += ' '
#                 generated_string = insert_into_string(generated_string, position, spaces)
#             substring_positions = get_substring_positions(generated_string, '-')
#         results.append(generated_string)
#     return results