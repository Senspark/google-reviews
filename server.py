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
import HTMLParser

HTTP_PORT = 52000
JSON_FILE = 'HAI-Google Play Android Developer-ec4b6d35d5b1.json'

# Gets the Google Play Store app link.
# @param package_name The package name of the application.
# @return The URL link to store.
def get_store_link(package_name):
    return 'https://play.google.com/store/apps/details?id=%s' % package_name

# Attempts to read the HTML source.
# @param url The URL to the source.
# @return HTML source.
def read_source(url):
    return urllib.urlopen(url).read()

# Gets the cover image URL within the HTML source.
# @param source The HTML source.
# @return Cover image URL.
def get_cover_image_url(source):
    i = source.find('"cover-image" src="')
    if i == -1:
        return None

    # Skip to the first ".
    i += 19

    j = source.find('"', i)
    if j == -1:
        return None

    # Skip =w300
    j -= 4

    # Substring.
    result = source[i:j]

    # Add `https:`
    # Add `=w16`: indicate 16x16 pixels resolution.
    result = 'https:%sw16' % result
    return result

# Converts from star count to text.
# @param star_count The number of stars
# @return String.
def parse_stars(star_count):
    stars = {}
    stars[1] = u'★☆☆☆☆'
    stars[2] = u'★★☆☆☆'
    stars[3] = u'★★★☆☆'
    stars[4] = u'★★★★☆'
    stars[5] = u'★★★★★'
    return stars[star_count]

# Converts from star count to color.
# @param star_count The number of stars.
# @return Color in hex format.
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

# https://developers.google.com/android-publisher/api-ref/reviews/reply
# https://developers.google.com/apis-explorer/#p/androidpublisher/v2/androidpublisher.reviews.reply
# @param package_name The application package name.
# @param review_id The ID of the review.
# @param reply_text The comment.
def reply_review(service, package_name, review_id, reply_text):
    service.reviews().reply(
        packageName=package_name,
        reviewId=review_id,
        body={'replyText': reply_text}
    ).execute()

# Format the specified review.
# Sample:
# Author · Viet Name
# ★★★★☆
# this is my comment
# v1.0.1 (1111) | May 31, 2017 at 9:59 AM
# @param review The review information retrieved from androidpublisher.
# @return A formatted dictionary.
def format_user_review(review, package_name):
    author_name         = review['authorName']
    review_id           = review['reviewId']
    user_comment        = review['comments'][0]['userComment']
    app_version_code    = user_comment.get('appVersionCode', None)
    app_version_name    = user_comment.get('appVersionName', None)
    reviewer_language   = user_comment['reviewerLanguage']
    last_modified       = user_comment['lastModified']['seconds']

    star_rating = get_star_rating(review)

    language_code, country_code = reviewer_language.split('_')
    country_name = pycountry.countries.get(alpha_2=country_code).name

    attachment = {}

    # Color.
    color = color_for_stars(star_rating)

    attachment['title']         = parse_stars(star_rating)
    attachment['text']          = get_user_comment(review)
    attachment['ts']            = last_modified
    attachment['color']         = color
    attachment['mrkdwn_in']     = ['text']

    # Callback ID contains both package name and review ID.
    attachment['callback_id']   = '%s|%s' % (package_name, review_id)

    # Header.
    author_texts = []

    # User's name.
    if len(author_name) > 0:
        author_texts.append(author_name)

    # User's country.
    author_texts.append(country_name)

    attachment['author_name'] = u' · '.join(author_texts)

    # Footer.
    footer_texts = []

    # Package name.
    footer_texts.append(package_name)

    # App version code and version name.    
    if app_version_name != None:
        footer_texts.append('v%s (%s)' % (app_version_name, app_version_code))

    attachment['footer'] = u' · '.join(footer_texts)

    # Buttons.
    attachment['actions'] = []

    return attachment

def format_developer_comment(review):
    comments            = review['comments']
    comment_count = len(comments)
    if comment_count < 2:
        return None

    developer_comment   = comments[1]['developerComment']
    text                = developer_comment['text']
    last_modified       = developer_comment['lastModified']['seconds']

    star_rating = get_star_rating(review)

    attachment = {}
    attachment['text']      = '*Reply*: %s' % text
    attachment['ts']        = last_modified
    attachment['color']     = color_for_stars(star_rating)
    attachment['mrkdwn_in'] = ['text']

    return attachment

def get_user_comment(review):
    return review['comments'][0]['userComment']['text']

def get_star_rating(review):
    return review['comments'][0]['userComment']['starRating']

def add_translate_button(attachment):
    # Translate (to English) button.
    translate_button = {}
    translate_button['name'] = 'translate'
    translate_button['text'] = 'Translate to English'
    translate_button['type'] = 'button'

    attachment['actions'].append(translate_button)

def remove_translate_button(attachment):
    attachment['actions'] = [action for action in attachment['actions'] if action['name'] != 'translate']

def add_reply_button(attachment):
    reply_button = {}
    reply_button['name'] = 'reply'
    reply_button['text'] = 'Reply'
    reply_button['type'] = 'select'
    reply_button['data_source'] = 'external'
    reply_button['min_query_length'] = 2

    attachment['actions'].append(reply_button)

