### The purpose of this file is to show how to use the Ansari API v2 in terms of the sequence of calls to make. 
### This is a bit more complicated than the v1 API because we have to create a thread and then add messages to it.
### The v1 API just had one call to add a message.
### This file is intended to be run from the command line.
### It assumes that you have a running Ansari server on localhost:8000.
### It also assumes that you have a running Ansari database on localhost:5432.
### The steps are: register an account, log in with an accounnt, create a thread, add messages to the thread, and then get the thread.

import uuid
import requests
import json
import os
import time
import sys
import random

# This is the URL of the Ansari server.   
# If you are running the Ansari server locally, you can use the second line

default_url_remote = 'https://api-beta.ansari.chat'
default_url_local = 'http://localhost:8000'


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
    result = response.json()
    print(f'Response is {response}')

    if response.status_code != 200:
        print('Failed to login')
        return None
    else: 
        return response.json()['token']
    

def logout(url, token):
    print('Logging out')
    response = requests.post(url + '/api/v2/users/logout', 
                            headers={'Authorization': 'Bearer ' + token, 
                                     'x-mobile-ansari': 'ANSARI', 
    })
    print(f'Response is {response}')
    return response.json()


# Now create a thread.

def create_thread(url, token):
    print('Creating thread')
    response = requests.post(url + '/api/v2/threads',
                            headers={
                                'Authorization': 'Bearer ' + token,
                                'x-mobile-ansari': 'ANSARI', 
                            }
                            )
    json = response.json()
    print(f'Response is {json}')
    if 'thread_id' not in json:
        print('Failed to create thread')
        return None
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

def set_thread_name(url, token, thread_id, name):
    print('Setting thread name')
    response = requests.post(url + '/api/v2/threads/' + str(thread_id) + '/name',
                             headers={'Authorization': 'Bearer ' + token, 
                                     'x-mobile-ansari': 'ANSARI'}, 
                             json={'name': name})
    print(f'Response is {response}')
    return response.json()         

def get_all_threads(url, token):
    print('Getting all threads')
    response = requests.get(url + '/api/v2/threads',
                            headers={'Authorization': 'Bearer ' + token, 
                                     'x-mobile-ansari': 'ANSARI', 
    })
    print(f'Response is {response}')
    return response.json()     

def delete_thread(url, token, thread_id):
    print('Deleting thread')
    response = requests.delete(url + '/api/v2/threads/' + str(thread_id),
                            headers={'Authorization': 'Bearer ' + token, 
                                     'x-mobile-ansari': 'ANSARI', 
    })
    print(f'Response is {response}')
    return response.json()

def refresh_token(url, token):
    print('Refreshing token')
    response = requests.get(url + '/api/v2/users/refresh_token', 
                            headers={'Authorization': 'Bearer ' + token, 
                                     'x-mobile-ansari': 'ANSARI', 
    })
    print(f'Response is {response}')
    return response.json()['token']

def add_feedback(url, token, thread_id, message_id, feedback_class, comment):
    print('Adding feedback')
    response = requests.post(url + '/api/v2/feedback',
                            headers={'Authorization': 'Bearer ' + token, 
                                     'x-mobile-ansari': 'ANSARI', 
    }, json={
        'thread_id': thread_id,
        'message_id': message_id,
        'feedback_class': feedback_class,
        'comment': comment
    })
    print(f'Response is {response}')
    return response.json()

# Generate a random email address.

if sys.argv[1] == 'local':
    default_url = default_url_local
elif sys.argv[1] == 'remote':
    default_url = default_url_remote
else: 
    print('Usage: python api_v2_exercise.py [local|remote]')
    sys.exit(1)


random_number = random.randint(0, 10000)
random_pass = str(uuid.uuid4())
email_address = f'waleedk+test_{random_number}@gmail.com'

# Try to login with a non-existent account. 
login(default_url, 'bogus@email.com', 'bogus')

# Try to register a weak password.
register(default_url, email_address, str("qwerty"), f'Waleed {random_number}', 'Kadous')

# Ok regigster for real. 
register(default_url, email_address, str(random_pass), f'Waleed {random_number}', 'Kadous')

# Try to register twice. See what happens. 
register(default_url, email_address, str(random_pass), f'Waleed {random_number}', 'Kadous')


token = login(default_url, email_address, str(random_pass))

#Use a refreshed token
new_token = refresh_token(default_url, token)

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

# Add feedback 
add_feedback(default_url, token, thread_id, result['messages'][0]['id'], 'thumbsup', 'I like this message')

# Create a second thread

thread_id = create_thread(default_url, token)

message = 'Salam 2.'
for chunk in add_message(default_url, token, thread_id, 'user', message): 
    sys.stdout.write(chunk.decode('utf-8'))
    sys.stdout.flush()
sys.stdout.write('\n')

message = "How old are you?"
for chunk in add_message(default_url, token, thread_id, 'user', message): 
    sys.stdout.write(chunk.decode('utf-8'))
    sys.stdout.flush()
sys.stdout.write('\n')

# Let's get all threads
response = get_all_threads(default_url, token)
print('All threads are ', response)

# Now let's delete the second thread 
response = delete_thread(default_url, token, thread_id)

# Let's check that we successfully deleted the thread. 
response = get_all_threads(default_url, token)
print('Now threads are ', response)


# Let's also check preference setting. 
set_pref(default_url, token, 'language', 'en')
set_pref(default_url, token, 'madhab', 'hanafi')  
result = get_prefs(default_url, token)
print(result)

# Now try to logout and then create a thread. This should fail.

logout(default_url, token)

#This should fail
thread_id = create_thread(default_url, token)
