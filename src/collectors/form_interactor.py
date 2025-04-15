"""
Module for filling input fields and scrolling on the page.
"""
import random
import time
import os
import sys
from random import randint
from tld import get_fld
from playwright.sync_api import sync_playwright, Locator, Frame, Page, \
    TimeoutError as PlaywrightTimeoutError

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.form_finder import FormFinder, register_selectors

CLICK_DWELL_TIME = 100
CLICK_DWELL_TIME_RANGE = 50
KEY_DWELL_TIME = 50
KEY_DWELL_TIME_RANGE = 50
KEY_DELAY_TIME = 150
KEY_DELAY_TIME_RANGE = 50

SCROLL_INTERVAL = 500
SCROLL_INTERVAL_RANGE = 100
SCROLL_SIZE = 400
SCROLL_SIZE_RANGE = 100

SCROLL_MIN = int(SCROLL_SIZE - SCROLL_SIZE_RANGE / 2)
SCROLL_MAX = int(SCROLL_SIZE + SCROLL_SIZE_RANGE / 2)
SCROLL_INTERVAL_MIN = int(SCROLL_INTERVAL - SCROLL_INTERVAL_RANGE / 2)
SCROLL_INTERVAL_MAX = int(SCROLL_INTERVAL + SCROLL_INTERVAL_RANGE / 2)

CLICK_DWELL_TIME_MIN = CLICK_DWELL_TIME - CLICK_DWELL_TIME_RANGE
CLICK_DWELL_TIME_MAX = CLICK_DWELL_TIME + CLICK_DWELL_TIME_RANGE
KEY_DWELL_TIME_MIN = KEY_DWELL_TIME - KEY_DWELL_TIME_RANGE
KEY_DWELL_TIME_MAX = KEY_DWELL_TIME + KEY_DWELL_TIME_RANGE
KEY_DELAY_TIME_MIN = KEY_DELAY_TIME - KEY_DELAY_TIME_RANGE
KEY_DELAY_TIME_MAX = KEY_DELAY_TIME + KEY_DELAY_TIME_RANGE


PASSWORD_INPUT = "TestPass4Sites!"
EMAIL_INPUT = "testmail@testing.com"

EMAIL_PREFIX = "testmail+"
EMAIL_SUFFIX = "@testing.com"

TIMEOUT = 5000

def get_email_to_fill(url):
    """
    Return the email to fill based on the given url.
    """
    # return EMAIL_INPUT
    domain = get_fld(url, fail_silently=True)
    if domain is None:
        return EMAIL_PREFIX + "unknown" + EMAIL_SUFFIX
    return EMAIL_PREFIX + domain + EMAIL_SUFFIX

def fill_fields(fields : dict, frame : Frame, log, max_fields : int = 2, \
                password_input = PASSWORD_INPUT, email_input = EMAIL_INPUT):
    """
    Fill in the provided fields, with a separate input for password and email fields.
    Only fills in max_fields of each field type. If max_fields == 0, all fields are filled.
    """
    func_start_time = time.time()
    filled_values = []
    # filled_ids = set()
    field = None
    submit_timestamp = None

    keys = ["password", "email"]
    inputs = {"password": password_input, "email": email_input}

    for key in keys:
        count = 0
        if key in fields.keys():
            for field in fields[key]:
                if max_fields == 0 or count < max_fields:
                    fill_start_time = time.time()
                    value = fill_field(field, frame, log, inputs[key])
                    if value != "":
                        fill_stop_time = time.time()
                        field_id = field.get_attribute("id")
                        field_name = field.get_attribute("name")
                        filled_values.append({"url": field.page.url,
                                            "value": value,
                                            "start_time": fill_start_time,
                                            "stop_time": fill_stop_time,
                                            "type": key,
                                            "id": field_id,
                                            "name": field_name
                                            })
                        count += 1
                else:
                    break

    if field is not None:
        try:
            with frame.expect_navigation(wait_until="networkidle", timeout=TIMEOUT):
                field.evaluate("node => node?.form?.submit()")
                submit_timestamp = time.time()
                log(f"✏️ Submitted form at {submit_timestamp} on {frame.url}")
        except PlaywrightTimeoutError:
            log(f"✏️ FormInteractor: No navigation after submitting form on {frame.url}")
            submit_timestamp = time.time()
        except Exception as e:
            log(f"✏️ Could not submit form on {frame.url}")
            print(e)

    func_end_time = time.time()
    log(f"✏️ fill_fields took {func_end_time-func_start_time:0.1f} s on {frame.url}")
    return filled_values, submit_timestamp

