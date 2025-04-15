"""
Class for collecting script scources.
"""
from playwright.sync_api import sync_playwright, CDPSession, Page
import helpers # type: ignore

class ScriptCollector:
    """
    Class for collecting script scources.
    """

    def __init__(self, cdp_client : CDPSession, args : dict, log = print):
        """
        Initialize the collector by creating the TrackerTracker and subscribing to events.
        """
        try:
            self.scripts = []
            self._log = log

            if args["record_full"]:
                cdp_client.send('Debugger.disable')
                cdp_client.on('Debugger.scriptParsed', lambda params : self.on_script_parsed(params))
                cdp_client.send('Debugger.enable')
            else:
                log("</> Will not record scripts.")
        except Exception as e:
            log(f"❌</> Unable to set up script collector due to error: {e}")

    def on_script_parsed(self, script_info : dict):
        """
        Save info about the parsed script.
        """
        try:
            # self.scripts.append({
            #     "scriptId": script_info.get("scriptId"),
            #     "url": script_info.get("url"),
            #     "startLine": script_info.get("startLine"),
            #     "startColumn": script_info.get("startColumn"),
            #     "endLine": script_info.get("endLine"),
            #     "endColumn": script_info.get("endColumn"),
            #     "executionContextId": script_info.get("executionContextId"),
            #     "hash": script_info.get("hash"),
            #     "executionContextAuxData": script_info.get("executionContextAuxData"),
            #     "isLiveEdit": script_info.get("isLiveEdit"),
            #     "sourceMapURL": script_info.get("sourceMapURL"),
            #     "hasSourceMapURL": script_info.get("hasSourceMapURL"),
            #     "isModule": script_info.get("isModule"),
            #     "length": script_info.get("length"),
            #     "stackTrace": script_info.get("stackTrace"),
            #     "codeOffset": script_info.get("codeOffset"),
            #     "scriptLanguage": script_info.get("scriptLanguage"),
            #     "debugSymbols": script_info.get("debugSymbols"),
            #     "embedderName": script_info.get("embedderName"),
            # })
            self.scripts.append(script_info)
        except Exception as e:
            self._log(f"❌</> Unable to parse script due to error: {e}")

    def get_scripts(self):
        """
        Return collected scripts.
        """
        return self.scripts
