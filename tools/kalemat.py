from pydantic import BaseModel
import requests
import os

KALEMAT_BASE_URL='https://api.kalimat.dev/search'
class Kalemat(BaseModel):

    def get_function_description(self):
    return {"name": "search_quran",
            "description": "Search the Qur'an for relevant verses. This should be extracted from the question.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The topic to search the Qur'an for ",
                    },
                },
                "required": ["query"],
            },
          }

    def __init__(self, env):
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

