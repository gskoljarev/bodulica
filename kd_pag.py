import json
import logging
import random
import re
import shutil
import string
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from utils import (
    get_settlement_names_and_tags,
    send_email,
)


# set constants
# -------------

COMPANY_NAME = "Komunalno društvo Pag"
SCRIPT_NAME = "kd_pag"
JOB_ID = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
NOW = datetime.now().strftime("%Y%m%d_%H%M%S")
BASE_URL = 'https://kd-pag.hr'
SOURCE_URL = f'{BASE_URL}/o-nama/prekidi-u-isporuci-usluga.html'
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
stdout_handler.stream = open(1, 'w', encoding="utf-8", buffering=1)

log_file_handler = logging.FileHandler(str(LOG_PATH.resolve()), encoding="utf-8")
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
            return


def process():
    # prepare headers
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:52.0)' \
                      'Gecko/20100101 Firefox/53.0'
    }
  
    # make initial request
    urls = [SOURCE_URL]
    responses = make_requests(headers, urls)

    # scrape sub page links
    for url, response in responses:
        soup = BeautifulSoup(response, 'html.parser')
        main = soup.find('main', {'id': 'g-mainbar'})

        # find and format raw links
        links = [
            BASE_URL+item.get("href") for item in \
                main.find_all(
                    "a",
                    href=re.compile(r"o-nama/prekidi-u-isporuci-usluga/"),
                    recursive=True
                )
        ]

    # make subpage requests
    responses = make_requests(headers, links)

    # scrape responses & collect entries
    entries = []
    for url, response in responses:
        soup = BeautifulSoup(response, 'html.parser')

        title = soup.find('h2').text.strip()
        body = soup.find('div', {'itemprop': 'articleBody'}).text
        external_id = url.rpartition('/')[2]
        link = url

        # available but unused
        published_at = ''
        # no discernible information available on source page
        subtitle = ''

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

    # load island data
    with open("islands.json", "rb") as f:
        islands_all = json.load(f)

    # create a results file it doesn't exist
    if not RESULTS_PATH.exists():
        f = RESULTS_PATH.open("w+")
        f.close()
    
    # open the existing results file
    with open(str(RESULTS_PATH.resolve())) as f:
        results = f.read()

    # process entries
    new_results = []
    for entry in entries:
        title_raw = entry.get('title').strip().replace(
            ',', ' '
        ).replace('-', ' ')
        title = [
            item.strip().lower() for item in title_raw.split(' ') if item.strip()
        ]

        body_raw = entry.get("body").strip().replace(
            '\n', ' '
        ).replace(
            '\xa0', ' '
        ).replace(
            ',', ' '
        ).replace('-', ' ')
        body = [
            item.strip().lower() for item in body_raw.split(' ') if item.strip()
        ]
        
        # get islands connected to the singular company unit
        unit = units[0]
        islands = unit.get('islands')

        # check if islands' settlements' tags in entry content
        for island in islands:
            # retrieve island's settlements
            settlements = get_settlement_names_and_tags(islands_all, island)
            for settlement in settlements:
                # form a result
                locality = settlement.get('name')
                external_id = entry.get('external_id').strip()
                title_result = entry.get('title').strip()
                result = f"{external_id}|{title_result}|{island}|{locality}"
                # check tags
                tags = settlement.get('tags').split(',')
                for tag in tags:
                    if tag in body or tag in title:
                        # check if result already exists
                        if result not in results:
                            new_results.append(result)

    if not new_results:
        return

    # remove duplicate new results
    new_results = list(set(new_results))

    # load island data
    with open("islands.json", "rb") as f:
        islands = json.load(f)

    # load contact data
    with open("contacts.json", "rb") as f:
        contacts = json.load(f)

    # construct email notifications
    emails = []
    for result in new_results:
        # construct an email message
        external_id, title, island_name, _ = result.split("|")
        subject = f'{COMPANY_NAME} | {title}'
        link = 'https://www.komunalac.com/obavijesti'
        body = f'<!DOCTYPE html><html><body><p>{title}</p><br>'\
            f'<a href="{link}">{link}</a></body></html>'.strip()

        # collect contacts' emails connected to this island
        email_addresses = next(
            (
                item.get("contacts") for item in contacts \
                    if item.get("island") == island_name
            ),
            []
        )
        
        # log what is to be sent
        emails_str = ",".join(email_addresses) if email_addresses \
            else "<no recipients>"
        logger.info(
            f"[NEW RESULT] {result}|{emails_str}"
        )

        emails.append((email_addresses, subject, body))
    
    # remove duplicate emails
    emails = list(set((tuple(emails), subject, body) for emails, subject, body in emails))

    # send email notifications
    for email in emails:
        email_addresses = email[0]
        subject = email[1]
        body = email[2]
        send_email(email_addresses, subject, body)

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