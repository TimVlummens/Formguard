"""
Module to detect login and signup pages.
Based on https://github.com/asumansenol/double_edged_sword_crawler/blob/main/collectors/LoginSignupPageCollector.js
"""
import os
import time
import sys
import tld
import numpy as np

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'  # disable tensorflow warnings
import tensorflow as tf

from playwright.sync_api import sync_playwright, Page

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import helpers
import cookie_accept

from os.path import abspath, dirname, join
MODULE_DIR = dirname(abspath(__file__))
MODULE_PARENT_DIR = dirname(MODULE_DIR)
MODEL_SRC_PATH = join(MODULE_PARENT_DIR, "model", "python_model")
INJECT_DIR = join(MODULE_PARENT_DIR, "inject")

LINK_HELPER_SRC = join(INJECT_DIR, "linkHelper.js")
IS_SHOWN_SRC = join(INJECT_DIR, "isShown.js")
REGISTER_LOGIN_FEAT_EXTRACTION_FOLDER = join(INJECT_DIR, "register_login_feature_extraction")
VOCAB_FOLDER = join(REGISTER_LOGIN_FEAT_EXTRACTION_FOLDER, "register_login_vocabulary")

ACCOUNT_VOCABS_SRC = join(VOCAB_FOLDER, "account_vocabs.js")
CONFIRM_VOCABS_SRC = join(VOCAB_FOLDER, "confirm_vocabs.js")
CURRENT_VOCABS_SRC = join(VOCAB_FOLDER, "current_vocabs.js")
FORGOT_ACTION_VOCABS_SRC = join(VOCAB_FOLDER, "forgot_action_vocabs.js")
FORGOT_VOCABS_SRC = join(VOCAB_FOLDER, "forgot_vocabs.js")
HAVE_VOCABS_SRC = join(VOCAB_FOLDER, "have_vocabs.js")
LOGIN_ACTION_VOCABS_SRC = join(VOCAB_FOLDER, "login_action_vocabs.js")
LOGIN_VOCABS_SRC = join(VOCAB_FOLDER, "login_vocabs.js")
NEW_VOCABS_SRC = join(VOCAB_FOLDER, "new_vocabs.js")
NEWSLETTER_VOCABS_SRC = join(VOCAB_FOLDER, "newsletter_vocabs.js")
NEXT_VOCABS_SRC = join(VOCAB_FOLDER, "next_vocabs.js")
NOT_HAVE_VOCABS_SRC = join(VOCAB_FOLDER, "not_have_vocabs.js")
PASSWORD_ATTR_VOCABS_SRC = join(VOCAB_FOLDER, "password_attr_vocabs.js")
PASSWORD_VOCABS_SRC = join(VOCAB_FOLDER, "password_vocabs.js")
REGISTER_ACTION_VOCABS_SRC = join(VOCAB_FOLDER, "register_action_vocabs.js")
REGISTER_VOCABS_SRC = join(VOCAB_FOLDER, "register_vocabs.js")
REMEMBER_ME_ACTION_VOCABS_SRC = join(VOCAB_FOLDER, "remember_me_action_vocabs.js")
REMEMBER_ME_VOCABS_SRC = join(VOCAB_FOLDER, "remember_me_vocabs.js")
USERNAME_VOCABS_SRC = join(VOCAB_FOLDER, "username_vocabs.js")

REGISTER_LOGIN_REGEX_PATTERNS_SRC = join(REGISTER_LOGIN_FEAT_EXTRACTION_FOLDER,
                                         "register_login_regexes.js")
REGISTER_LOGIN_SIGNALS_UTILS_SRC = join(REGISTER_LOGIN_FEAT_EXTRACTION_FOLDER,
                                        "register_login_signals_utils.js")
REGISTER_LOGIN_SIGNALS_SRC = join(REGISTER_LOGIN_FEAT_EXTRACTION_FOLDER,
                                  "register_login_signals.js")

