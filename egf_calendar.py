import shutil
import json
import re
import hashlib
import requests
import bs4

from datetime import datetime, timezone
from email import utils
from xml.sax.saxutils import escape
from os import path

DATA_DIR="/var/www/html"
# DATA_DIR="data"
CAL_NAME='egf-calendar'
HTML_PATH = f"{DATA_DIR}/{CAL_NAME}.html"
JSON_PATH = f"{DATA_DIR}/{CAL_NAME}.json"
ICAL_PATH = f"{DATA_DIR}/{CAL_NAME}.ics"
RSS_PATH = f"{DATA_DIR}/{CAL_NAME}.rss"


def fetch():
    r = requests.get('https://www.eurogofed.org/calendar/')
    with open(HTML_PATH, 'wb') as fd:
        for chunk in r.iter_content(chunk_size=4096):
            fd.write(chunk)


def guid(row):
    return f"{row['From'].year}::{row['City']}, {row['Co']}::{row['Event']}"


DESCRIPTION_TEMPLATE = (
    '<h3><a href="{url}">{title}</a></h3>'
    '<dl style="width: 100%;">'
    '<dt style="width: 30%; float: left;">Location:</dt>'
    '<dd style="width: 70%; float: left;">{city}, {country}<dd>'
    '<dt style="width: 30%; float: left;">Dates:</dt>'
    '<dd style="width: 70%; float: left;">{start_date} - {end_date}<dd>'
    '<dt style="width: 30%; float: left;">Contact:</dt>'
    '<dd style="width: 70%; float: left;">{contact}</dd></dl>'
)

def extract(cal_path, pubdate_cache):
    with open(cal_path, 'r') as file:
        soup = bs4.BeautifulSoup(file, 'html.parser')
    
    et_h2 = soup.find('h2', string='European Tournaments')
    et_div = et_h2.find_next('div')
    et_table = et_div.find('table', recursive=False)

    tbody = et_table('tbody')[0]
    rows = tbody('tr')
    headers = [h.string for h in rows[0]('th')]
    
    update_re = re.compile(r'Last updated: (\d\d\d\d-\d\d-\d\d \d\d:\d\d)')
    update_s = soup.find(string=update_re).string
    last_update_dt = datetime.strptime(update_re.match(update_s).group(1), "%Y-%m-%d %H:%M")

    dtstamp = datetime.now()
    
    extracted = []
    for row in rows[1:]:
        e = dict(zip(headers, row('td')))
        url = e['Event'].find('a')
        e['url'] = url.attrs['href'] if url is not None else '#'
        e['Event'] = " ".join(list(e['Event'].strings))
        e['From'] = datetime.strptime(e['From'].string + ' 08:00', '%d.%m.%Y %H:%M')
        e['To'] = datetime.strptime(e['To'].string + ' 16:00', '%d.%m.%Y %H:%M')
        e['City'] = e['City'].string
        e['Co'] = e['Co'].string
        e['Contact Address'] = " ".join([str(c) for c in e['Contact Address'].contents])
        e['last_update'] = last_update_dt
        e['dtstamp'] = dtstamp
        e['sha1'] = hashlib.sha1(bytes(str(row), 'utf8'), usedforsecurity=False).hexdigest()
        e['description_html'] = DESCRIPTION_TEMPLATE.format(
            title=escape(e['Event']),
            city=escape(e['City']),
            country=escape(e['Co']),
            start_date=e['From'].strftime('%d.%m.%Y'),
            end_date=e['To'].strftime('%d.%m.%Y'),
            contact=e['Contact Address'],
            url=e['url']
        )
        e['guid'] = guid(e)
        e['create_date'] = pubdate_cache.get(e['guid'], last_update_dt)
        pubdate_cache[e['guid']] = e['create_date']
        e['update_date'] = pubdate_cache.get(e['sha1'], last_update_dt)
        pubdate_cache[e['sha1']] = e['update_date']
        extracted.append(e)

    return extracted


def row2event(r, out):
    e = {}
    e['SUMMARY'] = r['Event']
    e['DTSTAMP'] = r['dtstamp'].strftime('%Y%m%dT%H%M%SZ')
    e['DTSTART'] = r['From'].strftime('%Y%m%dT%H%M%SZ')
    e['DTEND'] = r['To'].strftime('%Y%m%dT%H%M%SZ')
    e['CREATED'] = r['create_date'].strftime('%Y%m%dT%H%M%SZ')
    e['LAST-MODIFIED'] = r['update_date'].strftime('%Y%m%dT%H%M%SZ')
    e['LOCATION'] = f"{r['City'].string}, {r['Co'].string}"
    if 'url' in r:
        e['URL'] = r['url']
    e['UUID'] = r['guid']
    e['DESCRIPTION'] = r['description_html']
    
    out.write("BEGIN:VEVENT\r\n")
    for k, v in e.items():
        out.write(k)
        out.write(':')
        out.write(v)
        out.write('\r\n')
    out.write("END:VEVENT\r\n")


ITEM_TEMPLATE = """<item>
<title>{title}</title>
<link>{link}</link>
<guid isPermaLink="false">{guid}</guid>
<pubDate>{pubdate}</pubDate>
<description>
<![CDATA[
{description}
]]>
</description>
</item>
"""


def row2feeditem(row, out):
    contact = f"<a href=\"{row['url']}\">Website</a>. " if 'url' in row else ""
    contact += row['Contact Address']
    tpl_data = {
        "title": escape(row['Event']),
        "link": escape(row.get('url', 'https://www.eurogofed.org/calendar/')),
        "guid": escape(row['guid']+'_'+row['sha1']),
        "pubdate": escape(utils.format_datetime(row['last_update'])),
        "description": row['description_html']
    }
    
    out.write(ITEM_TEMPLATE.format(**tpl_data))


def write_ical(events, writer):
    writer.write('BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:egf2ical\r\nCALSCALE:GREGORIAN\r\nMETHOD:PUBLISH\r\n')
    writer.write('X-WR-CALNAME:EGF Tournaments\r\nX-WR-TIMEZONE:Europe/Belgrade\r\n')
    for e in events:
        row2event(e, writer)
    writer.write('END:VCALENDAR')

def write_rss(events, f):
    f.write('<?xml version="1.0" encoding="UTF-8" ?>\n')
    f.write('<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">')
    f.write('<channel>')
    f.write('<title>EGF Tournament Calendar Change Feed</title>')
    f.write('<description>Get notified when calendar updates</description>')
    f.write('<link>http://li1418-60.members.linode.com/egf-calendar.rss</link>')
    f.write('<atom:link href="http://li1418-60.members.linode.com/egf-calendar.rss" rel="self" type="application/rss+xml" />')
    f.write('<ttl>600</ttl>\n')
    for e in events:
        row2feeditem(e, f)
    f.write('</channel></rss>')

def main():
    fetch()
    if path.exists(JSON_PATH):
        with open(JSON_PATH, 'r') as jf:
            j = json.load(jf)
            pubdate_cache = {k: datetime.fromisoformat(v) for k, v in j.items()}
    else:
        pubdate_cache = {}
    events = extract(HTML_PATH, pubdate_cache)
    with open(ICAL_PATH, 'w') as f:
        write_ical(events, f)
    with open(RSS_PATH, 'w') as f:
        write_rss(events, f)
    with open(JSON_PATH, 'w') as f:
        json.dump({k: v.isoformat() for k, v in pubdate_cache.items()}, f)

if __name__ == '__main__':
    main()
