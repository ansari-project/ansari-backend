import requests
import os
from constants import KALEMAT_BASE_URL

class KalematAPI:

    def __init__(self):
        self.api_key = os.environ.get('KALEMAT_API_KEY')
        self.base_url = KALEMAT_BASE_URL # replace with actual base url
    
    def search(self, query: str, numResults: int=5,getText: int=1):

        headers = {'x-api-key': self.api_key}
        payload = {
            'query': query,
            'numResults': numResults,
            'getText': getText
            
        }

        response = requests.get(self.base_url, headers=headers, params=payload)
        
        if response.status_code != 200:
            raise Exception(f'Request failed with status {response.status_code}')
        
        return response.json()

# Example usage:
#api = KalematAPI() 
#result = api.search(query='Coral', numResults=10)
#print(result)
