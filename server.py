# !/usr/bin/env python
# coding: utf8

import contextlib
import logging
import requests
import socket
import SocketServer
import sys
import threading
import json
import BaseHTTPServer
import urllib
import urllib2
import urlparse
import httplib2
import oauth2client.service_account
import apiclient.discovery
import time
import pycountry
import random

HTTP_PORT = 52000
JSON_FILE = 'HAI-Google Play Android Developer-ec4b6d35d5b1.json'

# Converts from star count to text.
def parse_stars(star_count):
    stars = {}
    stars[1] = u'★☆☆☆☆'
    stars[2] = u'★★☆☆☆'
    stars[3] = u'★★★☆☆'
    stars[4] = u'★★★★☆'
    stars[5] = u'★★★★★'
    return stars[star_count]

def color_for_stars(star_count):
    colors = {}
    colors[1] = '#ffdddd'
    colors[2] = '#eebbbb'
    colors[3] = '#dd8888'
    colors[4] = '#cc4444'
    colors[5] = '#880000'
    return colors[star_count]

# Convert seconds to text.
# Sample: May 31, 2017 at 9:59 AM.
def parse_time_point(seconds_since_epoch):
    # https://stackoverflow.com/questions/12400256/python-converting-epoch-time-into-the-datetime
    # http://strftime.org/
    return time.strftime("%b %-d, %Y at %-I:%M %p", time.gmtime(int(seconds_since_epoch)))

# Format the specified review.
# Sample:
# Author · Viet Name
# ★★★★☆
# this is my comment
# v1.0.1 (1111) | May 31, 2017 at 9:59 AM
def format_review(review):
    author_name         = review['authorName']
    review_id           = review['reviewId']
    user_comment        = review['comments'][0]['userComment']
    app_version_code    = user_comment.get('appVersionCode', None)
    app_version_name    = user_comment.get('appVersionName', None)
    reviewer_language   = user_comment['reviewerLanguage']
    text                = user_comment['text']
    thumbs_up_count     = user_comment['thumbsUpCount']
    thumbs_down_count   = user_comment['thumbsDownCount']
    star_rating         = user_comment['starRating']
    last_modified       = user_comment['lastModified']['seconds']

    language_code, country_code = reviewer_language.split('_')
    country_name = pycountry.countries.get(alpha_2=country_code).name

    attachment = {}

    # Color.
    # color = '#{:06x}'.format(random.randint(0x000000, 0xffffff))
    color = color_for_stars(star_rating)

    # Reserved symbols: 👍👎 ·
    attachment['author_name']   = u'%s · %s' % (author_name, country_name)
    attachment['title']         = parse_stars(star_rating)
    attachment['text']          = text
    attachment['ts']            = last_modified
    attachment['color']         = color
    attachment['mrkdwn_in']     = 'text'

    # Unique callback id.
    attachment['callback_id']   = review_id

    # App version code and version name.
    if app_version_name != None:
        attachment['footer'] = 'v%s (%s)' % (app_version_name, app_version_code)

    # Buttons.
    actions = []

    # Translate (to English) button.
    translate_button = {}
    translate_button['name'] = 'translate'
    translate_button['text'] = 'Translate to English'
    translate_button['type'] = 'button'

    # Reply button.
    reply_button = {}
    reply_button['name'] = 'reply'
    reply_button['text'] = 'Reply'
    reply_button['type'] = 'select'
    reply_button['data_source'] = 'external'
    reply_button['min_query_length'] = 2

    attachment['actions'] = [translate_button, reply_button]

    return attachment

def handle_message_button(params, response, service):
    original_message = params['original_message']

    callback_id     = params['callback_id']
    response_url    = params['response_url']

def handle_message_menu(params, response, service):
    # Input value.
    value = params['value']
    response['options'] = []

    # Echo the value.
    response['options'].append({
        'text' : value,
        'value' : 'input'
    })

def handle_command(params, response, service):
    user_id         = params['user_id']
    channel_id      = params['channel_id']
    text            = params['text']
    response_url    = params['response_url']
    team_id         = params['team_id']
    channel_name    = params['channel_name']
    token           = params['token']
    command         = params['command']
    team_domain     = params['team_domain']
    user_name       = params['user_name']

    if command == '/reviews':
        reviews_resources = service.reviews()
        try:
            reviews_page = reviews_resources.list(
                packageName=text, 
                maxResults=5
            ).execute()
        except Exception as e:
            reviews_page = None
            response['text'] = str(e)

        print json.dumps(reviews_page, indent=4)

        if not reviews_page is None:
            attachments = []
            reviews = reviews_page['reviews']
            for review in reviews:
                attachment = format_review(review)
                attachments.append(attachment)

            response['attachments'] = attachments

# https://gist.github.com/bradmontgomery/2219997
# https://stackoverflow.com/questions/21631799/how-can-i-pass-parameters-to-a-requesthandler
def MakeHandlerClass(service):
    class MyHandler(BaseHTTPServer.BaseHTTPRequestHandler, object):
        def __init__(self, *args, **kwargs):
            self.service = service
            super(MyHandler, self).__init__(*args, **kwargs)

        def _set_headers(self):
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()

        def do_GET(self):
            print 'do_GET'
            self._set_headers()

        def do_HEAD(self):
            print 'do_HEAD'
            self._set_headers()

        def do_POST(self):
            print 'do_POST'
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            print 'length = %d' % content_length
            decoded_data = urllib.unquote(post_data).decode('utf8')
            params = dict(urlparse.parse_qsl(decoded_data))

            response = {}
            # response['response_type'] = 'in_channel'

            payload = params.get('payload')
            if payload != None:
                # Button.
                print 'Button type'
                payload_dict = json.loads(payload)
                print json.dumps(payload_dict, indent=4)

                original_message = payload_dict.get('original_message')
                if original_message == None:
                    print 'Message menu type'
                    # Message menu.
                    handle_message_menu(payload_dict, response, service)
                    
                else:
                    print 'Message button type'
                    # Message button or an option in message menu was selected.
                    handle_message_button(payload_dict, response, service)
            else:
                print 'Command type'
                print json.dumps(params, indent=4) 
                # Command.
                handle_command(params, response, service)

            print 'response = %s' % json.dumps(response, indent=4)

            self._set_headers()
            self.wfile.write(json.dumps(response))
            return

    return MyHandler

# # https://stackoverflow.com/questions/11348025/api-to-get-android-google-play-reviewsgetting-device-name-and-app-version
def connect_google_client():
    credentials = oauth2client.service_account.ServiceAccountCredentials.from_json_keyfile_name(
        JSON_FILE, scopes=['https://www.googleapis.com/auth/androidpublisher'])
    service = apiclient.discovery.build('androidpublisher', 'v2', http=credentials.authorize(httplib2.Http()))
    return service

def run_server(service):
    try:
        server = BaseHTTPServer.HTTPServer(('', HTTP_PORT), MakeHandlerClass(service))
        print 'Started HTTP server on port %s' % HTTP_PORT

        server.serve_forever()
    except KeyboardInterrupt:
        print '^C received, shutting down the web server'
        pass
    server.server_close()

if __name__ == '__main__':
    service = connect_google_client()
    run_server(service)