def fill_field(field : Locator, frame : Frame, log, field_input : str = "test"):
    """
    Fill the given field with the specified input by:
    scrolling the field into view.
    clicking on the input field.
    pressing each key one by one with a random time between each press.
    """
    # Scroll to field
    # print(field)
    try:
        field.scroll_into_view_if_needed(timeout = 2000)
    except PlaywrightTimeoutError:
        log(f"❌ Error finding field {field} on {frame.url}")
        return ""
    # Click on field
    try:
        box = field.bounding_box(timeout= 2000)
        # Create coordinates for where to click the button in a rectangle around the center
        x_coord = randint(int(box["x"] + box["width"]/4), int(box["x"] + 3*(box["width"]/4)))
        y_coord = randint(int(box["y"] + box["height"]/4), int(box["y"] + 3*(box["height"]/4)))

        frame.mouse.move(x_coord, y_coord)
        frame.wait_for_timeout(randint(CLICK_DWELL_TIME_MIN, CLICK_DWELL_TIME_MAX))
        frame.mouse.click(x_coord, y_coord, \
                          delay=randint(CLICK_DWELL_TIME_MIN, CLICK_DWELL_TIME_MAX))
    except PlaywrightTimeoutError:
        log(f"❌ FormInteractor: Error finding bounding box of field {field} on {frame.url}")
        return ""
    # Fill field key by key
    try:
        dwell_time = type_sequentially(field, field_input, frame)

        field.press("Tab", delay=dwell_time)
    except PlaywrightTimeoutError:
        log(f"❌ FormInteractor: Error filling field {field} on {frame.url}")
        return ""
    return field_input

def type_sequentially(field : Locator, field_input : str, frame : Frame):
    """
    Press keys sequentially with random delay.
    """
    for key in field_input:
        dwell_time = randint(KEY_DWELL_TIME_MIN, KEY_DWELL_TIME_MAX)
        field.press(key, delay=dwell_time)
        frame.wait_for_timeout(randint(KEY_DELAY_TIME_MIN, KEY_DELAY_TIME_MAX))
    return dwell_time

def scroll_to_bottom(page : Page, log = print, scroll_back : bool = False):
    """
    Function that tries to scroll to the bottom of the given page, or fifty times in case of
    long/infinite page. Scrolling happens in variating sizes and intervals.
    """
    func_start_time = time.time()
    nb_of_scrolls = 0
    max_nb_of_scrolls = 50

    prev_height = None
    while nb_of_scrolls < max_nb_of_scrolls:
        nb_of_scrolls += 1

        page.mouse.wheel(0, randint(SCROLL_MIN, SCROLL_MAX))
        page.wait_for_timeout(randint(SCROLL_INTERVAL_MIN, SCROLL_INTERVAL_MAX))
        curr_height = page.evaluate('(window.innerHeight + window.pageYOffset)')
        # print(curr_height)

        if not prev_height or prev_height != curr_height:
            prev_height = curr_height
        else:
            break
    if scroll_back:
        page.evaluate("() => {window.scrollTo(0, 0);}")
    func_end_time = time.time()
    log(f"✏️ scroll_to_bottom took {func_end_time-func_start_time:0.1f}" + \
        f"s on {page.url}")
