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
        for line in response.iter_content():
            # Filter out keep-alive new lines
            if line:
                decoded_line = line.decode('utf-8')
                sys.stdout.write(decoded_line)
                sys.stdout.flush()
                # Do something with the event
                # Typically, you'd parse the event data and act accordingly
                # For example, you could convert the line to JSON if expected
                # event_data = json.loads(decoded_line.lstrip("data: "))
                # print(event_data)
                    
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")

# Replace with the actual server URL that sends server-sent events
sse_url = "http://localhost:8000/api/v1/complete"

data = {
    "messages": [
        {
            "role": "user", 
            "content" : "Who are you?" 
        }
     
    ]
}

ansari_complete(sse_url, data)