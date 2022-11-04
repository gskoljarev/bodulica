import json
import logging
import random
import shutil
import string
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from utils import send_email


# set constants
# -------------

COMPANY_NAME = "Hrvatska pošta"
SCRIPT_NAME = "hrvatska_posta"
JOB_ID = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
NOW = datetime.now().strftime("%Y%m%d_%H%M%S")
BASE_URL = 'https://www.posta.hr'
SOURCE_URL = f'{BASE_URL}/aktualne-informacije/43'
DOWNLOAD_DELAY_SECONDS = 1
INFRASTRUCTURE_PATH = Path(f"{SCRIPT_NAME}/infrastructure.json")
RESULTS_PATH = Path(f"{SCRIPT_NAME}/results.log")
DOWNLOAD_PATH = Path(f"{SCRIPT_NAME}/data/data.json")
ARCHIVE_PATH = Path(f"{SCRIPT_NAME}/data/data_{NOW}_{JOB_ID}.json")
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

def make_requests(headers, urls):
    for url in urls:
        time.sleep(DOWNLOAD_DELAY_SECONDS)
        try:
            request = Request(url)
            for key, value in headers.items(): 
                request.add_header(key, value)
            response = urlopen(request).read().decode('utf-8')
            yield url, response
        except:
            logger.error(f"Error downloading data")
            exit()

def process():
    # prepare headers
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:52.0)' \
                      'Gecko/20100101 Firefox/52.0'
    }
  
    # make initial request
    urls = [SOURCE_URL]
    responses = make_requests(headers, urls)

    # scrape sub page links
    for url, response in responses:
        soup = BeautifulSoup(response, 'html.parser')
        div = soup.find('div', {'class': 'news-wrapper'})
        # find and format raw links
        links = [
            BASE_URL+item.get("href") for item in \
                div.findChildren("a" , recursive=False)
        ]

    # make subpage requests
    responses = make_requests(headers, links)

    # scrape responses & collect entries
    entries = []
    for url, response in responses:
        soup = BeautifulSoup(response, 'html.parser')
        title = soup.find('h1').text
        body = soup.find('div', {'class': 'page-content'}).text

        # no discernible information available on source page
        subtitle = ''
        published_at = ''
        subtitle = ''

        external_id = url.rpartition('/')[2]
        link = url

        entry = {
            "external_id": external_id,
            "published_at": published_at,
            "link": link,
            "title": title,
            "subtitle": subtitle,
            "body": body
        }
        entries.append(entry)

    # load infrastructure data
    with open(INFRASTRUCTURE_PATH.resolve(), "rb") as f:
        infrastructure = json.load(f)
        units = infrastructure.get("units")

    # create a results file it doesn't exist
    if not RESULTS_PATH.exists():
        f = RESULTS_PATH.open("w+")
        f.close()
    
    # open the existing results file
    with open(str(RESULTS_PATH.resolve())) as f:
        results = f.read()

    # process entries
    new_results = []
    message_links = []  # to be used when forming email messages
    for entry in entries:
        # compare entry data with results data
        external_id = entry.get("external_id")
        title = entry.get("title")
        body = entry.get("body")
        url = entry.get("url")
        processing_fields = [title, body]
        for unit in units:
            unit_name = unit.get("name")
            unit_tags = unit.get("tags")
            result = f"{external_id}|{title}|{unit_name}"
            # check first if there is already a result for this unit
            if result not in results and result not in new_results:
                unit_tags = unit.get("tags").split(",")
                for field in processing_fields:  # process each field
                    # check tags
                    for tag in unit_tags:
                        if tag in field.lower():
                            new_results.append(result)
                            message_links.append(
                                {
                                    "external_id": external_id,
                                    "url": url
                                }
                            )
    print(len(new_results))

    if not new_results:
        return

    # remove duplicate new results
    new_results = list(set(new_results))

    # log new results
    for result in new_results:
        logger.info((f"[NEW RESULT] {result}"))

    # load island data
    with open("islands.json", "rb") as f:
        islands = json.load(f)

    # load contact data
    with open("contacts.json", "rb") as f:
        contacts = json.load(f)

    # send email notifications
    for result in new_results:
        # construct an email message
        external_id, title, unit_name = result.split("|")
        subject = f'[{COMPANY_NAME}] {title}'
        link = next(
            (
                item.get("url") for item in message_links \
                    if item.get("external_id") == external_id
            ),
            None
        )
        body = f'<!DOCTYPE html><html><body><p>{title}</p>'\
            f'<a href="{link}">'\
            f'{link}</a></body></html>'.strip()

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
            f"[SEND EMAIL] {result}|{islands_str}|"\
            f"{emails_str}|{body}"
        )

        # send emails
        if emails_all:
            send_email(emails_all, subject, body)

    # write new results
    with open(RESULTS_PATH.resolve(), "a+", encoding="utf-8") as f:
        for result in new_results:
            f.write(f"{result}\n")

    # write to download file
    with open(DOWNLOAD_PATH.resolve(), "w+") as f:
        json.dump(entries, f)

    # also copy for archiving & debugging purposes
    shutil.copy(
        str(DOWNLOAD_PATH.resolve()),
        str(ARCHIVE_PATH.resolve())
    )

    return


# main
# ----

def main():
    process()


if __name__ == "__main__":
    main()