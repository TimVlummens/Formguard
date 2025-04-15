"""
Based on https://github.com/leaky-forms/leaky-forms/tree/main/leak-detector
"""

from haralyzer import HarParser, HarPage
from datetime import datetime
import json
import os
from os import get_terminal_size
from unicodedata import category
from urllib.parse import urlparse
from tld import get_fld
import ipaddress
from helpers.leak_common import get_domain, get_initiators, get_req_off_site_direction, get_entity
import maya
import pickle
from http import cookies as ck
import leak_detector as LeakDetector
from BlockListParser import (
    get_adblock_rules, easylist_rules_should_block,
    easyprivacy_rules_should_block, disconnect_rules_should_block, get_radar_trackers, get_whotracksme_trackers)

MODULE_DIR = os.path.dirname(os.path.abspath(__file__)) + '/'

with open(MODULE_DIR+'helpers/categories.pkl', 'rb') as handle:
    sites_categories = pickle.load(handle)
# with open(MODULE_DIR+'helpers/categories_dict.pickle.pkl', 'rb') as handle:
with open(MODULE_DIR+'helpers/categories_dict.pickle', 'rb') as handle:
    req_categories = pickle.load(handle)
# with open(MODULE_DIR+'helpers/hostname_rank_pairs.pkl', 'rb') as handle:
#     ranks = pickle.load(handle)

easylist_rules, easyprivacy_rules, disconnect_rules = get_adblock_rules()
tracker_radar_domains_entities_list = get_radar_trackers()
whotracksme_domains_entities_list = get_whotracksme_trackers()
MAX_LEAK_DETECTION_LAYERS = 3
CHECK_REFERRER_LEAKS = True

# PASSWD = 'myPwd1111111111111='
# EMAIL_ADDRESS_PREFIX = 'formisnpector.eu+'
# FILLED_EMAIL_DOMAIN = '@gmail.com'
PASSWD = "TestPass4Sites!"
EMAIL_ADDRESS_PREFIX = "testmail@testing.com"
FILLED_EMAIL_DOMAIN = '@gmail.com'

DETECT_LEAKS_IN_JS_COOKIES = True
SKIP_UNFILLED_SITES = True
ONLY_DETECT_LEAKS_AFTER_FILLING = False
ONLY_DETECT_LEAKS_BEFORE_FILLING = False

def get_ps1_or_host(url):
    """
    Get fld of given url.
    """
    if not url.startswith("http"):
        url = 'http://' + url

    try:
        return get_fld(url, fail_silently=False)
    except Exception:
        hostname = urlparse(url).hostname
        try:
            ipaddress.ip_address(hostname)
            return hostname
        except Exception:
            return ""


def get_email_filled_on_site(site_url):
    """Return the unique email we used for a given site."""
    emailSuffix = urlparse(site_url).hostname
    if emailSuffix.startswith('www.'):
        emailSuffix = emailSuffix[4:]
    return EMAIL_ADDRESS_PREFIX + emailSuffix + FILLED_EMAIL_DOMAIN


def has_tracker_initiator(initiators, request_url_domain, request_type):
    for initiator in initiators:
        try:
            easy_list_result = easylist_rules_should_block(easylist_rules, initiator, request_url_domain, request_type)
            easy_privacy_result = easyprivacy_rules_should_block(easyprivacy_rules, initiator, request_url_domain, request_type)
            disconnect_result = disconnect_rules_should_block(disconnect_rules, initiator)
            if easy_list_result | easy_privacy_result | disconnect_result:
                return True
        except Exception as ex:
            print('Error while checking blocklists, ', initiator, ex)
            continue
    return False


def has_third_party_initiator(initiators, final_url_domain):
    for initiator in initiators:
        initiator_domain = get_fld(initiator, fail_silently=True)
        if initiator_domain is None:
            # e.g. puppeteer evaluation script
            continue
        if initiator_domain != final_url_domain:
            return True
    return False


DEBUG = False


def detect_leaks_in_response(detector, response):
    cookie_str = ''
    location_str = ''
    n_layers = MAX_LEAK_DETECTION_LAYERS
    headers = response.get('headers', [])
    for header in headers:
        if header.get("name", '').lower() == "set-cookie":
            cookie_str = header.get("value", '')
    location_str = response.get('redirectURL', '')
    cookie_leaks = detector.check_cookie_str(cookie_str, encoding_layers=n_layers)
    location_leaks = detector.check_location_header(location_str)
    return cookie_leaks, location_leaks


