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

# Convert seconds to text.
# Sample: May 31, 2017 at 9:59 AM.
def parse_time_point(seconds_since_epoch):
    # https://stackoverflow.com/questions/12400256/python-converting-epoch-time-into-the-datetime
    # http://strftime.org/
    return time.strftime("%b %-d, %Y at %-I:%M %p", time.gmtime(int(seconds_since_epoch)))

# Format the specified review.
# Sample:
# ★★★★☆ May 31, 2017 at 9:59 AM
# this is my comment
# by This_is_my_name · 1111 (1.0.1) · England
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

    # Samnple
    # Reserved symbols: 👍👎 ·
    text_lines = []
    text_lines.append('%s _%s_' % (parse_stars(star_rating), parse_time_point(last_modified)))
    text_lines.append('%s' % text)

    last_line_args = []

    # Author name.
    if len(author_name) > 0:
        last_line_args.append('_by %s_' % author_name)

    # Country name.
    last_line_args.append('%s' % country_name)

    # App version code and version name.
    if app_version_name != None:
        last_line_args.append('v%s (%s)' % (app_version_name, app_version_code))

    text_lines.append('%s' % u' · '.join(last_line_args))
    return '\n'.join(text_lines)

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
            print json.dumps(params, indent=4)

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

            response = {}

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
                        attachment = {}
                        attachment['text'] = format_review(review)
                        attachment['mrkdwn_in'] = ['text']
                        attachments.append(attachment)

                    response['attachments'] = attachments

            response['response_type'] = 'in_channel'

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