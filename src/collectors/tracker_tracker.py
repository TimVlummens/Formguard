"""
TrackerTracker used to handle the parsing and registering of breakpoints for api calls.
Based on https://github.com/leaky-forms/leaky-forms-crawler/blob/a8ecdab3bdc10fbd3f6aa8814a9c1100daafbd1d/collectors/APICalls/TrackerTracker.js
"""
import re
import json
# from urllib.parse import urlsplit
from playwright.sync_api import CDPSession

MAX_ASYNC_CALL_STACK_DEPTH = 32
STACK_SOURCE_REGEX = re.compile(r'\((https?:\/\/.*?):[0-9]+:[0-9]+\)', re.IGNORECASE)

ALL_BREAKPOINTS = [{
        "proto": 'Document',
        "props": [
            {"name": 'cookie', "description": 'Document.cookie getter'},
            {"name": 'cookie', "description": 'Document.cookie setter', "setter": True, "saveArguments": True}
        ],
        "methods": [
            {"name": 'interestCohort'}
        ]
        },{
        "proto": 'HTMLInputElement',
        "props": [
            {
                "name": 'value',
                "description": 'Input element value',
            }
        ],
        "methods": []
    }]

INPUT_BREAKPOINT = [{
        "proto": 'HTMLInputElement',
        "props": [
            {
                "name": 'value',
                "description": 'Input element value',
            }
        ],
        "methods": []
    }]

