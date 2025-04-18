"""
Based on https://github.com/leaky-forms/leaky-forms/tree/main/leak-detector
"""

import maya
from collections import defaultdict
import json

filled_urls = defaultdict(str)
last_urls = defaultdict(str)
start_fill_time = defaultdict(int)
last_page_urls_temp = defaultdict(str)
cmp_type = defaultdict(str)
link_urls = defaultdict(str)
xpath_els = defaultdict(str)
ids_els = defaultdict(str)
filled = defaultdict(bool)
sites = set()

BATCH_PROCESS = True
START_INDEX = 0
END_INDEX = 10000


def get_successful_urls(success_file):
    """
    Get the list of successfully visited urls from the log file.
    """
    print(f"Will process {success_file}")

    urls = set()

    if not BATCH_PROCESS:
        for w in open(success_file, "r", encoding="utf-8").read().splitlines():
            urls.add(w.lower())
    else:
        print(f"Will process batch from index {START_INDEX} to {END_INDEX}")
        curr_index = 0
        for w in open(success_file, "r", encoding="utf-8").read().splitlines():
            if curr_index >= START_INDEX and curr_index < END_INDEX:
                urls.add(w.lower())
            curr_index += 1
    return list(urls)

def get_date_object(date_string):
    # GA: would prefer a built-in parser to reduce dependencies,
    # since we know the format
    return maya.parse(date_string).datetime()


def get_domain_from_line(log_line):
    try:
        return log_line.split()[1].split(":")[0]
    except Exception:
        return None


def get_urls_and_times_for_email_password_fields(log_file):
    print("Will process %s" % log_file)
    for line in open(log_file, encoding='utf-8'):
        if "CMP detected" in line:
            site_domain = get_domain_from_line(line)
            try:
                cmp_type[site_domain] = json.loads(line.split()[6])["cmpName"]
            except Exception:
                print("Cannot parse the CMP line", line)
        if "Will search for login fields on" in line:
            site_domain = get_domain_from_line(line)
            last_page_urls_temp[site_domain] = line.split()[-1]
        elif "Will fill in " in line:
            site_domain = get_domain_from_line(line)
            last_page_urls_temp[site_domain] = line.split()[-1]
        elif "Will fill " in line and "in email " not in line:
            site_domain = get_domain_from_line(line)
            # TODO: I think the time of "passwd fill start" overwrites
            # the "email fill start"
            if site_domain not in start_fill_time:
                start_fill_time[site_domain] = get_date_object(line.split()[0][5:]).timestamp()
        elif "Succesfully filled the email field" in line or "Successfully filled the email field" in line:
            site_domain = get_domain_from_line(line)
            filled_urls[site_domain] = start_fill_time[site_domain]
            last_urls[site_domain] = last_page_urls_temp[site_domain]
            attr_str = line.split("Successfully filled the email field")[-1]
            field_attrs_json = json.loads(attr_str)
            id_el = field_attrs_json['id']
            xpath_search_key = '$x("' + field_attrs_json["xpath"] + '")'
            xpath_els[site_domain] = xpath_search_key
            ids_els[site_domain] = id_el
            filled[site_domain] = True
        # elif "Succesfully filled the password field" in line or "Successfully filled the password field" in line:
        #     site_domain = get_domain_from_line(line)
        #     filled_urls[site_domain] = start_fill_time[site_domain]
        #     last_urls[site_domain] = last_page_urls_temp[site_domain]
        #     attr_str = line.split("Successfully filled the email field")[-1]
        #     field_attrs_json = json.loads(attr_str)
        #     id_el = field_attrs_json['id']
        #     xpath_search_key = '$x("' + field_attrs_json["xpath"] + '")'
        #     xpath_els[site_domain] = xpath_search_key
        #     ids_els[site_domain] = id_el
        #     filled[site_domain] = True
    return filled_urls, last_urls, set(filled_urls.keys()), set(cmp_type.keys()), xpath_els, ids_els