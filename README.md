# bodulica

Send email notifications about changes and disruptions of infrastructure on Croatian islands.

Visit https://skoljarev.com/bodulica and subscribe via email to start receiving email notifications.

## Documentation

- [Setup](#setup)
- [How to use](#usage)

## Setup

- requirements: `Python 3.10.x`
- install system packages: `apt install python3-venv`
- create a virtual environment `python3 -m venv .venv`
- activate the virtual environment: `source .venv/bin/activate`
- install Python requirements: `pip install -r requirements.txt`
- deactivate the virtual environment: `deactivate`
- setup a config file using `config.ini.example` as an example: `nano config.ini`
  - mailing uses Brevo service (formerly SendInBLue); to enable mailing set `MailEnabled`, `MailAPIURL` and `MailAPIToken`
- setup a contacts file using `contacts.json.example` as an example: `nano contacts.json`
- setup a cronjob at desired intervals, ie. every 12 hours:
```
nano /etc/crontab
5 */12   * * *   root    cd /opt/bodulica && .venv/bin/python jadrolinija.py
5 */12   * * *   root    cd /opt/bodulica && .venv/bin/python hep.py
5 */12   * * *   root    cd /opt/bodulica && .venv/bin/python hrvatska_posta.py
5 */12   * * *   root    cd /opt/bodulica && .venv/bin/python hak.py
5 */12   * * *   root    cd /opt/bodulica && .venv/bin/python vodovod_zadar.py
```

## Usage
- activate the virtual environment
`source .venv/bin/activate`

- run the script with today's date
`make`

- run the desired script
`python hak.py`