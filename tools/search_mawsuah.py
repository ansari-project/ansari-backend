import os
import json
import requests

VECTARA_BASE_URL='https://api.vectara.io:443/v1/query'
FN_NAME='search_mawsuah'
class SearchMawsuah:

    def __init__(self):
        self.auth_token = os.getenv('VECTARA_AUTH_TOKEN')
        self.customer_id = os.getenv('VECTARA_CUSTOMER_ID')
        self.corpus_id = os.getenv('VECTARA_CORPUS_ID')
        self.base_url = VECTARA_BASE_URL 
    

    def get_function_description(self):
        return {
                "name": FN_NAME,
                "description": "Queries an encyclopedia of Islamic jurisprudence (fiqh) for relevant rulings. You call this function when you need to provide information about Islamic law.  Regardless of the language used in the original conversation, you will translate the query into Arabic before searching the encyclopedia. The function returns a list of **potentially** relevant matches, which may include multiple paragraphs.",
                "parameters": {
                    "type": "object",
                    "properties": {
                    "query": {
                        "type": "string",
                        "description": "The topic to search for in the fiqh encyclopedia. You will translate this query into Arabic."
                        }
                    },
                    "required": ["query"]
                }
            }

    def get_fn_name(self):
         return FN_NAME

    def run(self, query: str, num_results: int=5):
        print(f'Searching al-mawsuah for "{query}"')
        # Headers
        headers = {
            "x-api-key": self.auth_token,
            "customer-id": self.customer_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        data = {"query": [
                        {
                        "query": query,
                        "queryContext": "",
                        "start": 0,
                        "numResults": num_results,
                        "contextConfig": {
                            "charsBefore": 0,
                            "charsAfter": 0,
                            "sentencesBefore": 2,
                            "sentencesAfter": 2,
                            "startTag": "<match>",
                            "endTag": "</match>"
                        },
                        "corpusKey": [
                            {
                            "customerId": self.customer_id,
                            "corpusId": self.corpus_id,
                            "semantics": 0,
                            "metadataFilter": "",
                            "lexicalInterpolationConfig": {
                                "lambda": 0.1
                            },
                            "dim": []
                            }
                        ],
                        "summary": []
                        }
                    ]
                    }

        response = requests.post(self.base_url, headers=headers, data=json.dumps(data))
        
        if response.status_code != 200:
            print(f"Query failed with code {response.status_code}, reason {response.reason}, text {response.text}")
            response.raise_for_status()
        
        return response.json()
    
    def pp_response(self, response):
        results = []
        for response_item in response['responseSet']:
            for result in response_item['response']:
                results.append(result['text'])
        return results

    def run_as_list(self, query: str, num_results: int=10):
        return self.pp_response(self.run(query, num_results))
    
    def run_as_json(self, query: str, num_results: int=10):
        return {"matches": self.pp_response(self.run(query, num_results))}
