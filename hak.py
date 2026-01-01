import json
import logging
import random
import shutil
import string
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from time import sleep
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from utils import (
    get_email_footer,
    send_email,
    contains_variant
)


# set constants
# -------------

COMPANY_NAME = "HAK"
SCRIPT_NAME = "hak"
JOB_ID = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
NOW = datetime.now().strftime("%Y%m%d_%H%M%S")
DOWNLOAD_DELAY = 3

SOURCE_URL_MARITIME = "https://m.hak.hr/stanje.asp?id=3"
INFRASTRUCTURE_PATHS_MARITIME = [
    Path(f"{SCRIPT_NAME}/infrastructure/gp_sibenik.json"),
    Path(f"{SCRIPT_NAME}/infrastructure/gv_line_iadera.json"),
    Path(f"{SCRIPT_NAME}/infrastructure/kapetan_luka_krilo.json"),
    Path(f"{SCRIPT_NAME}/infrastructure/miatrade.json"),
    Path(f"{SCRIPT_NAME}/infrastructure/rpz_vrgada.json"),
    Path(f"{SCRIPT_NAME}/infrastructure/tp_line.json"),
    Path(f"jadrolinija/infrastructure.json"),
]
DOWNLOAD_PATH_MARITIME = Path(f"{SCRIPT_NAME}/data/page_mar.html")
ARCHIVE_PATH_MARITIME = Path(f"{SCRIPT_NAME}/data/page_mar_{NOW}_{JOB_ID}.html")
RESULTS_PATH_MARITIME = Path(f"{SCRIPT_NAME}/results_mar.log")

SOURCE_URL_ROADS = "https://m.hak.hr/stanje.asp?id=1"
INFRASTRUCTURE_PATHS_ROADS = [
    Path(f"{SCRIPT_NAME}/infrastructure/hc.json"),
    Path(f"{SCRIPT_NAME}/infrastructure/zuc_lsz.json"),
    Path(f"{SCRIPT_NAME}/infrastructure/zuc_s.json"),
    Path(f"{SCRIPT_NAME}/infrastructure/zuc_zz.json"),
]
DOWNLOAD_PATH_ROADS = Path(f"{SCRIPT_NAME}/data/page_roads.html")
ARCHIVE_PATH_ROADS = Path(f"{SCRIPT_NAME}/data/page_roads_{NOW}_{JOB_ID}.html")
RESULTS_PATH_ROADS = Path(f"{SCRIPT_NAME}/results_roads.log")

LOG_PATH = Path(f"{SCRIPT_NAME}/processing.log")
EMAIL_FOOTER = get_email_footer()


# setup logging
# -------------

logger = logging.getLogger("main")
logger.setLevel(logging.INFO)
formatter = logging.Formatter(
    f"%(asctime)s | %(levelname)s | {JOB_ID} | %(message)s"
)

stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setLevel(logging.DEBUG)
stdout_handler.setFormatter(formatter)
stdout_handler.stream = open(1, 'w', encoding="utf-8", buffering=1)

log_file_handler = logging.FileHandler(str(LOG_PATH.resolve()), encoding="utf-8")
log_file_handler.setLevel(logging.DEBUG)
log_file_handler.setFormatter(formatter)

logger.addHandler(log_file_handler)
logger.addHandler(stdout_handler)


# processing
# ----------

