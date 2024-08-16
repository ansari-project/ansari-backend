import json

import requests

VECTARA_BASE_URL = "https://api.vectara.io:443/v1/query"

QUERY_CONTEXT = ""  # TODO: understand this param
START = 0  # TODO: understand this param
CHARS_BEFORE = 0
CHARS_AFTER = 0
SENTENCES_BEFORE = 2
SENTENCES_AFTER = 2
START_TAG = "<match>"
END_TAG = "</match>"
SEMANTICS = 0  # TODO: understand this param
METADATA_FILTER = ""
LEXICAL_INTERPOLATION_CONFIG = 0.1


class SearchVectara:
    def __init__(
        self,
        vectara_auth_token: str,
        vectara_customer_id: str,
        vectara_corpus_id: str,
        fn_name: str,
        fn_description: str,
        params: list[dict],
        required_params: list[str],
    ):
        self.auth_token = vectara_auth_token
        self.customer_id = vectara_customer_id
        self.corpus_id = vectara_corpus_id
        self.base_url = VECTARA_BASE_URL
        self.fn_name = fn_name
        self.fn_description = fn_description
        self.params = params
        self.required_params = required_params
    
    def get_function_description(self):
        return {
            "name": self.fn_name,
            "description": self.fn_description,
            "parameters": {
                "type": "object",
                "properties": {

                    param["name"]: {
                        "type": param["type"],
                        "description": param["description"],
                    }
                    for param in self.params

                },
                "required": self.required_params,
            },
        }

    def get_fn_name(self):
        return self.fn_name

    def _build_request_payload(self, query: str, num_results: int, **kwargs) -> dict:
        return {
            "query": [
                {
                    "query": query,
                    "queryContext": kwargs.get("queryContext", QUERY_CONTEXT),
                    "start": kwargs.get("start", START),
                    "numResults": num_results,
                    "contextConfig": {
                        "charsBefore": kwargs.get("charsBefore", CHARS_BEFORE),
                        "charsAfter": kwargs.get("charsAfter", CHARS_AFTER),
                        "sentencesBefore": kwargs.get(
                            "sentencesBefore", SENTENCES_BEFORE
                        ),
                        "sentencesAfter": kwargs.get("sentencesAfter", SENTENCES_AFTER),
                        "startTag": kwargs.get("startTag", START_TAG),
                        "endTag": kwargs.get("endTag", END_TAG),
                    },
                    "corpusKey": [
                        {
                            "customerId": self.customer_id,
                            "corpusId": self.corpus_id,
                            "semantics": kwargs.get("semantics", SEMANTICS),
                            "metadataFilter": kwargs.get(
                                "metadataFilter", METADATA_FILTER
                            ),
                            "lexicalInterpolationConfig": {
                                "lambda": kwargs.get(
                                    "lexicalInterpolationConfig",
                                    LEXICAL_INTERPOLATION_CONFIG,
                                )
                            },
                            "dim": [],
                        }
                    ],
                    "summary": [],
                }
            ]
        }

    def run(self, query: str, num_results: int = 5, **kwargs) -> dict:
        print(f'Searching al-mawsuah for "{query}"')
        headers = {
            "x-api-key": self.auth_token,
            "customer-id": self.customer_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        data = self._build_request_payload(query, num_results, **kwargs)

        response = requests.post(self.base_url, headers=headers, data=json.dumps(data))

        if response.status_code != 200:
            print(
                f"Query failed with code {response.status_code}, reason {response.reason}, text {response.text}"
            )
            response.raise_for_status()

        return response.json()

    def pp_response(self, response: dict) -> list:
        return [
            result["text"]
            for response_item in response["responseSet"]
            for result in response_item["response"]
        ]

    def run_as_list(self, query: str, num_results: int = 10, **kwargs) -> list:
        return self.pp_response(self.run(query, num_results), **kwargs)

    def run_as_json(self, query: str, num_results: int = 10, **kwargs) -> dict:
        return {"matches": self.pp_response(self.run(query, num_results, **kwargs))}
