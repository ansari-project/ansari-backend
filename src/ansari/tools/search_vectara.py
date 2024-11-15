import json

import requests


class SearchVectara:
    def __init__(
        self,
        vectara_api_key: str,
        vectara_corpus_key: str,
        fn_name: str,
        fn_description: str,
        params: list[dict],
        required_params: list[str],
    ):
        self.api_key = vectara_api_key
        self.corpus_key = vectara_corpus_key
        self.base_url = f"https://api.vectara.io/v2/corpora/{self.corpus_key}/query"
        self.fn_name = fn_name
        self.fn_description = fn_description
        self.params = params
        self.required_params = required_params

    def get_tool_description(self):
        return {
            "type": "function",
            "function": {
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
            },
        }

    def get_tool_name(self):
        return self.fn_name

    def _build_request_payload(
        self,
        query: str,
        num_results: int = 5,
        **kwargs,
    ) -> dict:
        return {
            "query": query,
            "search": {
                "custom_dimensions": kwargs.get("custom_dimensions", {}),
                "metadata_filter": kwargs.get("metadata_filter", ""),
                "lexical_interpolation": kwargs.get("lexical_interpolation", 0.025),
                "semantics": kwargs.get("semantics", "default"),
                "offset": kwargs.get("offset", 0),
                "limit": num_results,
                "context_configuration": {
                    "characters_before": kwargs.get("characters_before", 30),
                    "characters_after": kwargs.get("characters_after", 30),
                    "sentences_before": kwargs.get("sentences_before", 3),
                    "sentences_after": kwargs.get("sentences_after", 3),
                    "start_tag": kwargs.get("start_tag", "<em>"),
                    "end_tag": kwargs.get("end_tag", "</em>"),
                },
                # "reranker": {
                #     "type": "customer_reranker",
                #     "reranker_name": kwargs.get("reranker_name", "Rerank_Multilingual_v1"),
                #     "limit": kwargs.get("reranker_limit", 0),
                #     "cutoff": kwargs.get("reranker_cutoff", 0)
                # }
            },
            # "generation": {
            #     "generation_preset_name": kwargs.get("generation_preset_name", "vectara-summary-ext-v1.2.0"),
            #     "max_used_search_results": kwargs.get("max_used_search_results", 5),
            #     "prompt_template": kwargs.get("prompt_template", ""),
            #     "max_response_characters": kwargs.get("max_response_characters", 300),
            #     "response_language": kwargs.get("response_language", "auto"),
            #     "model_parameters": kwargs.get("model_parameters", {}),
            #     "citations": kwargs.get("citations", {"style": "none"}),
            #     "enable_factual_consistency_score": kwargs.get("enable_factual_consistency_score", True)
            # },
            "stream_response": kwargs.get("stream_response", False),
        }

    def run(self, query: str, num_results: int = 5, **kwargs) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-api-key": self.api_key,
        }
        data = self._build_request_payload(query, num_results, **kwargs)
        response = requests.post(self.base_url, headers=headers, data=json.dumps(data))
        if response.status_code != 200:
            error_msg = f"Query failed with code {response.status_code}, reason {response.reason}, text {response.text}"
            raise requests.exceptions.HTTPError(error_msg)
        return response.json()

    def pp_response(self, response: dict) -> list:
        """Extract text from response"""
        if not response.get("search_results"):
            return []

        results = [r["text"] for r in response["search_results"]]
        return results

    def run_as_list(self, query: str, num_results: int = 5, **kwargs) -> list:
        """Return results as a list of strings"""
        response = self.run(query, num_results, **kwargs)
        return self.pp_response(response)

    def run_as_json(self, query: str, num_results: int = 5, **kwargs) -> dict:
        """Return results wrapped in a JSON object"""
        response = self.run(query, num_results, **kwargs)
        return {"matches": self.pp_response(response)}

    def run_as_string(self, query: str, num_results: int = 5, **kwargs) -> str:
        """Return results as a newline-separated string"""
        results = self.run_as_list(query, num_results, **kwargs)
        return "\n".join(results)