def detect_leaks_in_request(detector, request):
    url, post_data = request['url'], request.get('postData')
    cookies = request.get('cookies', [])
    post_body = ''
    if post_data is not None:
        post_body = request.get('postData').get('text', '')
    headers = request.get('headers', [])
    referrer_str = ""
    cookie_str = ""
    for header in headers:
        if header.get("name", '').lower() == "referer":
            referrer_str = header.get("value", '')
        if header.get("name", '').lower() == "cookie":
            cookie_str = header.get("value", '')

    n_layers = MAX_LEAK_DETECTION_LAYERS
    url_leaks = detector.check_url(url, encoding_layers=n_layers)
    # cookie_leaks = detector.substring_search(cookie_str, max_layers=n_layers)
    cookie_leaks = detector.check_cookie_str(cookie_str, encoding_layers=n_layers)

    post_leaks = detector.check_post_data(post_body, encoding_layers=n_layers)
    if CHECK_REFERRER_LEAKS:
        referrer_leaks = detector.check_referrer_str(
            referrer_str, encoding_layers=n_layers
            )
        # if referrer_leaks:
            # print("FOUND REFERRER LEAKS", len(referrer_leaks), referrer_leaks, referrer_str)
        # referrer_leaks = detector.substring_search(referrer_str, max_layers=MAX_LEAK_DETECTION_LAYERS)
        return url_leaks, cookie_leaks, post_leaks, referrer_leaks
    else:
        return url_leaks, cookie_leaks, post_leaks, []


def get_referrer(request):
    try:
        headers = request.get('headers', [])
        referrer_str = ""
        for header in headers:
            if header.get("name", '').lower() == "referer":
                referrer_str = header.get("value", '')
        return referrer_str
    except KeyError:
        return ""


