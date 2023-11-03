import requests
import json
import sys

def ansari_complete(url, data):
    """Function to listen to server sent events from the given URL."""
    headers = {'Content-Type': 'application/json'}
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data), stream=True)
        # Check if the connection was established successfully
        if response.status_code != 200:
            print(f"Connection failed: {response.status_code}")
            return
        
        # Iterate over lines
        for content in response.iter_content():
            # Filter out keep-alive new lines
            if content:
                decoded_content = content.decode('utf-8')
                sys.stdout.write(decoded_content)
                sys.stdout.flush()
                    
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")

# Replace with the actual server URL that sends server-sent events
sse_url = "https://ansari-staging-b78f9bbc2ddc.herokuapp.com/api/v1/complete"

data = {
    "messages": [
        {
            "role": "user", 
            "content" : "Who are you?" 
        }
     
    ]
}

ansari_complete(sse_url, data)