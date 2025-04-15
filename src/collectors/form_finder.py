"""
Module to find input fields on a given page
"""
import os
import time
import sys
import re

from playwright.sync_api import sync_playwright, Page, Frame, Playwright, Locator

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import helpers

EMAILREGEX = re.compile(r'email|e-mail', re.IGNORECASE)
EMAILREGEXMATCHLINE = re.compile(r'^(email|e-mail)$', re.IGNORECASE)

"""
Queries the document and shadowRoot
Based on https://stackoverflow.com/a/71787772/5506400
"""
SHADOW_INPUT_SELECTOR = """
    {
        // Returns the first element matching given selector in the root's subtree.
        query(root, selector) {
            const arr = []
            const traverser = node => {
                if (arr.length) return;

                // 1. decline all nodes that are not elements
                if(node.nodeType !== Node.ELEMENT_NODE) return

                // 2. add the node to the array, if it matches the selector
                if(node.matches("input"+selector)) {
                    arr.push(node)
                    return;
                }

                // 3. loop through the children
                const children = node.children
                if (children.length) {
                    for(const child of children) {
                        traverser(child)
                    }
                }
                // 4. check for shadow DOM, and loop through it's children
                const shadowRoot = node.shadowRoot
                if (shadowRoot) {
                    const shadowChildren = shadowRoot.children
                    for(const shadowChild of shadowChildren) {
                        traverser(shadowChild)
                    }
                }
            }
            traverser(root)
            return arr.length ? arr[0] : null;
        },
        // Returns all elements matching given selector in the root's subtree.
        queryAll(root, selector) {
            const arr = []
            const traverser = node => {
                if (!node)
                    return
                // 1. decline all nodes that are not elements
                if(node.nodeType !== Node.ELEMENT_NODE) return

                // 2. add the node to the array, if it matches the selector
                // console.log("input"+selector)
                if(node.matches("input"+selector)) {
                    arr.push(node)
                }

                // 3. loop through the children
                const children = node.children
                if (children.length) {
                    for(const child of children) {
                        traverser(child)
                    }
                }
                // 4. check for shadow DOM, and loop through it's children
                const shadowRoot = node.shadowRoot
                if (shadowRoot) {
                    const shadowChildren = shadowRoot.children
                    for(const shadowChild of shadowChildren) {
                        traverser(shadowChild)
                    }
                }
            }
            traverser(root.body)
            return arr;
        }
    }"""

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))

FATHOM_COMPARE_SRC = f"{MODULE_DIR}/../inject/fathomCompare.js"

def register_selectors(pw):
    """
    Registers the custom selectors to be able to detect fields based on input types.
    """
    # selector searches for node.matches("input"+selector)
    pw.selectors.register("input", SHADOW_INPUT_SELECTOR)