def get_leakage_details(entry, final_url, initial_hostname, initial_url, detector, fill_timestamp, filled_values, request_timestamp, searches):
    """
    Find leaks for the given entry.
    """
    request_url = entry['request']['url']

    try:
        request_url_domain = get_ps1_or_host(request_url)
        final_url_domain = get_fld(final_url)
    except Exception as err:
        print('Error while parsing url', request_url, final_url, err)
        return None

    url_leaks, cookie_leaks, post_leaks, referrer_leaks = \
        detect_leaks_in_request(detector, entry["request"])
    response_cookie_leaks, response_location_leaks = \
        detect_leaks_in_response(detector, entry["response"])

    if not any([
        url_leaks, cookie_leaks, post_leaks, referrer_leaks,
            response_cookie_leaks, response_location_leaks]):
        return None
    # if not (len(url_leaks) or len(cookie_leaks) or len(post_leaks) or len(referrer_leaks)):
    #     return None

    referrer = get_referrer(entry["request"])
    # TODO
    request_type = "document"
    # request_type = (request['type']).lower()
    # last_page_domain_iframe = get_domain(last_page_url)
    last_page_domain_iframe, last_page_domain = get_domain(final_url), get_domain(final_url)
    is_same_party = get_req_off_site_direction(last_page_domain_iframe, request_url_domain, last_page_domain)
    req_domain_entity = get_entity(request_url_domain)
    field_fill_time = fill_timestamp
    try:
        category = sites_categories[final_url_domain]
    except:
        category = ''
        # print('Category data not found', final_url_domain)
    try:
        if request_url_domain in req_categories:
            req_domain_category = ', '.join(list(req_categories[request_url_domain])[0:2])
        else:
            req_domain_category = ''
    except:
        req_domain_category = ''
    # TODO
    # rank_of_site = ranks[initial_hostname]
    # req_initiators = get_initiators(request['initiators'])
    is_req_sent_after_fill = request_timestamp > field_fill_time
    is_any_field_filled = len(filled_values) != 0
    third_party_req = last_page_domain != request_url_domain
    easy_list_blocked = False
    easy_privacy_blocked = False
    disconnect_blocked = False
    DISABLE_ADBLOCK_CHECKS = False
    radar_blocked = False
    whotracksme_blocked = False
    tracker_owner = ''
    try:
        if not DISABLE_ADBLOCK_CHECKS:
            easy_list_blocked = easylist_rules_should_block(
                easylist_rules, request_url, request_url_domain, request_type)
            easy_privacy_blocked = easyprivacy_rules_should_block(
                easyprivacy_rules, request_url, request_url_domain, request_type)
            disconnect_blocked = disconnect_rules_should_block(
                disconnect_rules, request_url)
            radar_blocked = True if request_url_domain in tracker_radar_domains_entities_list else False
            whotracksme_blocked = True if request_url_domain in whotracksme_domains_entities_list else False
            if request_url_domain in whotracksme_domains_entities_list:
                tracker_owner = whotracksme_domains_entities_list[request_url_domain]
            elif request_url_domain in tracker_radar_domains_entities_list:
                tracker_owner = tracker_radar_domains_entities_list[request_url_domain]
    except Exception as ex:
        print('Error while checking blocklists, ', request_url, ex)

    # initiators = request['initiators']
    # req_has_third_party_initiator = has_third_party_initiator(
    #     initiators, final_url_domain)
    # req_tracker_initiator = has_tracker_initiator(initiators, request_url_domain, request_type)
    # was_cmp_detected = initial_hostname in cmp_websites

    leaks_dict = {
        'cookie_leaks': cookie_leaks, 'url_leaks': url_leaks,
        'post_leaks': post_leaks, 'referrer_leaks': referrer_leaks,
        'response_cookie_leaks': response_cookie_leaks,
        'response_location_leaks': response_location_leaks
        }
    # leaks_for_req = get_leak_details(
    #     leaks_dict, final_url, final_url_domain, initial_hostname,
    #     initial_url_domain, last_page_domain, third_party_req,
    #     easy_list_blocked, easy_privacy_blocked, disconnect_blocked,
    #     radar_blocked, whotracksme_blocked, tracker_owner,
    #     is_req_sent_after_fill, request_timestamp, field_fill_time,
    #     req_has_third_party_initiator, referrer,
    #     was_cmp_detected,
    #     is_any_field_filled, request_url, request_url_domain, request, request_type, category, rank_of_site, req_initiators, xpath, id, is_same_party, req_domain_entity, last_page_url, req_domain_category)
    leaks_for_req = get_leak_details(
        leaks_dict, final_url, final_url_domain, initial_url, initial_hostname,
        last_page_domain, third_party_req,
        easy_list_blocked, easy_privacy_blocked, disconnect_blocked,
        radar_blocked, whotracksme_blocked, tracker_owner,
        is_req_sent_after_fill, request_timestamp, field_fill_time,
        referrer, is_any_field_filled, request_url, request_url_domain, entry, request_type, category, is_same_party, req_domain_entity, req_domain_category, searches)
    return leaks_for_req


def get_leak_encoding(leak):
    # print(leak, len(leak), leak[0])
    # assert len(leak) <= 2
    if len(leak) == 2:
        encoding, search = leak
    elif len(leak) == 1:
        search = leak[0]
        encoding = "unencoded"
    else:  # double hashes, double encodings etc.
        search = leak[-1]
        encoding = "-".join(leak[:-1])
    return search, encoding


def get_search_type(search, searches = None):
    # return 'email' if 'gmail' in search else 'pwd'
    if searches is None:
        return 'email' if '@' in search else 'pwd'
    else:
        for type, values in searches.items():
            if search in values:
                return type
        return 'unknown'


def get_leak_details(
    leaks_dict, final_url, final_url_domain, initial_url, initial_hostname,
    last_page_domain, third_party_req,
    easy_list_blocked, easy_privacy_blocked, disconnect_blocked,
    radar_blocked, whotracksme_blocked, tracker_owner,
    is_req_sent_after_fill, request_timestamp, field_fill_time,
    referrer, is_any_field_filled, request_url, request_url_domain, entry, request_type, category, is_same_party, req_domain_entity, req_domain_category, searches):

    leaks_for_req = []
    for leak_type, leaks in leaks_dict.items():
        for leak in leaks:
            search, encoding = get_leak_encoding(leak)
            search_type = get_search_type(search, searches)
            # print("Leak with layered encoding/hashing", len(leak), leak)
            leaks_for_req.append(
                (search, search_type, encoding, leak_type,
                 final_url, final_url_domain, initial_url, initial_hostname,
                 last_page_domain, request_url,
                 request_url_domain, third_party_req,  easy_list_blocked, easy_privacy_blocked, disconnect_blocked,
                 radar_blocked, whotracksme_blocked, tracker_owner,
                 is_req_sent_after_fill, request_timestamp, field_fill_time,
                 referrer, is_any_field_filled, entry, request_type, category, is_same_party, req_domain_entity, req_domain_category))
    return leaks_for_req


