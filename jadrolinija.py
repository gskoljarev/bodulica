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
from urllib.request import urlopen
from xml.etree import ElementTree as ET

from utils import send_email


# set constants
# -------------

SCRIPT_NAME = "jadrolinija"
JOB_ID = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
NOW = datetime.now().strftime("%Y%m%d_%H%M%S")
SOURCE_URL = "https://www.jadrolinija.hr/Feeds/vijesti"
INFRASTRUCTURE_PATH = Path(f"{SCRIPT_NAME}/infrastructure.json")
RESULTS_PATH = Path(f"{SCRIPT_NAME}/results.log")
DOWNLOAD_PATH = Path(f"{SCRIPT_NAME}/data/feed.xml")
ARCHIVE_PATH = Path(f"{SCRIPT_NAME}/data/feed_{NOW}_{JOB_ID}.xml")
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
    # download the RSS feed
    try:
        with urlopen(url) as r:
            response = r.read()
    except:
        logger.error(f"Error downloading data")
        exit()

    # create a download file it doesn't exist
    if not DOWNLOAD_PATH.exists():
        f = DOWNLOAD_PATH.open("wb+")
        f.write(response)
        f.close()

    # check if new data available
    f = DOWNLOAD_PATH.open("rb")
    existing_data = f.read()
    f.close()
    if existing_data == response:
        exit()
    
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

    # process XML response & entries
    tree = ET.ElementTree(ET.fromstring(response))
    root = tree.getroot()
    entries = root.findall('.//channel/item')
    
    if not entries:
        return

    new_results = []
    for entry in entries:
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

    if not new_results:
        return

    # remove duplicate new results
    new_results = list(set(new_results))
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
        subject = f'[Jadrolinija] {title}'
        body = f'<!DOCTYPE html><html><body><h4>{title}</h4>'\
            '<a href="https://www.jadrolinija.hr">'\
            'https://www.jadrolinija.hr</a></body></html>'.strip()

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
            else "<no recepients>"
        islands_str = ",".join(islands)
        logger.info(
            f"[SEND EMAIL] {result}|{islands_str}|"\
            f"{emails_str}|{body}"
        )

        # send emails
        if emails_all:
            send_email(emails_all, subject, body)

    # write new results
    rf = RESULTS_PATH.open("a+")
    for result in new_results:
        rf.write(f"{result}\n")
    rf.close()

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