class FormFinder:
    """
    Class to find input fields on a given page
    """

    def __init__(self, pw : Playwright, page : Page, args : dict, log = print):
        self.pw = pw
        self.args = args
        self._log = log

        self.inject_scripts(page)

    def inject_scripts(self, page : Page):
        """
        Inject script into page to block creation of closed shadow roots if required.
        """
        if self.args["pierce"]:
            helpers.block_closed_shadows(page)

        if self.args["mode"] == "compare_detection":
            page.add_init_script(path=FATHOM_COMPARE_SRC)

    def check_is_visible(self, locators : Locator):
        """
        Check if the given locator is visible, based on zero size, visibility:hidden and 
        display:none, being located irrecoverably of screen.
        """
        locator_list = []
        count = locators.count()

        for i in range(count):
            locator = locators.nth(i)
            # Checks for zero size, visibility:hidden and display:none
            if not locator.is_visible():
                continue
            # Playwrights bounding bow is relative to viewport instead of root origin
            bounding_box = locator.bounding_box()
            curr_height = locator.page.evaluate('(window.pageYOffset)')
            if (bounding_box['x'] + bounding_box['width'] < 0) or \
            (bounding_box['y'] + bounding_box['height'] + curr_height < 0):
                continue

            locator_list.append(locator)

        return locator_list

    def check_attributes_match(self, locators : list, attributes : list, regex):
        """
        Returns a list of locators for which at least one attribute of "attributes" match "regex".
        """
        locator_list = []

        for locator in locators:
            for attribute in attributes:
                locator_attribute = locator.get_attribute(attribute)
                # print(locator_attribute)
                if locator_attribute is  None:
                    continue

                matches = regex.search(locator_attribute)
                if matches is not None:
                    locator_list.append(locator)
                    break

        return locator_list

    def check_label_match(self, frame : Frame, locators : list, regex):
        """
        Returns a list of locators for which a label exists that matches the regex.
        """
        locator_list = []

        for locator in locators:
            if locator.and_(frame.get_by_label(regex)).count() != 0:
                locator_list.append(locator)

        return locator_list

    def check_input_value_match(self, locators : list, regex):
        """
        Returns a list of locators for which the input value matches the regex.
        """
        locator_list = []

        for locator in locators:
            value = locator.input_value()
            if value is  None:
                continue

            matches = regex.search(value)
            if matches is not None:
                locator_list.append(locator)

        return locator_list

    def get_password_fields(self, frame : Frame):
        """
        Find all password fields on a given frame by searching for inputs with the "password" type,
        with the option to (not) pierce closed shadow roots.
        Returns a list of locators pointing to each field.
        In debug mode, highlights all detected fields.
        """
        # selector searches for node.matches("input"+selector)
        locators = frame.locator("input=[type='password']")
        locator_list = []
        try:
            locator_list = self.check_is_visible(locators)
        except Exception as e:
            self._log(f"🔍 Frame password locators skipped on {frame.url} due to error: {e}")

        if self.args["debug"]:
            for locator in locator_list:
                locator.highlight()
                frame.wait_for_timeout(1000)

        return locator_list

    def get_email_fields_by_type(self, frame : Frame):
        """
        Find all email fields on a given frame by searching for inputs with the "email" type,
        with the option to (not) pierce closed shadow roots.
        Returns a list of locators pointing to each field.
        In debug mode, highlights all detected fields.
        """
        # selector searches for node.matches("input"+selector)
        locators = frame.locator("input=[type='email']")
        locator_list = []
        try:
            locator_list = self.check_is_visible(locators)
        except Exception as e:
            self._log(f"🔍 Frame email locators skipped on {frame.url} due to error: {e}")

        if self.args["debug"]:
            for locator in locator_list:
                locator.highlight()
                frame.wait_for_timeout(1000)

        return locator_list

    def get_email_fields_by_attributes(self, frame : Frame, include_value : bool = False):
        """
        Find all email fields on a given frame by searching for inputs which exhibit 
        email field-like attributes, with the option to (not) pierce closed shadow roots.
        Returns a list of locators pointing to each field.
        In debug mode, highlights all detected fields.
        """
        # selector searches for node.matches("input"+selector)
        locators_text = frame.locator("input=[type='text']")
        locators_empty = frame.locator("input=[type=\"\"]")
        locators_not = frame.locator("input=:not([type])")

        # Combine locators into a single locator
        locators = locators_text.or_(locators_empty).or_(locators_not)

        final_locators = set()
        try:
            locator_list = self.check_is_visible(locators)

            locator_list_identifier = \
            self.check_attributes_match(locator_list, ["id", "name", "autocomplete"], \
                                        EMAILREGEXMATCHLINE)
            # print(locator_list_identifier)
            locator_list_placeholder = \
                self.check_attributes_match(locator_list, ["placeholder", "aria-label"], EMAILREGEX)
            # print(locator_list_placeholder)
            locator_list_label = \
                self.check_label_match(frame, locator_list, EMAILREGEX)
            # print(locator_list_label)
            locator_list_value = []
            if include_value:
                locator_list_value = \
                    self.check_input_value_match(locator_list, EMAILREGEX)

            final_locators = \
                set(locator_list_identifier + locator_list_placeholder + locator_list_label + \
                    locator_list_value)
            # print(final_locators)
        except Exception as e:
            self._log(f"🔍 Frame attribute locators skipped on {frame.url} due to error: {e}")

        if self.args["debug"]:
            for locator in list(final_locators):
                locator.highlight()
                frame.wait_for_timeout(1000)

        return list(final_locators)

    def get_email_fields_from_fathom(self, frame : Frame, debug : bool = False):
        """
        Find all email fields using fathom. Returns a LIST of locators.
        """
        field_list = []
        try:
            field_xpaths_from_fathom = \
                frame.evaluate("() => [...fathom.detectEmailInputs(document)]")
            # print(len(field_xpaths_from_fathom))
            for field in field_xpaths_from_fathom:
                field_list.append(\
                    {"id": field["id"], "name": field["name"], "xpath": field["xpath"]})

        except Exception as e:
            self._log(f"🔍 Fathom skipped on {frame.url} due to error: {e}")

        return field_list

    def get_fillable_password_email_fields(self, page : Page):
        """
        Return all input fields for passwords and emails.
        """
        func_start_time = time.time()
        all_locators = {"password": [], "email": []}
        count = 0

        frames = helpers.dump_frame_tree(page.main_frame)

        for frame in frames:
            if frame.url == "":
                # https://github.com/microsoft/playwright/issues/8943
                # self._log(f"🔍 Frame skipped on {frame.url} due to empty url." + \
                #           f"Detached: {frame.is_detached()}, Frame name: {frame.name}" + \
                #           f" , page: {page.url}")
                self._log(f"🔍 Frame skipped on {frame.url} due to empty url." + \
                          f"Detached: {frame.is_detached()}, Frame name empty: {frame.name == ''}" + \
                          f" , page: {page.url}")
                continue
            # Passwords
            new_locators = self.get_password_fields(frame)
            all_locators["password"] += new_locators
            count += len(new_locators)
            # Emails by type
            new_locators = self.get_email_fields_by_type(frame)
            all_locators["email"] += new_locators
            count += len(new_locators)
            # Emails by attributes
            new_locators = self.get_email_fields_by_attributes(frame)
            all_locators["email"] += new_locators
            count += len(new_locators)

        func_duration = time.time() - func_start_time
        self._log(f"🔍 get_fillable_password_email_fields took {func_duration:0.1f}" + \
                  f" s on {page.url}")
        n_email = len(all_locators["email"])
        n_password = len(all_locators["password"])
        if n_email + n_password > 0:
            self._log(f"⭐ {n_email} email, {n_password} password fields were detected on {page.url}")
        else:
            self._log(f"🔍 No email or password fields were detected on {page.url}")
        return all_locators

    def get_attributes_from_fields(self, page : Page, locator_list : list):
        """
        Return the id's and names of the given locators.
        """
        fields = []
        for locator in locator_list:
            try:
                field = {"id": "", "name": "", "locator": str(locator)}
                field["id"] = locator.get_attribute("id")
                field["name"] = locator.get_attribute("name")
                fields.append(field)
            except Exception as e:
                self._log(f"🔍 Frame attributes skipped on {page.url} due to error: {e}")
        return fields

    def compare_detections(self, page):
        """
        Find all email fields on a given page using three methods.
        """
        fields_without_value = []
        fields_with_value = []
        fields_from_fathom = []
        fields_from_type = []
        frames = helpers.dump_frame_tree(page.main_frame)

        func_start_time = time.time()
        start_time = time.time()
        for frame in frames:
            if frame.url == "":
                # https://github.com/microsoft/playwright/issues/8943
                # self._log(f"🔍 Frame skipped on {frame.url} due to empty url." + \
                #           f"Detached: {frame.is_detached()}, Frame name: {frame.name}" + \
                #           f" , page: {page.url}")
                self._log(f"🔍 Frame skipped on {frame.url} due to empty url." + \
                          f"Detached: {frame.is_detached()}, Frame name empty: {frame.name == ''}" + \
                          f" , page: {page.url}")
                continue
            fields_without_value += self.get_attributes_from_fields(page, \
                self.get_email_fields_by_attributes(frame, False))
        without_time = time.time() - start_time
        start_time = time.time()
        for frame in frames:
            if frame.url == "":
                # https://github.com/microsoft/playwright/issues/8943
                # self._log(f"🔍 Frame skipped on {frame.url} due to empty url." + \
                #           f"Detached: {frame.is_detached()}, Frame name: {frame.name}" + \
                #           f" , page: {page.url}")
                self._log(f"🔍 Frame skipped on {frame.url} due to empty url." + \
                          f"Detached: {frame.is_detached()}, Frame name empty: {frame.name == ''}" + \
                          f" , page: {page.url}")
                continue
            fields_with_value += self.get_attributes_from_fields(page, \
                self.get_email_fields_by_attributes(frame, True))
        with_time = time.time() - start_time
        start_time = time.time()
        for frame in frames:
            if frame.url == "":
                # https://github.com/microsoft/playwright/issues/8943
                # self._log(f"🔍 Frame skipped on {frame.url} due to empty url." + \
                #           f"Detached: {frame.is_detached()}, Frame name: {frame.name}" + \
                #           f" , page: {page.url}")
                self._log(f"🔍 Frame skipped on {frame.url} due to empty url." + \
                          f"Detached: {frame.is_detached()}, Frame name empty: {frame.name == ''}" + \
                          f" , page: {page.url}")
                continue
            fields_from_fathom += self.get_email_fields_from_fathom(frame)
        fathom_time = time.time() - start_time
        for frame in frames:
            if frame.url == "":
                # https://github.com/microsoft/playwright/issues/8943
                # self._log(f"🔍 Frame skipped on {frame.url} due to empty url." + \
                #           f"Detached: {frame.is_detached()}, Frame name: {frame.name}" + \
                #           f" , page: {page.url}")
                self._log(f"🔍 Frame skipped on {frame.url} due to empty url." + \
                          f"Detached: {frame.is_detached()}, Frame name empty: {frame.name == ''}" + \
                          f" , page: {page.url}")
                continue
            fields_from_type += self.get_attributes_from_fields(page, \
                self.get_email_fields_by_type(frame))

        func_end_time = time.time()
        self._log(f"🔍 compare_detections took {func_end_time-func_start_time:0.1f}" + \
                  f" s on {page.url}")
        self._log(f"🔍 {[len(fields_from_fathom), len(fields_without_value), len(fields_with_value)]}"\
                  + f"fields detected on {page.url}")

        comparison = ""
        if len(fields_without_value) < len(fields_from_fathom):
            comparison = "less"
        elif len(fields_without_value) == len(fields_from_fathom):
            comparison = "equal"
        else:
            comparison = "more"

        data = {"comparison": comparison,
                "count_fields_without_value": len(fields_without_value),
                "count_fields_with_value": len(fields_with_value),
                "count_fields_from_fathom": len(fields_from_fathom),
                "count_fields_from_type": len(fields_from_type),
                "fields_without_value": fields_without_value,
                "fields_with_value": fields_with_value,
                "fields_from_fathom": fields_from_fathom,
                "time_fields_without_value": without_time,
                "time_fields_with_value": with_time,
                "time_fields_from_fathom": fathom_time,
                "fields_from_type": fields_from_type
                }

        return data