def should_skip_leak_check(event_timestamp, fill_timestamp):
    """Check if we should skip detecting leaks in a request or a cookie."""
    if ONLY_DETECT_LEAKS_AFTER_FILLING:
        if (event_timestamp and fill_timestamp and
                event_timestamp < (fill_timestamp - 3)):  # buffer time
            # print("Will skip the pre-fill request/cookie", event_timestamp,
            #       fill_timestamp, (event_timestamp - fill_timestamp))
            return True

    elif ONLY_DETECT_LEAKS_BEFORE_FILLING:
        if not event_timestamp:
            return True
        if fill_timestamp and (event_timestamp > fill_timestamp):
            # print("Will skip the post-fill request/cookie", event_timestamp,
            #       fill_timestamp, (event_timestamp - fill_timestamp))
            return True
    return False


def detect_leaks_in_js_cookies(
    js_cookies, initial_hostname, initial_url, leak_detector, final_url,
        fill_timestamps, last_page_urls, filled_websites, cmp_websites):
    last_page_url = last_page_urls.get(initial_hostname, final_url)
    cmp_detected = initial_hostname in cmp_websites
    filled = initial_hostname in filled_websites
    leaks = []

    if not len(js_cookies):
        return None

    fill_timestamp = fill_timestamps.get(initial_hostname)
    if ONLY_DETECT_LEAKS_AFTER_FILLING and fill_timestamp is None:
        return None

    for js_cookie in js_cookies:
        source, cookie_str, cookie_timestamp = js_cookie
        if should_skip_leak_check(cookie_timestamp, fill_timestamp):
            continue

        cookie_leaks = leak_detector.check_cookie_str(
            cookie_str, encoding_layers=MAX_LEAK_DETECTION_LAYERS)
        if not cookie_leaks:
            continue
        try:
            cookies = ck.SimpleCookie()
            cookies.load(cookie_str)
            final_domain = get_fld(final_url)
            print("COOKIE LEN", len(cookies))
            for cookie in cookies.values():
                print("COOKIE", initial_hostname, final_domain, cookie.key, cookie.value, cookie.get('secure'),
                      cookie.get('httponly'), cookie.get('expires'),
                      cookie_str, source)
        except ck.CookieError:
            pass

        for leak in cookie_leaks:
            search, encoding = get_leak_encoding(leak)
            search_type = get_search_type(search)
            leaks.append(
                [initial_hostname, search_type, search, encoding, cookie_str,
                 source, initial_url, final_url, last_page_url, cmp_detected,
                 filled])
    return leaks


def detect_leaks_in_requests(entries, initial_hostname, initial_url, leak_detector, final_url, filled_values, searches):
    """
    Check all request entries for leaks.
    """
    all_leaks = []

    if len(entries) == 0:
        print('No requests in', final_url)
        return None

    timestamps = []
    for field in filled_values:
        timestamp = field.get("start_time", 0)
        if timestamp is not None:
            timestamps.append(int(timestamp))

    if ONLY_DETECT_LEAKS_AFTER_FILLING and len(timestamps) == 0:
        print("No timestamps found in ", final_url)
        return None

    fill_timestamp = min(timestamps)

    p = '%Y-%m-%dT%H:%M:%S.%fZ'

    for entry in entries:
        timestamp = entry.get('startedDateTime', 0)
        timestamp = datetime.strptime(timestamp, p)
        req_timestamp = (timestamp - datetime(1970, 1, 1)).total_seconds()
        # if not req_timestamp:
        #     assert request['type'] == 'WebSocket'
        if should_skip_leak_check(req_timestamp, fill_timestamp):
            continue
        if entry['request']['url'].startswith('blob:'):
            continue

        leak_details = get_leakage_details(
            entry, final_url, initial_hostname, initial_url, leak_detector,
            fill_timestamp, filled_values, req_timestamp, searches)

        if leak_details is not None:
            all_leaks += leak_details
    return all_leaks