class TrackerTracker:
    """
    TrackerTracker used to handle the parsing and registering of breakpoints for api calls.
    """
    _cdp_session : CDPSession = None
    _main_url : str

    def __init__(self, cdp_session : CDPSession, args : dict, log = print):
        self._cdp_session = cdp_session
        self._log = log
        self._log("⚙️ TrackerTracker initiated")

        self._cdp_session.send('Debugger.enable')
        self._cdp_session.send('Runtime.enable')
        self._cdp_session.send('Runtime.setAsyncCallStackDepth', \
                               {"maxDepth": MAX_ASYNC_CALL_STACK_DEPTH})

        if args["record_full"]:
            self.all_breakpoints = ALL_BREAKPOINTS
        else:
            self.all_breakpoints = INPUT_BREAKPOINT

    def send_command(self, command : str, payload : dict = {}):
        """
        Send the specified command using the cdp session from this tracker tracker
        """
        try:
            return self._cdp_session.send(command, payload)
        except Exception as e:
            # self._log(\
            #     f"⚙️ Unable to send command {command} with payload {payload} due to error: {e}")
            return None

    def set_main_url(self, url : str):
        """
        Set the main url of this tracker tracker to the specified url.
        This is used as a default value.
        """
        self._main_url = url

    def _add_breakpoint(self, expression : str, condition : str, description : str, \
                        context_id, save_arguments : bool):
        """
        Construct the condition script and command to register a breakpoint.
        """
        try:
            # self._log("\n add breakpoint \n")
            result = self.send_command("Runtime.evaluate", \
                        {"expression": expression, "contextId": context_id, "silent": True})

            if result is None or result.get("exceptionDetails"):
                # raise Exception("API unavailable in given context.")
                # self._log(f"⚙️ API unavailable in given context on {self._main_url}")
                return

            condition_script = (""
                "const data = {\n"
                f"description: '{description}',\n"
                "stack: (new Error()).stack,\n"
                "timestamp: Date.now(),\n"
                "details: (\n"
                    "(this.tagName && this.tagName.toUpperCase() === 'INPUT') && \n"
                    "['text', 'email', 'password'].includes(this.type)) ? {\n"
                    "id: this.id,\n"
                    "type: this.type,\n"
                    "value: this.value,\n"
                    # "formAction: this.form.action,\n"
                    "baseURI: this.baseURI,\n"
                    "timestamp: Date.now(),\n"
                    "} : {},\n"
                "};\n"
            "")

            if save_arguments:
                condition_script += "data.args = Array.from(arguments).map(a => a.toString());"

            condition_script += ("window.registerAPICall(JSON.stringify(data));\n"
                "//console.log('call');"
                "false;")

            if condition:
                condition_script = (""
                    f"if (!!({condition})) {{"
                        f"{condition_script}"
                    "}")

            # self._log(condition_script)

            # self._log(result.get("result").get("objectId"))
            self.send_command("Debugger.setBreakpointOnFunctionCall", { \
                "objectId": result.get("result").get("objectId"), \
                "condition": condition_script \
                })

        except Exception as e:
            # self._log("Error occured: ", e)
            pass

    def _process_prop(self, prop, obj, context_id):
        try:
            if prop.get("setter") is True:
                setter = "set"
            else:
                setter = "get"
            expression = f"Reflect.getOwnPropertyDescriptor({obj}, '{prop.get('name')}').{setter}"

            if prop.get("description"):
                description = prop.get("description")
            else:
                description = f"{obj}.{prop.get('name')}"

            self._add_breakpoint(expression, prop.get("condition"), description, context_id, \
                                bool(prop.get("saveArguments")))
        except:
            return

    def _process_method(self, method, obj, context_id):
        try:
            expression = f"Reflect.getOwnPropertyDescriptor({obj}, '{method.get('name')}').value"

            if method.get("description"):
                description = method.get("description")
            else:
                description = f"{obj}.{method.get('name')}"

            self._add_breakpoint(expression, method.get("condition"), description, context_id, \
                                bool(method.get("saveArguments")))
        except:
            return

    def _process_breakpoint(self, processed_breakpoint, context_id):
        try:
            if processed_breakpoint.get("global"):
                obj = processed_breakpoint["global"]
            else:
                obj = f"{processed_breakpoint['proto']}.prototype"

            for prop in processed_breakpoint["props"]:
                self._process_prop(prop, obj, context_id)
            for method in processed_breakpoint["methods"]:
                self._process_method(method, obj, context_id)
        except Exception as e:
            # self._log(f"⚙️ Unable to set up API breakpoint in tracker_tracker due to error: {e}")
            return

    def setup_context_tracking(self, context_id = None):
        """
        Setup the required breakpoints.
        """
        for processed_breakpoint in self.all_breakpoints:
            self._process_breakpoint(processed_breakpoint, context_id)

    def _get_script_url(self, stack):
        """
        Get the script url from the stack as the first url in the stack.
        """
        try:
            if not isinstance(stack, str):
                self._log('⚙️⚠️ stack is not a string')
                return None

            lines = stack.split('\n')

            for line in lines:
                line_data = re.findall(STACK_SOURCE_REGEX, line)
                if line_data:
                    return line_data[0]
        except:
            pass

        return None

    def _get_breakpoint_by_name(self, breakpoint_name):
        for processed_breakpoint in self.all_breakpoints:
            try:
                proto = processed_breakpoint.get("proto")
                global_val = processed_breakpoint.get("global")
                props = processed_breakpoint.get("props")
                methods = processed_breakpoint.get("methods")

                if global_val:
                    obj = global_val
                else:
                    obj = f"{proto}.prototype"
                matching_prop = None
                for prop in props:
                    if prop.get("description") and prop.get("description") == breakpoint_name:
                        matching_prop = prop
                        break
                    elif f"{obj}.{prop.get('name')}" == breakpoint_name:
                        matching_prop = prop
                        break

                if matching_prop:
                    return matching_prop

                matching_method = None
                for method in methods:
                    if method.get("description") and method.get("description") == breakpoint_name:
                        matching_method = method
                        break
                    elif f"{obj}.{method.get('name')}" == breakpoint_name:
                        matching_method = method
                        break

                if matching_method:
                    return matching_method
            except:
                pass

        return None

    def process_debugger_pause(self, params):
        """
        Handle the breakpoint that caused a pause.
        """
        payload = None
        is_global = False
        try:
            payload = json.loads(params.get("payload"))
        except Exception:
            self._log(f'⚙️ Invalid brakpoint payload {params.get("payload")}')
            return None

        # self._log(payload)
        # self._log(payload.get("description"))
        processed_breakpoint = self._get_breakpoint_by_name(payload.get("description"))
        script = self._get_script_url(payload.get("stack"))

        # try:
        #     # Should calculate absolute URL, look into further?
        #     url_obj = urlsplit(self._main_url + script)
        #     script = url_obj.geturl()
        #     self._log(script)
        # except Exception as e:
        #     self._log('⚠️ invalid source, assuming global', script)
        #     script = self._main_url

        if not script:
            self._log('⚙️⚠️ unknown source, assuming global')
            script = self._main_url
            is_global = True

        if not processed_breakpoint:
            self._log(f'️⚙️⚠️ unknown breakpoint {params}')
            return None

        # if payload.get("details").get("value") is not None and \
        #         payload.get("details").get("value") != "":
        #     self._log(payload.get("details").get("value"))

        return {
            "description": payload.get("description"),
            "saveArguments": processed_breakpoint.get("saveArguments"),
            "timestamp": payload.get("timestamp"),
            "arguments": payload.get("args"),
            "details": payload.get("details"),
            "stack": payload.get("stack"),
            "source": script,
            "global": is_global
        }

def get_all_script_urls(stack, log = print):
    """
    Get all script url from the stack.
    """
    try:
        if not isinstance(stack, str):
            log('⚙️⚠️ stack is not a string')
            return None

        lines = stack.split('\n')

        urls = set()
        for line in lines:
            line_data = re.findall(STACK_SOURCE_REGEX, line)
            if line_data:
                urls.add(line_data[0])
        return list(urls)
    except:
        return None

def _main():
    pass

if __name__ == "__main__":
    _main()
