### The purpose of this file is to show how to use the Ansari API v2 in terms of the sequence of calls to make. 
### This is a bit more complicated than the v1 API because we have to create a thread and then add messages to it.
### The v1 API just had one call to add a message.
### This file is intended to be run from the command line.
### It assumes that you have a running Ansari server on localhost:8000.
### It also assumes that you have a running Ansari database on localhost:5432.
### The steps are: register an account, log in with an accounnt, create a thread, add messages to the thread, and then get the thread.

import requests
import json
import os
import time
import sys
import random

# This is the URL of the Ansari server.   
# If you are running the Ansari server locally, you can leave this as is.

default_url = 'http://localhost:8000'

# Start with registering. 

def register(url, email, password, first_name, last_name):
    print(f'Registering {email} {password} {first_name} {last_name}')
    response = requests.post(url + '/api/v2/users/register',  
                             headers={
                                'x-mobile-ansari': 'ANSARI', 
                             }, json={
                                'email': email,
                                'password': password,
                                'first_name': first_name,
                                'last_name': last_name
                            })
    print(f'Response is {response}')
    content = response.json()
    print(f'Content is {content}')
    return response.json()

# Now log in.

def login(url, email, password):
    print(f'Logging in {email} {password}')
    response = requests.post(url + '/api/v2/users/login', json={
        'email': email,
        'password': password
    })
    print(f'Response is {response.json()}')
    return response.json()['token']

# Now create a thread.

def create_thread(url, token):
    print('Creating thread')
    response = requests.post(url + '/api/v2/threads',
                            headers={
                                'Authorization': 'Bearer ' + token,
                                'x-mobile-ansari': 'ANSARI', 
                            }
                            )
    print(f'Response is {response.json()}')
    return response.json()['thread_id']

# Now add a message to the thread.
    
def add_message(url, token, thread_id, role, content):
    print('Adding message')
    response = requests.post(url + '/api/v2/threads/' + str(thread_id), 
        json={
        'role': role,
        'content': content
    }, headers={
        'Authorization': 'Bearer ' + token,
        'x-mobile-ansari': 'ANSARI', 
    }, stream=True)
    return response.iter_content(chunk_size=None)

# Now get the thread.
    
def get_thread(url, token, thread_id):
    print('Getting thread')
    response = requests.get(url + '/api/v2/threads/' + str(thread_id), 
                            headers={'Authorization': 'Bearer ' + token, 
                                        'x-mobile-ansari': 'ANSARI', 
    })
    print(f'Response is {response}')
    return response.json()


def set_pref(url, token, key, value):
    print('Setting preference')
    response = requests.post(url + '/api/v2/preferences',
                            headers={'Authorization': 'Bearer ' + token, 
                                        'x-mobile-ansari': 'ANSARI', 
    }, json={
        'key': key, 
        'value': value
    })
    print(f'Response is {response}')
    return response.json()

def get_prefs(url, token):
    print('Getting preferences')
    response = requests.get(url + '/api/v2/preferences',
                            headers={'Authorization': 'Bearer ' + token, 
                                        'x-mobile-ansari': 'ANSARI', 
    })
    print(f'Response is {response}')
    return response.json()

# Generate a random email address.

random_number = random.randint(0, 10000)
email_address = f'waleedk+test_{random_number}@gmail.com'

register(default_url, email_address, str(random_number), f'Waleed {random_number}', 'Kadous')
token = login(default_url, email_address, str(random_number))
thread_id = create_thread(default_url, token)
message = 'Salam.'
for chunk in add_message(default_url, token, thread_id, 'user', message): 
    sys.stdout.write(chunk.decode('utf-8'))
    sys.stdout.flush()
sys.stdout.write('\n')

message = "How many verses mention coral in the Qur'an? Just the number, I dont need the verses."
for chunk in add_message(default_url, token, thread_id, 'user', message): 
    sys.stdout.write(chunk.decode('utf-8'))
    sys.stdout.flush()
sys.stdout.write('\n')

result = get_thread(default_url, token, thread_id)
print(result)

# Let's also check preference setting. 
set_pref(default_url, token, 'language', 'en')
set_pref(default_url, token, 'madhab', 'hanafi')  
result = get_prefs(default_url, token)
print(result)
