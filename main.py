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
			ident, verification_master, verification_shifts, private_key, cheque = cryptotools.generateCheque()
			verification_chars, verification_bars = cryptotools.generate_chars_bars(verification_master, verification_shifts)
			ident_formatted = ' '.join([ident[:5], ident[5:10], ident[10:]])
			cheque_data = {'ident':ident, 'ident_formatted':ident_formatted, 'verification_chars':verification_chars, 'verification_bars':verification_bars, 'private_key':private_key, 'cheque':cheque}
			cheque_dates.append(cheque_data)

		# render page
		self.render('print.html', cheque_dates = cheque_dates)

class MainPage(Handler):
	def get(self):
		cheque_ident = self.request.get('cheque_ident')

		if cheque_ident:
			self.handle_request(self, True)
			return

		self.render('main.html',
					cheque_ident = cheque_ident,
					cheque_balance = None)

	def post(self):
		self.handle_request(self, False)
		return

	def handle_request(self, is_get_request, *args, **kwargs):
		# get parameters
		check_balance = self.request.get('check_balance')
		redeem = self.request.get('redeem')
		cheque_ident = self.request.get('cheque_ident')
		cheque_ident_requested = self.request.get('cheque_ident_requested')
		cheque_ident_filtered = filter(lambda x: x.isdigit(), cheque_ident)
		cheque_ident_requested_filtered = filter(lambda x: x.isdigit(), cheque_ident_requested)
		cheque_ident_formatted = '-'.join([cheque_ident_filtered[i:i+5] for i in range(0, len(cheque_ident_filtered), 5)])
		cheque_ident_requested_formatted = '-'.join([cheque_ident_requested_filtered[i:i+5] for i in range(0, len(cheque_ident_requested_filtered), 5)])
		receiver_btc_adr = self.request.get('receiver_btc_adr').strip()
		verification_index_request = self.request.get('verification_index')
		verification_code = self.request.get('verification_code')
		verification_code_filtered = filter(lambda x: x.isalpha(), verification_code)
		recaptcha_response = self.request.get('g-recaptcha-response')

		recaptcha_url = 'https://www.google.com/recaptcha/api/siteverify'
		values = {'secret': "6LcsKHwUAAAAAB3UkPVyeRErujY0G7cgq7Z6UWqh", 'response': recaptcha_response}

		echange_rate_usd = cryptotools.get_exchange_rate_usd()

		verification_index_list = []
		base = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
		for i in range(4):
			for j in range(4):
				verification_index_list.append(base[i]+base[j+4])
		verification_index_new = random.randint(0,15)
		verification_index_chars = verification_index_list[verification_index_new]

		if cheque_ident_requested:
			cheque_balance, cheque_public_address = cryptotools.get_balance(cheque_ident_requested_filtered)
		else:
			cheque_balance, cheque_public_address = cryptotools.get_balance(cheque_ident_filtered)

		if cheque_balance and (cheque_balance > 0):
			service_fee, transaction_fee = cryptotools.get_fees(cheque_balance, cheque_public_address)
			if (transaction_fee == 0):
				error_message_transaction_fee = "Balance too low for payout (not enough for network fee)."
				total_payout = 0
			else:
				error_message_transaction_fee = None
				total_payout = cheque_balance - service_fee - transaction_fee
			show_cheque_balance = True
			show_payout_details = True
			show_service_fee = (service_fee != 0)
			cheque_balance_usd = '{:.2f}'.format(float(cheque_balance)*echange_rate_usd/100000000)
			service_fee_usd = '{:.2f}'.format(float(service_fee)*echange_rate_usd/100000000)
			transaction_fee_usd = '{:.2f}'.format(float(transaction_fee)*echange_rate_usd/100000000)
			total_payout_usd = '{:.2f}'.format(float(total_payout)*echange_rate_usd/100000000)
			cheque_balance = '{:.8f}'.format(float(cheque_balance)/100000000)
			service_fee = '{:.8f}'.format(float(service_fee)/100000000)
			transaction_fee = '{:.8f}'.format(float(transaction_fee)/100000000)
			total_payout = '{:.8f}'.format(float(total_payout)/100000000)

		else:
			show_cheque_balance = (cheque_balance is not None)
			show_payout_details = False
			show_service_fee = False
			error_message_transaction_fee = None
			cheque_balance_usd = '{:.2f}'.format(0.0)
			service_fee_usd = '{:.2f}'.format(0.0)
			transaction_fee_usd = '{:.2f}'.format(0.0)
			total_payout_usd = '{:.2f}'.format(0.0)
			cheque_balance = '{:.8f}'.format(0.0)
			service_fee = '{:.8f}'.format(0.0)
			transaction_fee = '{:.8f}'.format(0.0)
			total_payout = '{:.8f}'.format(0.0)

		if check_balance or (is_get_request == True):
			# render main page
			if show_cheque_balance:
				self.render('main.html',
					cheque_ident = cheque_ident_formatted,
					cheque_ident_requested = cheque_ident_formatted,
					cheque_public_address = cheque_public_address,
					verification_index_chars = verification_index_chars,
					verification_index = verification_index_new,
					cheque_balance = cheque_balance,
					service_fee = service_fee,
					transaction_fee = transaction_fee,
					total_payout = total_payout,
					cheque_balance_usd = cheque_balance_usd,
					service_fee_usd = service_fee_usd,
					transaction_fee_usd = transaction_fee_usd,
					total_payout_usd = total_payout_usd,
					show_payout_details = show_payout_details,
					show_service_fee = show_service_fee,
					error_message_transaction_fee = error_message_transaction_fee)
			else:
				if len(cheque_ident_filtered) == 15:
					error_message_id = "ID not found"
				else:
					error_message_id = "Invalid ID"
				self.render('main.html',
						cheque_ident = cheque_ident,
						cheque_balance = None,
						error_message_id = error_message_id)
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
					if cryptotools.validate_btc_address(receiver_btc_adr):
						error_code, message = cryptotools.redeem(cheque_ident_requested_filtered, verification_code_filtered, verification_index_request, receiver_btc_adr)
						error_message_verification = message
						error_message_address = None
					else:
						error_code = 201
						error_message_verification = None
						error_message_address = 'Invalid address'
					if error_code == 0:
						show_payout_details = False
						show_service_fee = False
						cheque_balance = '{:.8f}'.format(0.0)
						cheque_balance_usd = '{:.2f}'.format(0.0)
						self.render('main.html',
									cheque_ident = cheque_ident_requested_formatted,
									cheque_ident_requested = cheque_ident_requested_formatted,
									cheque_public_address = cheque_public_address,
									cheque_balance = cheque_balance,
									cheque_balance_usd = cheque_balance_usd,
									show_payout_details = show_payout_details,
									show_service_fee = show_service_fee,
									redeem_transaction = message)
						return
					else:
						self.render('main.html',
									cheque_ident = cheque_ident_requested_formatted,
									cheque_ident_requested = cheque_ident_requested_formatted,
									cheque_public_address = cheque_public_address,
									cheque_balance = cheque_balance,
									verification_index_chars = verification_index_chars,
									verification_index = verification_index_new,
									receiver_btc_adr = receiver_btc_adr,
									service_fee = service_fee,
									transaction_fee = transaction_fee,
									total_payout = total_payout,
									cheque_balance_usd = cheque_balance_usd,
									service_fee_usd = service_fee_usd,
									transaction_fee_usd = transaction_fee_usd,
									total_payout_usd = total_payout_usd,
									show_payout_details = show_payout_details,
									show_service_fee = show_service_fee,
									error_message_verification = error_message_verification,
									error_message_address = error_message_address)
						return

			# return recaptcha error
			error_message_captcha = 'Captcha failed'
			self.render('main.html',
						cheque_ident = cheque_ident_formatted,
						cheque_ident_requested = cheque_ident_formatted,
						cheque_public_address = cheque_public_address,
						cheque_balance = cheque_balance,
						verification_index_chars = verification_index_chars,
						verification_index = verification_index_new,
						receiver_btc_adr = receiver_btc_adr,
						service_fee = service_fee,
						transaction_fee = transaction_fee,
						show_payout_details = show_payout_details,
						show_service_fee = show_service_fee,
						total_payout = total_payout,
						cheque_balance_usd = cheque_balance_usd,
						service_fee_usd = service_fee_usd,
						transaction_fee_usd = transaction_fee_usd,
						total_payout_usd = total_payout_usd,
						error_message_captcha = error_message_captcha)
			return


app = webapp2.WSGIApplication([
    webapp2.Route(r'/print', handler = PrintChequesPage),
    webapp2.Route(r'/', handler = MainPage),
], debug=True)