def detect_leaks_in_frames(frames, initial_hostname, initial_url, leak_detector, final_url, filled_values, searches):
    """
    Check all websocket frames for leaks.
    """
    all_leaks = []

    if len(frames) == 0:
        # print('No frames in', final_url)
        return None

    timestamps = []
    for field in filled_values:
        timestamp = field.get("start_time")
        if timestamp is not None:
            timestamps.append(int(timestamp))

    if ONLY_DETECT_LEAKS_AFTER_FILLING and len(timestamps) == 0:
        print("No timestamps found in ", final_url)
        return None

    fill_timestamp = min(timestamps)
    frame_leaks = []
    is_any_field_filled = len(filled_values) != 0

    for frame in frames:
        timestamp = frame.get('wallTime', 0)
        req_timestamp = int(timestamp)
        # if not req_timestamp:
        #     assert request['type'] == 'WebSocket'
        if should_skip_leak_check(req_timestamp, fill_timestamp):
            continue
        is_req_sent_after_fill = req_timestamp > fill_timestamp
        if frame['url'].startswith('blob:'):
            continue

        n_layers = MAX_LEAK_DETECTION_LAYERS
        frame_leaks += leak_detector.substring_search(str(frame.get("postData", "")), max_layers=n_layers)

        leaks_dict = {"websocket_leaks": frame_leaks}

        try:
            request_url_domain = get_ps1_or_host(frame['url'])
            final_url_domain = get_fld(final_url)
        except Exception as err:
            print('Error while parsing url', frame['url'], final_url, err)
            return None
        
        
        is_same_party = get_req_off_site_direction(final_url_domain, request_url_domain, final_url_domain)
        request_url = frame['url']
        request_type = "websocket"
        third_party_req = final_url_domain != request_url_domain

        easy_list_blocked = False
        easy_privacy_blocked = False
        disconnect_blocked = False
        DISABLE_ADBLOCK_CHECKS = False
        radar_blocked = False
        whotracksme_blocked = False
        tracker_owner = ''
        referrer = ""
        try:
            if not DISABLE_ADBLOCK_CHECKS:
                easy_list_blocked = easylist_rules_should_block(
                    easylist_rules, request_url, request_url_domain, request_type)
                easy_privacy_blocked = easyprivacy_rules_should_block(
                    easyprivacy_rules, request_url, request_url_domain, request_type)
                disconnect_blocked = disconnect_rules_should_block(
                    disconnect_rules, request_url)
                radar_blocked = True if request_url_domain in tracker_radar_domains_entities_list else False
                whotracksme_blocked = True if request_url_domain in whotracksme_domains_entities_list else False
                if request_url_domain in whotracksme_domains_entities_list:
                    tracker_owner = whotracksme_domains_entities_list[request_url_domain]
                elif request_url_domain in tracker_radar_domains_entities_list:
                    tracker_owner = tracker_radar_domains_entities_list[request_url_domain]
        except Exception as ex:
            print('Error while checking blocklists, ', request_url, ex)
        
        try:
            category = sites_categories[final_url_domain]
        except:
            category = ''
            print('Category data not found', final_url_domain)
        try:
            if request_url_domain in req_categories:
                req_domain_category = ', '.join(list(req_categories[request_url_domain])[0:2])
            else:
                req_domain_category = ''
        except:
            req_domain_category = ''

        req_domain_entity = get_entity(request_url_domain)

        leaks_for_req = get_leak_details(
                leaks_dict, final_url, final_url_domain, initial_url, initial_hostname,
                get_domain(final_url), third_party_req,
                easy_list_blocked, easy_privacy_blocked, disconnect_blocked,
                radar_blocked, whotracksme_blocked, tracker_owner,
                is_req_sent_after_fill, req_timestamp, fill_timestamp,
                referrer, is_any_field_filled, request_url, request_url_domain, frame, request_type, category, is_same_party, req_domain_entity, req_domain_category, searches)

    if leaks_for_req is not None:
        return leaks_for_req
    return []


def get_cookie_timestamp(js_cookie, initial_hostname):
    try:
        return float(js_cookie['timestamp'])
    except Exception:
        try:
            # some weird cookies have data strings instead of
            # a unix timestamp. Possibly due to scripts
            # overwriting Date
            return maya.parse(
                js_cookie['timestamp'].strip('"')
                ).datetime().timestamp()
        except Exception:
            print(initial_hostname,
                  "Malformed cookie timestamp: %s Cookie: %s" %
                  (js_cookie['timestamp'], js_cookie))
            # if we can't parse the date, we set the timestamp to a high
            # number to consider the cookie in the leak detection
            return 0