SCRIPTS_TO_INJECT = [
    LINK_HELPER_SRC, IS_SHOWN_SRC, ACCOUNT_VOCABS_SRC, CONFIRM_VOCABS_SRC, \
    CURRENT_VOCABS_SRC, FORGOT_ACTION_VOCABS_SRC, FORGOT_VOCABS_SRC, \
    HAVE_VOCABS_SRC, LOGIN_ACTION_VOCABS_SRC, LOGIN_VOCABS_SRC, NEW_VOCABS_SRC, \
    NEWSLETTER_VOCABS_SRC, NEXT_VOCABS_SRC, NOT_HAVE_VOCABS_SRC, \
    PASSWORD_ATTR_VOCABS_SRC, PASSWORD_VOCABS_SRC, REGISTER_ACTION_VOCABS_SRC, \
    REGISTER_VOCABS_SRC, REMEMBER_ME_ACTION_VOCABS_SRC, REMEMBER_ME_VOCABS_SRC, \
    USERNAME_VOCABS_SRC, REGISTER_LOGIN_REGEX_PATTERNS_SRC, \
    REGISTER_LOGIN_SIGNALS_UTILS_SRC, REGISTER_LOGIN_SIGNALS_SRC
    ]


INNER_LINKS_QUERY = """
            // select a and button elements
            (function getLinks() {
                const links = window.document.querySelectorAll('a, button');
                // find the center of the viewport
                const center = {
                    x: window.innerWidth / 2,
                    y: window.innerHeight / 2
                };
                let linkAttrs = [];
                for (const link of links) {
                    // find the center of each link
                    const rect = link.getBoundingClientRect();
                    const linkCenter = {
                        x: rect.left + (rect.width / 2),
                        y: rect.top + (rect.height / 2)
                    };
                    // find the distance between the link and the viewport center
                    const distance = Math.hypot(center.x - linkCenter.x, center.y - linkCenter.y);
                    const href = link.getAttribute('href');
                    // get the title of the link
                    const title = link.getAttribute('title');
                    // get the text of the link
                    const text = link.innerText;
                    if (href) {
                        linkAttrs.push({
                            distance,
                            href,
                        });
                    }
                    // add the distance and the href to an array
                }
                // sort the array by distance, ascending
                linkAttrs.sort((a, b) => a.distance - b.distance);
                return [...new Set(linkAttrs.map(link => link.href))];
            })();
            """

EXCLUDED_EXTS = [".jpg", ".jpeg", ".pdf", ".png"]
N_URL_CHARS_TO_LOG = 64  # to avoid long urls in logs

