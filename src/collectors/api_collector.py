"""
Class for collecting api calls of the HTMLInputElement type.
Based on https://github.com/leaky-forms/leaky-forms-crawler/blob/a8ecdab3bdc10fbd3f6aa8814a9c1100daafbd1d/collectors/APICallCollector.js
"""
import argparse
import os
import sys
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, CDPSession, Page

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tracker_tracker import TrackerTracker, get_all_script_urls # type: ignore
import form_finder # type: ignore
import helpers # type: ignore
# from . import form_interactor

SAVE_STACKTRACE_SCRIPT_URLS_ONLY = True

class ApiCollector:
    """
    Class for collecting api calls of the HTMLInputElement type.
    """

    def __init__(self, cdp_client : CDPSession, url : str, args : dict, log = print):
        """
        Initialize the collector by creating the TrackerTracker and subscribing to events.
        """
        try:
            tracker = TrackerTracker(cdp_client, args, log)
            tracker.set_main_url(url)

            self.stats = {}
            self.input_element_breakpoints = []
            self.calls = []

            self.args = args
            self._log = log

            cdp_client.on('Runtime.bindingCalled', \
                        lambda params : self.on_binding_called(tracker, params))
            cdp_client.send('Runtime.addBinding', {"name": 'registerAPICall'})
            cdp_client.on('Runtime.executionContextCreated', \
                        lambda params : self.on_execution_context_crated(tracker, \
                                                                         cdp_client, params))
        except Exception as e:
            log(f"❌⚙️ Unable to set up API collector due to error: {e}")

    def on_execution_context_crated(self, tracker : TrackerTracker, \
                                    _cdp_client : CDPSession, params):
        """
        Function called on Runtime.executionContextCreated event.
        Uses the TrackerTracker to set breakpoints on the required functions.
        """
        try:
            if not params.get("context"):
                return
            # self._log(params)
            if (not params.get("context").get("origin") or \
                    params.get("context").get("origin") == "://") \
                    and params.get("context").get("auxData").get("type") == "isolated":
                return

            tracker.setup_context_tracking(params.get("context").get("id"))
        except Exception as e:
            self._log(f"❌⚙️ Unable to set API breakpoint due to error: {e}")

    def on_binding_called(self, tracker : TrackerTracker, params):
        """
        Function called on Runtime.bindingCalled event.
        Handles the breakpoint for the api call and appends the required data for later collection.
        """
        try:
            new_breakpoint = tracker.process_debugger_pause(params)

            if new_breakpoint is not None and \
                    new_breakpoint.get("description") == "Input element value":
                value = new_breakpoint.get("details", {}).get("value", "")
                if self.args["record_full"] or value != "":
                    self.input_element_breakpoints.append(new_breakpoint)

            if new_breakpoint is not None and new_breakpoint.get("source") and \
                    new_breakpoint.get("description"):
                if new_breakpoint.get("source") in self.stats:
                    source_stats = self.stats.get(new_breakpoint.get("source"))
                else:
                    source_stats = {}

                count = 0

                if new_breakpoint.get("description") in source_stats:
                    count = source_stats.get(new_breakpoint.get("description"))

                source_stats[new_breakpoint.get("description")] = count + 1
                self.stats[new_breakpoint.get("source")] = source_stats

                if new_breakpoint.get("saveArguments"):
                    self.calls.append({
                        "source": new_breakpoint.get("source"),
                        "description": new_breakpoint.get("description"),
                        "arguments": new_breakpoint.get("arguments"),
                        "details": new_breakpoint.get("details"),
                        "timestamp": new_breakpoint.get("timestamp")
                    })
        except Exception as e:
            self._log(f"❌⚙️ Unable to handle API breakpoint due to error: {e}")

    def is_acceptable_url(self, url_string : str):
        """
        Checks if the given url string is a valid url.
        """
        url = None

        try:
            url = urlsplit(url_string)
        except:
            return False

        if url and url.scheme == "data":
            return False

        return True

    # def get_initiators_from_stack(self, stack):
    #     """
    #     Gets all initiators from the stack recursively.
    #     """
    #     current_initiators = []
    #     parent_initiators = []

    #     for frame in stack.get("callFrames"):
    #         if frame.get("url"):
    #             current_initiators.append(frame.get("url"))
    #         elif frame.get("fileName"):
    #             current_initiators.append(frame.get("fileName"))

    #     if stack.get("parent"):
    #         parent_initiators = get_initiators_from_stack(stack.get("parent"))

    #     return current_initiators + parent_initiators

    # def get_all_initiators(self, initiator):
    #     """
    #     Gets all initiators from the stack.
    #     """
    #     all_initiators = set()

    #     if not initiator:
    #         return all_initiators
    #     if initiator.get("url"):
    #         all_initiators.add(initiator.get("url"))
    #     if initiator.get("stack"):
    #         new_initiators = get_initiators_from_stack(initiator.get("stack"))
    #         all_initiators.update(new_initiators)

    #     return list(all_initiators)

    def convert_input_element_breakpoints(self):
        """
        Replace full stack traces with distinct script urls if the flag is set.
        """
        try:
            if not SAVE_STACKTRACE_SCRIPT_URLS_ONLY:
                return

            # new_input_element_breakpoints = []
            for new_breakpoint in self.input_element_breakpoints:
                new_breakpoint["scripts"] = get_all_script_urls(new_breakpoint["stack"], self._log)
        except:
            return

    def get_api_collector_data(self):
        """
        Return the collected data. Function should be called after all input interaction has
        finished. Can be called after closing the page.
        """
        try:
            call_stats = {}

            self.convert_input_element_breakpoints()

            for source, called in self.stats.items():
                if not self.is_acceptable_url(source):
                    continue

                call_stats[source] = called

            # self._log({"call_stats" : call_stats, "saved_calls" : \
            #       list(filter(lambda x : is_acceptable_url(x.get("source")), calls)), \
            #       "input_element_results" : input_element_breakpoints})
            return {"call_stats" : call_stats, "saved_calls" : \
                    list(filter(lambda x : self.is_acceptable_url(x.get("source")), self.calls)), \
                    "input_element_results" : self.input_element_breakpoints}
        except:
            return {"call_stats" : {}, "saved_calls" : [], "input_element_results" : []}

    def inject_own_value_readers(self, page : Page):
        """
        Inject a script into the site to add eventlisteners to all input fields
        so that they can be read out by the api_collector.
        """
        script = """
            () => {
                function queryAllDeep(root, selector) {
                    const arr = [];
                    const traverser = node => {
                        if (!node)
                            return;
                        // 1. decline all nodes that are not elements
                        if(node.nodeType !== Node.ELEMENT_NODE) return;

                        // 2. add the node to the array, if it matches the selector
                        if(node.matches(selector)) {
                            arr.push(node);
                        }

                        // 3. loop through the children
                        const children = node.children;
                        if (children.length) {
                            for(const child of children) {
                                traverser(child);
                            }
                        }
                        // 4. check for shadow DOM, and loop through it's children
                        const shadowRoot = node.shadowRoot;
                        if (shadowRoot) {
                            const shadowChildren = shadowRoot.children;
                            for(const shadowChild of shadowChildren) {
                                traverser(shadowChild);
                            }
                        }
                    }
                    traverser(root.body);
                    return arr;
                }
                      
                // Function to print the value of the updated input field
                const printUpdatedValue = (event) => {
                    const input = event.target;
                    console.log(`input_value: ${input.name || input.id}: ${input.value}`);
                };

                // Select all input fields
                const inputFields = queryAllDeep(document, 'input');

                // Listen for changes in input fields
                inputFields.forEach(input => {
                    input.addEventListener('input', printUpdatedValue);
                });
            }
        """

        frames = helpers.dump_frame_tree(page.main_frame)
        for frame in frames:
            frame.evaluate(script)