DESC_JS_COOKIE_SET = "Document.cookie setter"


def get_js_cookies(calls, initial_hostname):
    js_cookies = []
    if not calls or not calls['savedCalls']:
        return js_cookies
    for saved_call in calls['savedCalls']:
        if saved_call['description'] != DESC_JS_COOKIE_SET:
            continue
        js_ck = saved_call
        if not js_ck['arguments']:
            # print(initial_hostname, "Missing cookie arguments: %s Cookie: %s" %
            #       (js_ck['arguments'], js_ck))
            continue
        # setting the cookie value to '' is used to remove the cookie
        if not js_ck['arguments'][0]:
            continue
        timestamp = get_cookie_timestamp(js_ck, initial_hostname)
        js_cookies.append((js_ck['source'], js_ck['arguments'][0], timestamp))

    return js_cookies


def get_input_field_sniffers(input_reads, initial_hostname, search_terms, searches):
    """
    Check if any inputs have been sniffed by API calls.
    """
    sniffs = set()
    if not input_reads:
        return sniffs
    for input_read in input_reads:
        read_details = input_read['details']
        if 'value' not in read_details:
            continue
        sniffed_value = read_details['value']

        if 'source' not in input_read:
            source = None
        else:
            source = input_read['source']

        scripts_tuple = tuple(input_read.get('scripts', []))

        if sniffed_value not in search_terms:
            continue

        for type, type_searches in searches.items():
            if sniffed_value in type_searches:
                sniffs.add((type, initial_hostname, source, sniffed_value, scripts_tuple))
                continue

    return sniffs


def detect_leaks_in_json(crawl_details):
    """
    Detect leaks for a single site using its json and har file.
    """
    # try:
    (url, crawl_dir) = crawl_details

    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    file_name = urlparse(url).hostname
    file_path = crawl_dir + file_name

    # Load json and har file
    json_results = json.loads(open(file_path+".json", encoding='utf-8').read())
    with open(file_path+".har", 'r', encoding='utf-8') as f:
        har_parser = HarParser(json.loads(f.read()))
    har_results = har_parser.har_data

    final_url = json_results['general']['page_url']
    if final_url == "about:blank":
        return None

    calls = json_results['apis']

    initial_url = url
    # hostname of the initial url is used in the logs
    # so it's easier to join data by this hostname
    initial_hostname = urlparse(initial_url).hostname

    input_reads = calls.get('input_element_results') if calls else None

    entries = har_results['entries']
    frames = json_results["websockets"]["received"]
    frames += json_results["websockets"]["sent"]

    filled_values = json_results["filled_values"]
    if SKIP_UNFILLED_SITES and len(filled_values) == 0:
        # print("No input field found, will skip", initial_hostname)
        return None

    # print("Will search for leaks", initial_hostname)

    searches = {}
    search_terms = set()
    for field in filled_values:
        if field["type"] not in searches:
            searches[field["type"]] = set()
        searches[field["type"]].add(field["value"])
        searches[field["type"]].add(field["value"][:-1])
        searches[field["type"]].add(field["value"][:-2])

        search_terms.add(field["value"])
        search_terms.add(field["value"][:-1])
        search_terms.add(field["value"][:-2])


    sniffs = get_input_field_sniffers(
        input_reads, initial_hostname, search_terms, searches)

    leak_detector = LeakDetector.LeakDetector(
        search_terms,
        encoding_set=LeakDetector.LIKELY_ENCODINGS,
        hash_set=LeakDetector.LIKELY_HASHES,
        encoding_layers=MAX_LEAK_DETECTION_LAYERS,
        hash_layers=MAX_LEAK_DETECTION_LAYERS,
        debugging=False
    )

    site_leaks = detect_leaks_in_requests(
        entries, initial_hostname, initial_url, leak_detector, final_url,
        filled_values, searches)

    socket_leaks = detect_leaks_in_frames(
        frames, initial_hostname, initial_url, leak_detector, final_url,
        filled_values, searches)

    if socket_leaks:
        site_leaks += socket_leaks

    if site_leaks and not calls:
        print("LEAK detected BUT NO CALLS", initial_hostname, site_leaks)
    js_cookie_leaks = None
    return site_leaks, sniffs, js_cookie_leaks
    # except Exception as e:
    #     print(e)
    #     return None