def handle_message_button(params, response, service):
    original_message    = params['original_message']
    attachment_id       = params['attachment_id']
    callback_id         = params['callback_id']
    response_url        = params['response_url']
    actions             = params['actions']

    package_name, review_id = callback_id.split('|')

    action              = actions[0]
    action_type         = action['type']
    action_name         = action['name']

    if action_type == 'button':
        action_value = action['value']
    elif action_type == 'select':
        action_value = action['selected_options'][0]['value']

    if action_name == 'translate':
        # Translate button.
        review = service.reviews().get(
            packageName=package_name, 
            reviewId=review_id,
            translationLanguage='en_US'
        ).execute()

        translated_text = get_user_comment(review)

        attachments = []
        for original_attachment in original_message['attachments']:
            if str(original_attachment['id']) == attachment_id:
                original_attachment['text'] += '\n*Translated*: %s' % translated_text
                remove_translate_button(original_attachment)
            attachments.append(original_attachment)

        response['attachments'] = attachments

    elif action_name == 'reply':
        reply_text = action_value
        reply_review(service, package_name, review_id, reply_text)
    else:
        assert(False)

    # Replace the old message.
    response['replace_original'] = True

def handle_message_menu(params, response, service):
    # Input value.
    value = params['value']
    response['options'] = []

    # Echo the value.
    response['options'].append({
        'text' : value,
        'value' : value
    })

    # Pre-defined replies are not useful (can not see all lines).
    return

    # Pre-defined replies.
    # https://docs.google.com/document/d/1pVQTriN4YoybD3T7xegmvjY9vgqar8ivP2BvyHQshg4/edit?ts=5677c503

    # Dùng cho: Phàn nàn về game lỗi hay ko hài lòng về hiệu năng.
    # Usage: Complains about game bugs or Dissatisfaction.
    response['options'].append({
        'text' : (
            'Thanks for your feedback!'
            '\n'
            'Please give us more details of your dissatisfaction, we will fix it for you!'
            '\n'
            'Thanks again, and please give us the best rating (5★), help us more motivation to continue improving this game!'
        ),
        'value' : 'reply_0'
    })

    # Dùng cho: Phàn nàn về game kém hay hoặc thiếu tính năng.
    # Usage: Complains about bad games or missing features.
    response['options'].append({
        'text' : (
            'Thanks for your feedback!'
            '"\n"'
            'We think it make this game more challenge!'
            '\n'
            'Let\'s wait for next versions for cool gameplay, it will be coming soon!'
            '\n'
            'Thanks again, and please give us the best rating (5★), help us more motivation to continue improving this game!'
        ),
        'value' : 'reply_1'
    })

    # Dùng cho: Đánh giá vô tội vạ chả biết lý do gì, hoặc chỉ đánh giá tệ.
    # Usage: Complains about what-is-the-reason or just low ratings.
    response['options'].append({
        'text' : (
            'Thanks for your feedback!'
            '\n'
            'We wish you have enjoy this game.'
            '\n'
            'So please give us the best rating (5★), help us more motivation to continue improving this game!'
        ),
        'value' : 'reply_2'
    })

    # Dùng cho: Có vẻ lỗi gì đó nhưng không nêu rõ.
    # Usage: Complains about unknown bugs.
    response['options'].append({
        'text' : (
            'Thanks for your feedback!'
            '\n'
            'We think it make this game more challenge!'
            '\n'
            'Let\'s wait for the next version for cool gameplay, it will be coming soon!',
            '\n'
            'Thanks again, and please give us the best rating (5★), help us more motivation to continue improving this game!'
        ),
        'value' : 'reply_3'
    })

    # Dùng cho: Có ý kiến cập nhật hay sửa theo nhu cầu cá nhân (cách chơi, nhiều quảng cáo,...)
    # Usage: Personal opinion (new gameplay, many ads...)
    response['options'].append({
        'text' : (
            'Thanks for your feedback!'
            '\n'
            'We will fix your problem!'
            '\n'
            'Let\'s wait for next versions for cool gameplay, it will be coming soon!'
            '\n'
            'Thanks again, and please give us the best rating (5★), help us more motivation to continue improving this game!'
        ),
        'value' : 'reply_4'
    })

    # Vietnamese only.
    # Dùng cho: Có ý kiến cập nhật hay sửa theo nhu cầu cá nhân (cách chơi, nhiều quảng cáo,...)
    response['options'].append({
        'text' : (
            'Cám ơn bạn đã feedback cho chúng tôi!'
            '\n'
            'Chúng tôi luôn muốn người dùng đạt trải nghiệm tốt nhất.'
            '\n'
            'Xin hãy cho 5★ đo là động lực để chúng tôi phát triển trò chơi này tốt hơn!'
        ),
        'value' : 'reply_5'
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
        package_name = text
        reviews_resources = service.reviews()
        try:
            reviews_page = reviews_resources.list(
                packageName=package_name, 
                maxResults=5
            ).execute()
        except Exception as e:
            reviews_page = None
            response['text'] = str(e)

        print json.dumps(reviews_page, indent=4)

        if not reviews_page is None:
            attachments = []
            reviews = reviews_page['reviews']

            # Slow!            
            # image_url = get_cover_image_url(read_source(get_store_link(package_name)))

            for review in reviews:
                attachment = format_user_review(review, package_name)

                add_translate_button(attachment)
                add_reply_button(attachment)

                # Add a footer icon if any.
                # if image_url != None:
                #    attachment['footer_icon'] = image_url

                attachments.append(attachment)

                dev_attachment = format_developer_comment(review)
                if dev_attachment != None:
                    attachments.append(dev_attachment)

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
            # print 'data = %s' % post_data

            qsl_data = urlparse.parse_qsl(post_data)

            params = dict(qsl_data)
            print '========================================================================'
            print 'params = %s' % json.dumps(params, indent=4)

            response = {}
            response['response_type'] = 'in_channel'

            payload = params.get('payload')
            if payload != None:
                # Button.
                print 'Button type'
                payload_dict = json.loads(payload)
                print 'payload = %s' % json.dumps(payload_dict, indent=4)

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