def process(source='maritime'):
    # handle source
    if source == 'maritime':
        SOURCE_URL = SOURCE_URL_MARITIME
        INFRASTRUCTURE_PATHS = INFRASTRUCTURE_PATHS_MARITIME
        DOWNLOAD_PATH = DOWNLOAD_PATH_MARITIME
        ARCHIVE_PATH = ARCHIVE_PATH_MARITIME
        RESULTS_PATH = RESULTS_PATH_MARITIME
    if source == 'roads':
        SOURCE_URL = SOURCE_URL_ROADS
        INFRASTRUCTURE_PATHS = INFRASTRUCTURE_PATHS_ROADS
        DOWNLOAD_PATH = DOWNLOAD_PATH_ROADS
        ARCHIVE_PATH = ARCHIVE_PATH_ROADS
        RESULTS_PATH = RESULTS_PATH_ROADS

    # prepare headers
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '\
                      'AppleWebKit/537.36 (KHTML, like Gecko) '\
                      'Chrome/107.0.0.0 Safari/537.36'
    }

    # download the page
    try:
        request = Request(SOURCE_URL)
        for key, value in headers.items(): 
            request.add_header(key, value)
        response = urlopen(request).read()
    except:
        logger.error(f"Error downloading data")
        return

    # create a download file it doesn't exist
    if not DOWNLOAD_PATH.exists():
        f = DOWNLOAD_PATH.open("wb+")
        f.close()

    # check if new data available
    f = DOWNLOAD_PATH.open("rb")
    existing_data = f.read()
    f.close()
    if existing_data == response:
        return
    
    # load infrastructure data
    units = list()
    for infrastructure_path in INFRASTRUCTURE_PATHS:
        with open(infrastructure_path.resolve(), "rb") as f:
            infrastructure = json.load(f)
            units.extend(infrastructure.get("units"))

    # create a results file it doesn't exist
    if not RESULTS_PATH.exists():
        f = RESULTS_PATH.open("w+")
        f.close()

    # open the existing results file
    with open(str(RESULTS_PATH.resolve()), encoding='utf-8') as f:
        existing_results = [
            line.strip() for line in f if line.strip()
        ]

    # process response
    soup = BeautifulSoup(response, 'html.parser')
    date_time_raw = soup.find('div', {'id': 'sitno'}).text
    date_raw, time_raw = date_time_raw.replace(
        'Pomorski promet', ''
    ).split(' ')
    content_raw = soup.find('ul', {'class': 'pageitem'}).text
    content = content_raw.strip().replace(
        ';', ' '
    ).replace(
        ':', ' '
    )

    results = []

    for unit in units:
        unit_name = unit.get("name")
        result = unit_name
        # check first if there is already a result for this unit
        if result not in results:
            unit_tags = unit.get("tags").split(",")
            # &nbsp; turns into \xa0 when splitting and
            # slavic alphabet characters are not parsed correctly,
            # so we normalize first
            content_value = unicodedata.normalize(
                "NFKC", content.lower()
            )
            # find unit name and tags in field value;
            # use unit name (a number) as a separate tag
            # due to mixing with other numbers in value -
            # sorted by splitting field value by space
            if unit_name in content_value.split(" "):
                results.append(result)
            for tag in unit_tags:
                if source == 'maritime':
                    if contains_variant(content.lower(), tag):
                        results.append(result)
                if source == 'roads':
                    if tag in content.lower():
                        results.append(result)

    # remove duplicate new results
    results = list(set(results))

    # check for new results
    new_results = []
    for item in results:
        if item not in existing_results:
            new_results.append(item)

    # load contact data
    with open("contacts.json", "rb") as f:
        contacts = json.load(f)

    # send email notifications
    for result in new_results:
        # construct an email message
        unit_name = result
        unit_label = next(
            (
                item.get("label") for item in units \
                    if item.get("name") == unit_name
            ),
            ''
        )
        subject = f'{COMPANY_NAME} | {unit_label}'
        if source == 'maritime':
            body = f'<!DOCTYPE html><html><body>'\
                f'<p>HAK - Pomorski promet {date_raw}</p><br>'\
                '<a href="https://m.hak.hr/stanje.asp?id=3">'\
                'https://m.hak.hr/stanje.asp?id=3</a>'\
                f'{EMAIL_FOOTER}'\
                '</body></html>'.strip()
        else:
            body = f'<!DOCTYPE html><html><body>'\
                f'<p>HAK - Prohodnost {date_raw}</p><br>'\
                '<a href="https://m.hak.hr/stanje.asp?id=1">'\
                'https://m.hak.hr/stanje.asp?id=1</a>'\
                f'{EMAIL_FOOTER}'\
                '</body></html>'.strip()

        # retrieve islands connected to this unit
        islands = next(
            (
                unit.get("islands") for unit in units \
                    if unit.get("name") == unit_name
            ),
            []
        )
        emails_all = []
        # collect contacts' emails connected to this island
        for island in islands:
            emails = next(
                (
                    item.get("contacts") for item in contacts \
                        if item.get("island") == island
                ),
                []
            )
            emails_all.extend(emails)

        # remove duplicate emails
        emails_all = list(set(emails_all))
        
        # log what is to be sent
        emails_str = ",".join(emails_all) if emails_all \
            else "<no recipients>"
        islands_str = ",".join(islands)
        logger.info(
            f"[NEW RESULT] {result}|{islands_str}|{emails_str}"
        )

        # send emails
        send_email(emails_all, subject, body)

    # write results
    with open(RESULTS_PATH.resolve(), "w+", encoding="utf-8") as f:
        for result in results:
            f.write(f"{result}\n")

    # write to download file
    f = DOWNLOAD_PATH.open("wb+")
    f.write(response)
    f.close()

    # also copy for archiving & debugging purposes
    shutil.copy(
        str(DOWNLOAD_PATH.resolve()),
        str(ARCHIVE_PATH.resolve())
    )


# main
# ----

def main():
    process(source='maritime')
    sleep(DOWNLOAD_DELAY)
    process(source='roads')


if __name__ == "__main__":
    main()