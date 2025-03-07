import html
import json
import logging
import random
import shutil
import ssl
import string
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup

from utils import send_email


# set constants
# -------------

COMPANY_NAME = "Jadrolinija"
SCRIPT_NAME = "jadrolinija"
JOB_ID = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
NOW = datetime.now().strftime("%Y%m%d_%H%M%S")
SOURCE_URL_FEED = "https://www.jadrolinija.hr/feeds/vijesti"
SOURCE_URL_SITE = "https://www.jadrolinija.hr/hr/obavijesti-za-putnike"
DOWNLOAD_DELAY_SECONDS = 2
INFRASTRUCTURE_PATH = Path(f"{SCRIPT_NAME}/infrastructure.json")
RESULTS_PATH = Path(f"{SCRIPT_NAME}/results.log")
DOWNLOAD_FEED_PATH = Path(f"{SCRIPT_NAME}/data/feed.xml")
ARCHIVE_FEED_PATH = Path(f"{SCRIPT_NAME}/data/feed_{NOW}_{JOB_ID}.xml")
DOWNLOAD_SITE_PATH = Path(f"{SCRIPT_NAME}/data/data.json")
ARCHIVE_SITE_PATH = Path(f"{SCRIPT_NAME}/data/data_{NOW}_{JOB_ID}.json")
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
            context = ssl._create_unverified_context()
            request = Request(url)
            for key, value in headers.items(): 
                request.add_header(key, value)
            response = urlopen(request, context=context).read().decode('utf-8')
            yield url, response
        except:
            logger.error(f"Error downloading data")
            exit()


