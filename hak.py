import html
import json
import logging
import random
import shutil
import string
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from utils import send_email


# set constants
# -------------

COMPANY_NAME = "HAK"
SCRIPT_NAME = "hak"
JOB_ID = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
NOW = datetime.now().strftime("%Y%m%d_%H%M%S")
SOURCE_URL = "https://m.hak.hr/stanje.asp?id=3"
INFRASTRUCTURE_PATHS = [
    Path(f"{SCRIPT_NAME}/infrastructure.json"),
    Path(f"jadrolinija/infrastructure.json"),
]
RESULTS_PATH = Path(f"{SCRIPT_NAME}/results.log")
DOWNLOAD_PATH = Path(f"{SCRIPT_NAME}/data/page.html")
ARCHIVE_PATH = Path(f"{SCRIPT_NAME}/data/page_{NOW}_{JOB_ID}.html")
LOG_PATH = Path(f"{SCRIPT_NAME}/processing.log")


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

log_file_handler = logging.FileHandler(str(LOG_PATH.resolve()))
log_file_handler.setLevel(logging.DEBUG)
log_file_handler.setFormatter(formatter)

logger.addHandler(log_file_handler)
logger.addHandler(stdout_handler)


# processing
# ----------

def process(url):
    # prepare headers
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '\
                      'AppleWebKit/537.36 (KHTML, like Gecko) '\
                      'Chrome/107.0.0.0 Safari/537.36'
    }

    # download the page
    try:
        request = Request(url)
        for key, value in headers.items(): 
            request.add_header(key, value)
        response = urlopen(request).read()
    except:
        logger.error(f"Error downloading data")
        exit()

    # create a download file it doesn't exist
    if not DOWNLOAD_PATH.exists():
        f = DOWNLOAD_PATH.open("wb+")
        f.close()

    # check if new data available
    f = DOWNLOAD_PATH.open("rb")
    existing_data = f.read()
    f.close()
    if existing_data == response:
        exit()
    
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
    with open(str(RESULTS_PATH.resolve())) as f:
        results = f.read()

    # process response
    soup = BeautifulSoup(response, 'html.parser')
    date_time_raw = soup.find('div', {'id': 'sitno'}).text
    date_raw, time_raw = date_time_raw.replace(
        'Pomorski promet', ''
    ).split(' ')
    content = soup.find('ul', {'class': 'pageitem'}).text

    new_results = []

    for unit in units:
        unit_name = unit.get("name")
        result = f"{date_raw}|{unit_name}"
        # check first if there is already a result for this unit
        if result not in results and result not in new_results:
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
                new_results.append(result)
            for tag in unit_tags:
                if tag in content.lower():
                    new_results.append(result)

    if not new_results:
        return

    # remove duplicate new results
    new_results = list(set(new_results))

    # load contact data
    with open("contacts.json", "rb") as f:
        contacts = json.load(f)

    # send email notifications
    for result in new_results:
        # construct an email message
        date_raw, unit_name = result.split("|")
        unit_label = next(
            (
                item.get("label") for item in units \
                    if item.get("name") == unit_name
            ),
            ''
        )
        subject = f'[{COMPANY_NAME}] {unit_label}'
        body = f'<!DOCTYPE html><html><body><p>HAK - Pomorski promet {date_raw}</p><br>'\
            '<a href="https://www.hak.hr/info/stanje-na-cestama/#trajektni-promet">'\
            'https://www.hak.hr/info/stanje-na-cestama/#trajektni-promet</a></body></html>'.strip()

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

    # write new results
    with open(RESULTS_PATH.resolve(), "a+", encoding="utf-8") as f:
        for result in new_results:
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

    return


# main
# ----

def main():
    process(SOURCE_URL)


if __name__ == "__main__":
    main()