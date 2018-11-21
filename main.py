# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


# import library os for reading path directory name ..
import os
import datetime
import random

# for routing subdomains
from webapp2_extras import routes

# for logging
import logging

# import third party library blockcypher
import blockcypher

# import
import cryptotools

# for working with regular expressions
import re

# to be able to import jinja2 , add to app.yaml
import jinja2
import webapp2

from google.appengine.api import app_identity

# for using datastore
from google.appengine.ext import ndb
from google.appengine.api import images
from base64 import b64encode

# validate user inputs
# import validate

# use pygl tools
# import pygltools as pt

# for REST APIs
import urllib
import urllib2
import json

# tell jinja2 where to look for files
template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir), autoescape=True)

class Handler(webapp2.RequestHandler):
	def write(self, *a, **kw):
		self.response.out.write(*a, **kw)

	def render_str(self, template, **params):
		t = jinja_env.get_template(template)
		return t.render(params)

	def render(self, template, **kw):
		output = self.render_str(template, **kw)
		self.write(output)


class PrintChequesPage(Handler):
	def get(self):

		# number of cheques to print
		NUMBER_OF_CHEQUES = 3

		# get cheques and images
		cheque_dates = []
		for i in range(NUMBER_OF_CHEQUES):
			ident, verification_master, verification_shifts, cheque = cryptotools.generateCheque()
			verification_chars, verification_bars = cryptotools.generate_chars_bars(verification_master, verification_shifts)
			ident_formatted = ' '.join([ident[:5], ident[5:10], ident[10:]])
			cheque_data = {'ident':ident_formatted, 'verification_chars':verification_chars, 'verification_bars':verification_bars, 'cheque':cheque}
			cheque_dates.append(cheque_data)

		# render page
		self.render('print.html', cheque_dates = cheque_dates)

class MainPage(Handler):
	def get(self):
		# get ident
		cheque_ident = self.request.get('q')

		self.render('main.html', cheque_ident = cheque_ident, cheque_balance = None)
		'''
		if cheque_ident:
			cheque_balance = cryptotools.get_balance(cheque_ident)
			# render main page
			self.render('main.html', cheque_ident = cheque_ident, cheque_balance = cheque_balance)
		else:
			# render main page
			self.render('main.html', cheque_ident = cheque_ident, cheque_balance = None)
		'''

	def post(self):
		# get parameters
		check_balance = self.request.get('check_balance')
		redeem = self.request.get('redeem')
		cheque_ident = self.request.get('cheque_ident')
		cheque_ident_requested = self.request.get('cheque_ident_requested')
		cheque_ident_filtered = filter(lambda x: x.isdigit(), cheque_ident)
		cheque_ident_requested_filtered = filter(lambda x: x.isdigit(), cheque_ident_requested)
		cheque_ident_formatted = '-'.join([cheque_ident_filtered[i:i+5] for i in range(0, len(cheque_ident_filtered), 5)])
		receiver_address = self.request.get('receiver_address')
		verification_index_request = self.request.get('verification_index')
		verification_code = self.request.get('verification_code')
		verification_code_filtered = filter(lambda x: x.isalpha(), verification_code)
		recaptcha_response = self.request.get('g-recaptcha-response')

		recaptcha_url = 'https://www.google.com/recaptcha/api/siteverify'
		values = {'secret': "6LcsKHwUAAAAAB3UkPVyeRErujY0G7cgq7Z6UWqh", 'response': recaptcha_response}

		verification_index_list = []
		base = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
		for i in range(4):
			for j in range(4):
				verification_index_list.append(base[i]+base[j+4])
		verification_index_new = random.randint(0,15)
		verification_index_chars = verification_index_list[verification_index_new]

		cheque_balance, cheque_public_address = cryptotools.get_balance(cheque_ident_filtered)

		if cheque_balance and (cheque_balance > 0):
			service_fee, transaction_fee = cryptotools.get_fees(cheque_balance)
			total_payout = cheque_balance - service_fee - transaction_fee

			cheque_balance = float(cheque_balance)/100000000
			service_fee = float(service_fee)/100000000
			transaction_fee = float(transaction_fee)/100000000
			total_payout = float(total_payout)/100000000
		else:
			service_fee = 0.0
			transaction_fee = 0.0
			total_payout = 0.0

		if check_balance:
			# render main page
			if cheque_balance is not None:
				self.render('main.html',
					cheque_ident = cheque_ident_formatted,
					cheque_ident_requested = cheque_ident_formatted,
					cheque_public_address = cheque_public_address,
					cheque_balance = cheque_balance,
					verification_index_chars = verification_index_chars,
					verification_index = verification_index_new,
					service_fee = service_fee,
					transaction_fee = transaction_fee,
					total_payout = total_payout)
			else:
				if len(cheque_ident_filtered) == 15:
					self.render('main.html',
						cheque_ident = cheque_ident,
						cheque_ident_requested = cheque_ident_formatted,
						cheque_balance = 0.0)
					return
				else:
					self.render('main.html',
						cheque_ident = cheque_ident,
						cheque_ident_requested = 'invalid',
						cheque_balance = 0.0)
					return
		else:
			# check recaptcha
			if recaptcha_response:
				# get info from recaptcha server
				data = urllib.urlencode(values)
				req = urllib2.Request(recaptcha_url, data)
				response = urllib2.urlopen(req)
				result = json.load(response)
				if result['success']:
					# captcha success
					if cryptotools.validate_btc_address(receiver_address):
						error_code, message = cryptotools.redeem(cheque_ident_requested_filtered, verification_code_filtered, verification_index_request, receiver_address)
					else:
						error_code = 201
						message = 'Receiver address is no valid Bitcoin address.'
					if error_code == 0:
						self.render('main.html',
									cheque_ident = cheque_ident_formatted,
									cheque_ident_requested = cheque_ident_formatted,
									cheque_public_address = cheque_public_address,
									cheque_balance = 0.0,
									redeem_transaction = message)
						return
					else:
						self.render('main.html',
									cheque_ident = cheque_ident_formatted,
									cheque_ident_requested = cheque_ident_formatted,
									cheque_public_address = cheque_public_address,
									cheque_balance = cheque_balance,
									verification_index_chars = verification_index_chars,
									verification_index = verification_index_new,
									receiver_address = receiver_address,
									service_fee = service_fee,
									transaction_fee = transaction_fee,
									total_payout = total_payout,
									error_message = message)
						return

			# return recaptcha error
			message = 'captcha failed'
			self.render('main.html',
						cheque_ident = cheque_ident_formatted,
						cheque_ident_requested = cheque_ident_formatted,
						cheque_public_address = cheque_public_address,
						cheque_balance = cheque_balance,
						verification_index_chars = verification_index_chars,
						verification_index = verification_index_new,
						receiver_address = receiver_address,
						service_fee = service_fee,
						transaction_fee = transaction_fee,
						total_payout = total_payout,
						error_message = message)
			return


app = webapp2.WSGIApplication([
    webapp2.Route(r'/print', handler = PrintChequesPage),
    webapp2.Route(r'/', handler = MainPage),
], debug=True)
