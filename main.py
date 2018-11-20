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
		cheque_ident_filtered = filter(lambda x: x.isdigit(), cheque_ident)
		receiver_address = self.request.get('receiver_address')
		verification_index = self.request.get('verification_index')
		verification_code = self.request.get('verification_code')
		
		if check_balance:
			cheque_balance = cryptotools.get_balance(cheque_ident_filtered)
			# render main page
			if cheque_balance is not None:
				cheque_ident_formatted = '-'.join([cheque_ident_filtered[i:i+5] for i in range(0, len(cheque_ident_filtered), 5)])
				
				verification_index_list = []
				base = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
				for i in range(4):
					for j in range(4):
						verification_index_list.append(base[i]+base[j+4])
				
				verification_index = random.randint(0,15)
				verification_index_chars = verification_index_list[verification_index]
				self.render('main.html', cheque_ident = cheque_ident_formatted, cheque_balance = cheque_balance, verification_index_chars = verification_index_chars, verification_index = verification_index)
			else:
				self.render('main.html', cheque_ident = cheque_ident, cheque_balance = cheque_balance)
		elif redeem:
			error_code, message = cryptotools.redeem(cheque_ident_filtered, verification_code, verification_index, receiver_address)
			if error_code == 0:
				self.render('main.html', cheque_ident = cheque_ident, redeem_transaction = message)
			else:
				self.render('main.html', cheque_ident = cheque_ident, error_message = str(error_code) + ': ' + message)
		
		
		
		
		 
		
app = webapp2.WSGIApplication([
    webapp2.Route(r'/print', handler = PrintChequesPage),
    webapp2.Route(r'/', handler = MainPage),
], debug=True)





