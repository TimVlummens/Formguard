"""
Based on https://github.com/leaky-forms/leaky-forms/tree/main/leak-detector
"""

import sys
from multiprocessing import Pool, cpu_count
from os.path import basename, join
from glob import glob
from time import time
import pandas as pd
import pickle
import csv
import json
from urllib.parse import urlparse
from login_leak_detector import detect_leaks_in_json

def get_successful_urls(success_file):
    """
    Get the list of successfully visited urls from the log file.
    """
    print(f"Will process {success_file}")

    urls = set()
    for w in open(success_file, "r", encoding="utf-8").read().splitlines():
        urls.add(w.lower())
    return list(urls)

def analyze_api_calls(json_data):
    """
    Summarize Api calls to which urls accessed which specific fields.
    """
    api_result = {"input_element_value": set(), "input_filled": {}}

    # Get filled values
    filled_values = []
    for filled_field in json_data["filled_values"]:
        filled_values.append(filled_field["value"])
        api_result["input_filled"][filled_field["value"]] = set()

    input_element_results = json_data["apis"]["input_element_results"]
    # Check the calls
    for call in input_element_results:
        # Add the chain of scripts in its entirety, incase the chain changes
        api_result["input_element_value"].add(tuple(call.get("scripts", [])))

        if call.get("details"):
            if call["details"].get("value") in filled_values:
                api_result["input_filled"][call["details"]["value"]].add(\
                    tuple(call.get("scripts", [])))

    return api_result

def analyze_websockets(json_data):
    """
    Summarize Websockets to which urls sent or received frames.
    """
    websockets_result = {"sent": set(), "received": set()}

    sent = json_data["websockets"]["sent"]
    for socket in sent:
        websockets_result["sent"].add(socket["url"])

    received = json_data["websockets"]["received"]
    for socket in received:
        websockets_result["received"].add(socket["url"])

    return websockets_result

def analyze_site(crawl_details):
    """
    Summarize API calls and websockets.
    """
    url, crawl_dir = crawl_details
    og_url = url

    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    file_name = urlparse(url).hostname

    json_file = crawl_dir + file_name + ".json"
    # Load the data from the .json file
    f = open(json_file, encoding="utf-8")
    json_data = json.load(f)
    f.close()

    api_results = analyze_api_calls(json_data)
    websocket_results = analyze_websockets(json_data)

    return detect_leaks_in_json(crawl_details), \
            {"_recording": og_url,
            "api_summary": api_results,
            "websocket_summary": websocket_results
            }

def analyze_codegen_recordings(crawl_dir):
    """
    Main function.
    """
    crawl_name = basename(crawl_dir)
    print(f"Will search for leaks in {crawl_name}")

    if not crawl_dir.endswith("/") and not crawl_dir.endswith("\\"):
        crawl_dir += "\\"

    successful_urls = get_successful_urls(crawl_dir + "_successful_sites.txt")

    print(f"Will process {len(successful_urls)} jsons")
    crawl_details = []
    for url in successful_urls:
        crawl_details.append((url, crawl_dir))

    counter = 0
    all_summaries = []
    all_site_leaks = []
    all_js_leaks = []
    n_leaky_sites = 0
    all_sniffs = set()

    start_time = time()

    with Pool(processes=(min(cpu_count(), len(successful_urls)))) as pool:
        for leaks, summary in pool.imap_unordered(analyze_site, crawl_details):

            if not counter % 100 and counter != 0:
                passed_time = time() - start_time
                print(
                    "Processed %d jsons. Found %d leaks on %d sites in %0.1fs"
                    % (counter, len(all_site_leaks),
                        n_leaky_sites, passed_time))
            counter += 1

            all_summaries.append(summary)
            if leaks is None:
                continue
            site_leaks, sniffs, js_cookie_leaks = leaks
            all_sniffs.update(sniffs)

            if site_leaks is not None and len(site_leaks):
                # print('Detected leak(s) on', site_leaks[0][7])  # initial host
                all_site_leaks += site_leaks
                n_leaky_sites += 1
            elif js_cookie_leaks is not None and len(js_cookie_leaks):
                print('Detected leaks in js_cookies only', js_cookie_leaks)
                all_js_leaks += js_cookie_leaks

    t_leak_end = time()
    leak_detection_time = t_leak_end - start_time
    print("FINISHED! Processed %d jsons. Found %d leaks on %d sites in %0.1f" %
          (counter, len(all_site_leaks), n_leaky_sites, leak_detection_time))

    #########################################################################################

    # df = pd.DataFrame(all_site_leaks, columns=[
    #     'search', 'search_type', 'encoding', 'leak_type', 'final_url',
    #     'final_url_domain', 'initial_url', 'initial_hostname',
    #     'last_page_domain', 'request_url', 'request_url_domain',
    #     'third_party_req', 'easy_list_blocked', 'easy_privacy_blocked',
    #     'disconnect_blocked', 'radar_blocked', 'whotracksme_blocked', 'tracker_owner',
    #     'is_req_sent_after_fill', 'request_timestamp',
    #     'field_fill_time', 'is_any_initiator_third_party', 'referrer',
    #     'was_cmp_detected', 'is_any_field_filled', 'request', 'request_type', 'category', 'rank_of_site', 'req_initiators', 'xpath', 'id', 'is_same_party', 'req_domain_entity', 'last_page_url', 'req_domain_category'])
    # print(all_site_leaks[0])
    df = pd.DataFrame(all_site_leaks, columns=[
        'search', 'search_type', 'encoding', 'leak_type',
        'final_url', 'final_url_domain', 'initial_url', 'initial_hostname', 
        'last_page_domain', 'request_url', 
        'request_url_domain', 'third_party_req', 'easy_list_blocked', 'easy_privacy_blocked', 'disconnect_blocked',
        'radar_blocked', 'whotracksme_blocked', 'tracker_owner',
        'is_req_sent_after_fill', 'request_timestamp', 'field_fill_time',
        'referrer', 'is_any_field_filled', 'entry', 'request_type', 'category',
        'is_same_party', 'req_domain_entity', 'req_domain_category'])

    # with open("%s_js_cookie_leaks.pkl" % crawl_name, 'wb') as handle:
    #     pickle.dump(all_js_leaks, handle)

    with open("%s_js_cookie_leaks.csv" % crawl_name, 'w', encoding='utf-8') as handle:
        write = csv.writer(handle)
        write.writerows(all_js_leaks)

    # Store data (serialize)
    # with open("%s_sniffs.pkl" % crawl_name, 'wb') as handle:
    #     pickle.dump(all_sniffs, handle)

    with open("%s_sniffs.csv" % crawl_name, 'w', encoding='utf-8') as handle:
        write = csv.writer(handle)
        write.writerows(all_sniffs)

    email_sniffed_set = set()
    pwd_sniffed_set = set()
    for leak_type, initial_hostname, __, __, __ in all_sniffs:
        if leak_type == 'email':
            email_sniffed_set.add(initial_hostname)
        if leak_type == 'pwd':
            pwd_sniffed_set.add(initial_hostname)

    df['email_sniffed'] = df.initial_hostname.map(
        lambda x: x in email_sniffed_set)
    df['pwd_sniffed'] = df.initial_hostname.map(
        lambda x: x in pwd_sniffed_set)

    # df.to_pickle("%s_leaks_df.pkl" % crawl_name)
    df.to_csv("%s_leaks_df.csv" % crawl_name)

if __name__ == "__main__":
    if len(sys.argv) >= 2:  # no arg means process all crawls
        analyze_codegen_recordings(sys.argv[1])