class LoginSignupPageCollector:
    """
    Class for detecting login and signup pages.
    """
    SAVE_STACKTRACE_SCRIPT_URLS_ONLY = True

    def __init__(self, log = print):
        self._log = log
        self._links = []
        self._internal_links = []
        self._model = self._load_model()
        self._script_src_bundle = self.build_script_bundle()

    def build_script_bundle(self):
        """
        Build the script bundle.
        """
        script_src_bundle = ""
        for script in SCRIPTS_TO_INJECT:
            script_src_bundle += open(script, "r", encoding='utf-8').read()
        return script_src_bundle

    def _load_model(self):
        """
        Load the ML model.
        """
        self._log(f"📃 Model loading in progress from  {MODEL_SRC_PATH}")
        model = tf.saved_model.load(MODEL_SRC_PATH)
        return model

    def add_scripts_before_navigation(self, page : Page, log = print):
        """
        Add the necessary scripts to a given page.
        """
        if page:
            log(f"🔗 Adding the necessary scripts on {page.url}")
            try:
                page.add_init_script(script=self._script_src_bundle)
            except Exception as e:
                log(f"❌ Login/Signup Collector: Error while adding scripts on {page.url}: {e}")

    def _should_include_link(self, link_url_stripped : str, page_domain : str, page_url : str, \
                             log = print):
        """
        Check if the given link should be saved in the found links.
        """
        LOG_SKIPPED_LINKS = False
        if tld.get_fld(link_url_stripped, fail_silently=True) != page_domain:
            if LOG_SKIPPED_LINKS:
                log(f"🔗 Will skip the external link: {link_url_stripped}")
            return False
        if any(file_ext in link_url_stripped for file_ext in EXCLUDED_EXTS):
            if LOG_SKIPPED_LINKS:
                log(f"🔗 Bad file extension, will skip: {link_url_stripped}")
            return False
        page_url_stripped = page_url
        if page_url_stripped.endswith("#") or page_url_stripped.endswith("/"):
            page_url_stripped = page_url_stripped[:-1]
        if link_url_stripped == page_url_stripped:
            if LOG_SKIPPED_LINKS:
                log(f"🔗 Skipping same page link: {link_url_stripped} ({page_url})")
            return False

        return True

    def _control_links(self, links : list, page_url : str, page_domain : str, log = print):
        """
        Checks each link in the list of links to see if they should be kept.
        Returns a list containing only thest valid links.
        """
        return_links = set()

        for link in links:
            link_url_stripped = link
            if link.startswith("/"):
                link_url_stripped = page_url + link
            if link_url_stripped.endswith("#") or link_url_stripped.endswith("/"):
                link_url_stripped = link_url_stripped[:-1]

            if not self._should_include_link(link_url_stripped, page_domain, page_url, \
                                             log):
                continue
            return_links.add(link_url_stripped)
        return list(return_links)

    def get_links(self, page : Page, log = print, selection : int = 5):
        """
        Get the inner links of the page.
        Returns the first "selection" links classified as login, signup and neither.
        """
        start_time = time.time()
        page.evaluate("() => {window.scrollTo(0, 0);}")

        page_url = page.url.lower()
        page_domain = tld.get_fld(page_url, fail_silently=True)
        login_links = page.evaluate(\
            "() => getLinksFiltered(loginActionRegexPattern, loginRegexPattern)")
        login_links = self._control_links(login_links, page_url, page_domain, log)

        signup_links = page.evaluate(\
            "() => getLinksFiltered(registerActionRegex,registeRegexPattern)")
        signup_links = self._control_links(signup_links, page_url, page_domain, log)

        inner_links = page.evaluate(INNER_LINKS_QUERY)
        inner_links = self._control_links(inner_links, page_url, page_domain, log)
        # inner_links_not_in_login_signup = \
        #     [link for link in inner_links if \
        #     (link not in login_links and link not in signup_links)]

        self._links = login_links[0:selection] + signup_links[0:selection] # + \
            # inner_links_not_in_login_signup[0:selection]

        duration = time.time() - start_time
        # log(f"🔗 Found {len(self._links)} links on {page.url}")
        # log(f"🔗 get_links took {duration:0.1f} s on {page.url}")
        log(f"🔗 get_links found {len(self._links)} links in {duration:0.1f} s on {page.url}")

        return self._links

    def _arg_max(self, given_list : list):
        """
        Return the index of the largest value in a list.
        """
        # print(given_list)
        return given_list.index(max(given_list))

    def _predict_page_type(self, page_signals):
        """
        Use the ML model to predict if the given signals indicate a login or signup page.
        """
        result = {"isLogin": False, "isSignup": False, "url": ""}
        prediction_result = self._model.signatures["serving_default"](\
            tf.convert_to_tensor([page_signals], dtype=np.float32))
        res_arg_max = self._arg_max(prediction_result["Identity"].numpy().tolist()[0])
        # print(res_arg_max)
        if res_arg_max == 1:
            result["isLogin"] = True
        elif res_arg_max == 2:
            result["isSignup"] = True
        return result

    def _combine_page_frame_signals(self, page_frame_signals):
        """
        Combine the signals from the page and all frames to one flattened list.
        """
        combined_signals = [0]*88
        for each_signals in page_frame_signals:
            for j in range(len(each_signals)):
                if each_signals[j] is True:
                    combined_signals[j] = 1

        return combined_signals

    def _get_page_signals(self, page : Page, log = print):
        """
        Get the required signals for the ML model from the page and its frames.
        """
        signals_from_page_and_frames = []
        page_signals = page.evaluate("() => getSignalsAndConvertToBinary()")
        signals_from_page_and_frames.append(page_signals)
        frames = helpers.dump_frame_tree(page.main_frame)
        log(f"🔗 Received signals from page with {len(frames)} frames: {page.url}")
        for frame in frames:
            try:
                frame_url = frame.url
                frame_name = frame.name
                # just for logging
                # frame_identifier = f"{frame_name[:N_URL_CHARS_TO_LOG]} {frame_url[:N_URL_CHARS_TO_LOG]}" # frame name seems to contain dicts, html or other things
                frame_identifier = f"Frame url: {frame_url[:N_URL_CHARS_TO_LOG]}, Frame name empty: {frame_name == ''}"
                # log(f"Frame url: {frame_url}")
                # log(f"Frame name: {frame_name}")

                if  "chrome-error://" in frame_url:  # GA: should we use startswith?
                    log(f"🔗 _get_page_signals: chrome-error:// {frame_identifier}")
                    continue
                # if frame_name == "" or frame_url == "":
                if frame_name == "" and frame_url == "":
                    log(f"🔗 _get_page_signals: Likely detached frame with no name and URL. Skipping... {frame}")
                    continue
                log(f"🔗 Getting signals from frame {frame_identifier}")
                frame_signals = frame.evaluate("() => getSignalsAndConvertToBinary()")
                signals_from_page_and_frames.append(frame_signals)
            except Exception as e:
                if hasattr(e, 'message') and "Frame.evaluate: Frame was detached" in e.message:
                    log(f"🔗 LoginSignupSignalsCollector: Frame was detached on {page.url}")
                else:
                    log("❌ LoginSignupSignalsCollector:" + \
                        f" Error while getting signals on {page.url}: {e}")

        combined_signals = self._combine_page_frame_signals(signals_from_page_and_frames)
        return combined_signals

    def get_prediction_result(self, page : Page, log = print):
        """
        Get the prediction result of the given page, indicating whether it is
        a login page, signup page or neither.
        """
        try:
            start_time = time.time()
            page_signals = self._get_page_signals(page, log)
            prediction_result = self._predict_page_type(page_signals)
            page_url = page.url

            end_time = time.time()
            log(f"🔗 get_prediction_result took {end_time-start_time:0.1f}" + \
                f" s on {page.url}")
            if prediction_result.get("isLogin"):
                log(f"🔗 Found login page ⭐: {page_url}")
                return True
            elif prediction_result.get("isSignup"):
                log(f"🔗 Found signup page ⭐: {page_url}")
                return True
            else:
                return False
        except Exception as e:
            log(f"❌🔗 get_prediction_result failed due to error: {e}")
            return False


    def get_login_signup_page_collector_data(self, page : Page, log = print):
        """
        Get the urls of the first page or inner link to contain a login form
        and the first to contain a signup form.
        """
        start_time = time.time()
        login_signup_page_url_details = {"loginUrl": "", "signupUrl": ""}
        page_signals = self._get_page_signals(page, log)
        prediction_result = self._predict_page_type(page_signals)
        page_url = page.url

        if prediction_result.get("isLogin"):
            log(f"🔗 Found login page: {page_url}")
            login_signup_page_url_details["loginUrl"] = page_url
        elif prediction_result.get("isSignup"):
            log(f"🔗 Found signup page: {page_url}")
            login_signup_page_url_details["signupUrl"] = page_url

        if login_signup_page_url_details.get("loginUrl") != "" and \
                login_signup_page_url_details.get("signupUrl") != "":
            return login_signup_page_url_details

        log(f"🔗 Getting links from {page_url}")
        links = self.get_links(page, log)

        log("🔗 Did not find login and signup page on the landing page, "+\
                  "will try to find from links")
        # return login_signup_page_url_details
        for link in links:
            log(f"Navigating to {link}")
            page.goto(link)
            page.wait_for_timeout(2500)
            page_url = page.url

            page_signals = self._get_page_signals(page, log)
            prediction_result = self._predict_page_type(page_signals)

            if login_signup_page_url_details.get("loginUrl") == "" and \
                    prediction_result.get("isLogin"):
                log(f"Found login page: {page_url}")
                login_signup_page_url_details["loginUrl"] = page_url
            elif login_signup_page_url_details.get("signupUrl") == "" and \
                    prediction_result.get("isSignup"):
                log(f"Found signup page: {page_url}")
                login_signup_page_url_details["signupUrl"] = page_url

            if login_signup_page_url_details.get("loginUrl") != "" and \
                    login_signup_page_url_details.get("signupUrl") != "":
                break

        end_time = time.time()
        log("🔗 get_login_signup_page_collector_data took "+\
               f"{end_time-start_time:0.1f} s")
        return login_signup_page_url_details