def process():
    # process the RSS feed
    # --------------------

    # download the data
    try:
        context = ssl._create_unverified_context()
        with urlopen(SOURCE_URL_FEED, context=context) as r:
            response_feed = r.read()
    except:
        logger.error(f"Error downloading data")
        exit()

    # create a download file it doesn't exist
    if not DOWNLOAD_FEED_PATH.exists():
        f = DOWNLOAD_FEED_PATH.open("wb+")
        f.close()

    # # check if new downloaded data available
    # f = DOWNLOAD_FEED_PATH.open("rb")
    # existing_data = f.read()
    # f.close()
    # if existing_data == response:
    #     exit()
    
    # load infrastructure data
    with open(INFRASTRUCTURE_PATH.resolve(), "rb") as f:
        infrastructure = json.load(f)
        units = infrastructure.get("units")

    # create a results file if it doesn't exist
    if not RESULTS_PATH.exists():
        f = RESULTS_PATH.open("w+")
        f.close()

    # open the existing results file
    with open(str(RESULTS_PATH.resolve())) as f:
        results = f.read()

    # process XML response & entries
    tree = ET.ElementTree(ET.fromstring(response_feed))
    root = tree.getroot()
    entries_feed = root.findall('.//channel/item')

    if not entries_feed:
        entries_feed = []

    # process the site
    # ----------------

    # prepare headers
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) ' \
                      'AppleWebKit/605.1.15 (KHTML, like Gecko) ' \
                      'Version/17.4.1 Safari/605.1.15'
    }
  
    # make initial request
    urls = [SOURCE_URL_SITE]
    responses = make_requests(headers, urls)

    # scrape sub page links
    for url, response in responses:
        soup = BeautifulSoup(response, 'html.parser')
        ul = soup.find('ul', {'class': 'press__list'})
        # find links
        links = [
            item.get("href") for item in \
                ul.findChildren("a" , recursive=True)
        ]

    # make subpage requests
    responses = make_requests(headers, links)

    # scrape responses & collect entries
    entries_site = []
    for url, response in responses:
        soup = BeautifulSoup(response, 'html.parser')
        external_id = url.rpartition('/')[2]
        title = soup.find('h1').text
        subtitle = soup.find('h2').text
        body = soup.find('div', {'class': 'wysiwyg'}).text.strip()

        # unused; no discernible information available in the subpage,
        # but can be parsed from root source URL
        # published_at = '' 

        # link = url  # unused

        entry = {
            "external_id": external_id,
            # "published_at": published_at,
            # "link": link,
            "title": title,
            "subtitle": subtitle,
            "body": body
        }
        entries_site.append(entry)

    # continue with further processing
    # --------------------------------

    new_results = []
    
    # check for new results in the RSS feed data
    for entry in entries_feed:
        # parse XML entry data
        external_id = entry.findtext("guid", default="")
        title = html.unescape(entry.findtext("title", default=""))
        subtitle = html.unescape(entry.findtext("description", default=""))
        body = html.unescape(
            entry.findtext("{http://www.w3.org/2005/Atom}content", default="")
        )
        # # not used / unreliable in the feed
        # published_at = entry.findtext("pubDate", default="")
        
        # compare XML entry data with results data
        processing_fields = [
            title, subtitle, body
        ] 
        for unit in units:
            unit_name = unit.get("name")
            result = f"{external_id}|{title}|{unit_name}"
            # check first if there is already a result for this unit
            if result not in results and result not in new_results:
                unit_tags = unit.get("tags").split(",")
                for field in processing_fields:  # process each field
                    # &nbsp; turns into \xa0 when splitting and
                    # slavic alphabet characters are not parsed correctly,
                    # so we normalize first
                    field_value = unicodedata.normalize(
                        "NFKC", field.lower()
                    )
                    # find unit name and tags in field value;
                    # use unit name (a number) as a separate tag
                    # due to mixing with other numbers in value -
                    # sorted by splitting field value by space
                    if unit_name in field_value.split(" "):
                        new_results.append(result)
                    for tag in unit_tags:
                        if tag in field.lower():
                            new_results.append(result)

    # check for new results in the site data
    for entry in entries_site:
        # compare entry data with results data
        external_id = entry.get("external_id")
        title = entry.get("title")
        body = entry.get("body")
        
        # compare the site entry data with results data
        processing_fields = [
            title, subtitle, body
        ] 
        for unit in units:
            unit_name = unit.get("name")
            result = f"{external_id}|{title}|{unit_name}"
            # check first if there is already a result for this unit
            if result not in results and result not in new_results:
                unit_tags = unit.get("tags").split(",")
                for field in processing_fields:  # process each field
                    # &nbsp; turns into \xa0 when splitting and
                    # slavic alphabet characters are not parsed correctly,
                    # so we normalize first
                    field_value = unicodedata.normalize(
                        "NFKC", field.lower()
                    )
                    # find unit name and tags in field value;
                    # use unit name (a number) as a separate tag
                    # due to mixing with other numbers in value -
                    # sorted by splitting field value by space
                    if unit_name in field_value.split(" "):
                        new_results.append(result)
                    for tag in unit_tags:
                        if tag in field.lower():
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
        external_id, title, unit_name = result.split("|")
        unit_label = next(
            (
                item.get("label") for item in units \
                    if item.get("name") == unit_name
            ),
            ''
        )
        subject = f'[{COMPANY_NAME}] {unit_label}'
        if 'urn:uuid' in external_id:
            body = f'<!DOCTYPE html><html><body><p>{title}</p><br>'\
                '<a href="https://www.jadrolinija.hr/hr/obavijesti/stanje-u-prometu/">'\
                'https://www.jadrolinija.hr/hr/obavijesti/stanje-u-prometu/</a></body></html>'.strip()
        else:
            body = f'<!DOCTYPE html><html><body><p>{title}</p><br>'\
                '<a href="https://www.jadrolinija.hr/hr/obavijesti-za-putnike">'\
                'https://www.jadrolinija.hr/hr/obavijesti-za-putnike</a></body></html>'.strip()

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

    # write to download files
    f = DOWNLOAD_FEED_PATH.open("wb+")
    f.write(response_feed)
    f.close()

    with open(DOWNLOAD_SITE_PATH.resolve(), "w+") as f:
        json.dump(entries_site, f)

    # also copy for archiving & debugging purposes
    shutil.copy(
        str(DOWNLOAD_FEED_PATH.resolve()),
        str(ARCHIVE_FEED_PATH.resolve())
    )

    shutil.copy(
        str(DOWNLOAD_SITE_PATH.resolve()),
        str(ARCHIVE_SITE_PATH.resolve())
    )

    return


# main
# ----

def main():
    process()


if __name__ == "__main__":
    main()