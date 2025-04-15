"""
Module to intercept websocket frames on a given page,
as playwright .har recording does not record these.
"""
import argparse
import os
import sys
import time

from playwright.sync_api import sync_playwright, Page, WebSocket

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# import helpers

class WebsocketCollector:
    """
    Module to intercept websocket frames on a given page,
    as playwright .har recording does not record these.
    """
    def __init__(self, page : Page, url : str, log = print):
        self._log = log
        self.url = url

        self.collected_requests = {"sent": [], "received": []}
        page.on("websocket", self.handle_websocket)

    def handle_websocket(self, websocket : WebSocket):
        """
        Handle the creation of websockets.
        """
        self._log(f"✉️ Websocket created on {self.url}")
        url = websocket.url
        websocket.on("framesent", lambda params : \
                     self.handle_websocket_frame_sent(params, websocket_url=url))
        websocket.on("framereceived", lambda params : \
                     self.handle_websocket_frame_received(params, websocket_url=url))

    def handle_websocket_frame_sent(self, params, websocket_url : str):
        """
        Handle the sending of websocket frames.
        """
        self._log(f"✉️ Websocket frame sent on {self.url} from: {websocket_url}")
        data = {"url": websocket_url, "wallTime": time.time(), "postData":params}
        self.collected_requests["sent"].append(data)

    def handle_websocket_frame_received(self, params, websocket_url : str):
        """
        Handle the receiving of websocket frames.
        """
        self._log(f"✉️ Websocket frame received on {self.url} from: {websocket_url}")
        data = {"url": websocket_url, "wallTime": time.time(), "postData":params}
        self.collected_requests["received"].append(data)

    def get_websocket_collector_data(self):
        """
        Return the collected requests.
        """
        return self.collected_requests
