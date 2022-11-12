import json
import logging
import random
import shutil
import string
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from utils import (
    get_settlement_names_and_tags,
    send_email,
)


# set constants
# -------------

COMPANY_NAME = "HEP"
SCRIPT_NAME = "hep"
JOB_ID = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
NOW = datetime.now().strftime("%Y%m%d_%H%M%S")
SOURCE_URL = 'https://www.hep.hr/ods/bez-struje/19' \
    '?dp={company}&el={unit}&datum={date}'
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
    # load infrastructure data
    with open(INFRASTRUCTURE_PATH.resolve(), "rb") as f:
        infrastructure = json.load(f)
        companies = infrastructure.get("companies")

    # generate dates (today + 3 days in advance)
    dates_generated = list()
    for i in range(0, 4):
        date_generated = (
            date.today() + timedelta(days=i)
        ).strftime("%d.%m.%Y")
        dates_generated.append(date_generated)
    
    # generate URLs
    urls = list()
    for company in companies:
        for unit in company.get('units'):
            for date_generated in dates_generated:
                urls.append(
                    SOURCE_URL.format(
                        company=company.get('tag'),
                        unit=unit.get('tag'),
                        date=date_generated
                    )
                )

    # prepare headers
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:52.0)' \
                      'Gecko/20100101 Firefox/52.0'
    }

    # start making requests
    responses = make_requests(headers, urls)

    # scrape responses & collect entries
    entries = []
    for url, response in responses:
        if 'Nema planiranih' in response:
            continue

        soup = BeautifulSoup(response, 'html.parser')
        content = soup.find('div', {'class': 'radwrap'}).text

        # no discernible information available on source site
        published_at = ''
        subtitle = ''
        external_id = url

        parsed_url = urlparse(url)
        parsed_date = parse_qs(parsed_url.query)['datum'][0]
        title = f'Bez struje - {parsed_date}'
        company_tag = parse_qs(parsed_url.query)['dp'][0]
        unit_tag = parse_qs(parsed_url.query)['el'][0]
        
        link = url
        body = content

        entry = {
            "external_id": external_id,
            "published_at": published_at,
            "company_tag": company_tag,
            "unit_tag": unit_tag,
            "link": link,
            "title": title,
            "subtitle": subtitle,
            "body": body
        }
        entries.append(entry)

    # create a results file it doesn't exist
    if not RESULTS_PATH.exists():
        f = RESULTS_PATH.open("w+")
        f.close()
    
    # open the existing results file
    with open(str(RESULTS_PATH.resolve())) as f:
        results = f.read()

    # load island data
    with open("islands.json", "rb") as f:
        islands_all = json.load(f)

    # process entries
    new_results = []
    for entry in entries:
        # isolate and format settlement names in the entry body
        body_raw = entry.get("body")
        body = [
            item.strip().split("Ulica:")[0].strip().lower() \
                for item in body_raw.replace('\n', ' ').split("Mjesto: ") \
                    if item.strip()
        ]
        
        # get islands connected to the company unit
        entry_company_tag = entry.get("company_tag")
        entry_unit_tag = entry.get("unit_tag")
        company = next(
            (
                item for item in companies if item['tag'] == entry_company_tag
            ), None
        )
        unit = next(
            (
                item for item in company.get('units') \
                    if item['tag'] == entry_unit_tag
            ), None
        )
        islands = unit.get('islands')

        # check if islands' settlements' tags in entry content
        for island in islands:
            # retrieve island's settlements
            settlements = get_settlement_names_and_tags(islands_all, island)
            for settlement in settlements:
                # form a result
                entry_external_id = entry.get("external_id")
                entry_title = entry.get("title")
                locality = settlement.get('name')
                result = f"{entry_external_id}|{entry_title}|{island}|{locality}"
                # check tags
                tags = settlement.get('tags').split(',')
                for tag in tags:
                    if tag in body:
                        # check if result already exists
                        if result not in results:
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
        external_id, title, island_name, _ = result.split("|")
        island_label = next(
            (
                item.get("label") for item in islands_all \
                    if item.get("name") == island_name
            ),
            ''
        )
        subject = f'[{COMPANY_NAME}] {island_label}'
        link = external_id
        body = f'<!DOCTYPE html><html><body><p>{title}</p><br>'\
            f'<a href="{link}">{link}</a></body></html>'.strip()

        # collect contacts' emails connected to this island
        emails = next(
            (
                item.get("contacts") for item in contacts \
                    if item.get("island") == island_name
            ),
            []
        )
        
        # log what is to be sent
        emails_str = ",".join(emails) if emails \
            else "<no recipients>"
        logger.info(
            f"[NEW RESULT] {result}|{emails_str}"
        )

        # send emails
        send_email(emails, subject, body)

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