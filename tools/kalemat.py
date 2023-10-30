import requests
import os
from hermetic.core.tool import Tool

KALEMAT_BASE_URL='https://api.kalimat.dev/search'
NAME = 'kalemat'
class Kalemat(Tool):

    def __init__(self, env):
        super().__init__(env = env)
        self.env.add_tool(NAME, self)

        self.api_key = os.environ.get('KALEMAT_API_KEY')
        self.base_url = KALEMAT_BASE_URL 
    
    def run(self, query: str, numResults: int=5,getText: int=1):

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
    
    def run_as_string(self, query: str, numResults: int=10, getText: int=1):
        def pp_ayah(ayah):
                ayah_num = ayah['id']
                ayah_ar = ayah['text']
                ayah_en = ayah['en_text']
                result = f'Ayah: {ayah_num}\nArabic Text: {ayah_ar}\nEnglish Text: {ayah_en}\n\n'
                return result
        results =  self.run(query, numResults, getText)
        rstring = '\n'.join([pp_ayah(r) for r in results])
        return rstring

# Example usage:
#api = KalematAPI() 
#result = api.search(query='Coral', numResults=10)
#print(result)
