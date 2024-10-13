import re
import os
import time
from pydantic import BaseModel
from util.prompt_mgr import PromptMgr
from tools.search_quran import SearchQuran
from tools.search_hadith import SearchHadith
import json
from openai import OpenAI
import litellm
from litellm.types import utils as litellm_types # can be ctrl+clicked to see implementation of Delta/ChatCompletionDeltaToolCall classes.
from langfuse import Langfuse
from datetime import datetime, date
from langfuse.model import InitialGeneration, CreateGeneration, CreateTrace
import hashlib
from typing import Union
from dotenv import load_dotenv
load_dotenv()

# litellm.set_verbose=True

lf = Langfuse()
lf.auth_check()

MODEL = 'gpt-4o' # 'groq/llama3-70b-8192'

MAX_TOOL_TRIES = 5
class Ansari: 
    def __init__(self, json_format = False):
        sq = SearchQuran()
        sh = SearchHadith()
        self.tool_name_to_instance = { sq.get_tool_name(): sq, sh.get_tool_name(): sh}
        self.model = MODEL
        self.pm = PromptMgr()
        self.sys_msg = self.pm.bind('system_msg_tool').render()
        self.tools = [x.get_tool_description() for x in self.tool_name_to_instance.values()]
        self.message_history = [{
            'role': 'system',
            'content': self.sys_msg
        }]
        self.json_format = json_format
        
    # The trace id is a hash of the first user input and the time. 
    def compute_trace_id(self):
        today = date.today()
        hashstring = str(today) + self.message_history[1]['content']
        result = hashlib.md5(hashstring.encode())
        return 'chash_' + result.hexdigest()

    def greet(self):
        self.greeting = self.pm.bind('greeting')
        return self.greeting.render()
    
    def process_input(self, user_input):
        self.message_history.append({
            'role': 'user',
            'content': user_input
        })
        return self.process_message_history()

    def log(self):
        trace_id = self.compute_trace_id()
        trace_msg = '\n\n' if os.getenv('TO_STDIO') else ''
        trace_msg += f'trace id: {trace_id}'
        print(trace_msg)
        trace = lf.trace(CreateTrace(
            id=trace_id,
            name='ansari-trace'
        ))

        generation = trace.generation(CreateGeneration(
            name='ansari-gen',
            startTime=self.start_time,
            endTime=datetime.now(),
            model=MODEL,
            prompt=self.message_history[:-1],
            completion=self.message_history[-1]['content'],
        )) 

    
    def replace_message_history(self, message_history):
        self.message_history = [{
            'role': 'system',
            'content': self.sys_msg
        }] + message_history
        for m in self.process_message_history():
            if m:
                yield m

    def process_message_history(self):
        # Keep processing the user input until we get something from the assistant
        self.start_time = datetime.now()
        count = 0
        while self.message_history[-1]['role'] != 'assistant':
            try: 
                print(f'Process attempt #{count+1} of this message history:')
                print('-'*60)
                print(self.message_history)
                print('-'*60)
                # This is pretty complicated so leaving a comment. 
                # We want to yield from so that we can send the sequence through the input
                # Also use tools only if we haven't tried too many times (failure) and if the last message was not from the tool (success!)
                use_tool = (count < MAX_TOOL_TRIES) and self.message_history[-1]['role'] != 'tool'
                print('Will attempt to use tools?:', use_tool)
                if not use_tool:
                    status_msg = 'Not using tools -- tries exceeded' if count >= MAX_TOOL_TRIES else 'Used tools! will paraphrase using "words" mode ...'
                    print(status_msg)

                yield from self.process_one_round(use_tool)
                count += 1
            except Exception as e:
                print('Exception occurred: ', e)
                print('Retrying in 5 seconds...')
                time.sleep(5)
        self.log()
    
    def get_completion(self, **kwargs):
        return litellm.completion(
            **kwargs
        )
        
    @staticmethod
    def _combine_json_objects(json_string):
        """
        Combine multiple JSON objects in a string into a single JSON object with concatenated values.

        This function takes a string containing multiple JSON objects and combines them into a single
        JSON object. The values of the same keys are concatenated with a comma and a space.

        Args:
            json_string (str): A string containing multiple JSON objects.

        Returns:
            str: A JSON string representing the combined JSON object.

        Example:
            >>> json_string = '{"query": "2:1"}{"query": "2:2"}{"query": "2:1"}'
            >>> combined_json = combine_json_objects(json_string)
            >>> print(combined_json)
            {"query": "2:1, 2:2"}
        """
        # Use regular expression to find all JSON objects in the string
        # (assuming there are no nested JSON objects)
        json_objects = re.findall(r'\{.*?\}', json_string)
        
        # Parse each JSON object and combine the values
        combined_json = {}
        for obj in json_objects:
            data = json.loads(obj)
            for key, value in data.items():
                if key in combined_json:
                    # Append the value to the list if it's not already present
                    if value not in combined_json[key]:
                        combined_json[key].append(value)
                else:
                    # Initialize the list with the first value
                    combined_json[key] = [value]

        # Convert lists to comma-separated strings
        for key in combined_json:
            combined_json[key] = ", ".join(combined_json[key])
                
        return combined_json

    def process_one_round(self, use_tool = True):
        response = None
        common_params = {
            'model': self.model,
            'messages': self.message_history,
            'stream': True,
            'timeout': 30.0,
            'temperature': 0.0,
            'metadata': {'generation-name': 'ansari'},
            'num_retries': 5
        }

        while not response:
            try: 
                if use_tool: 
                    tools_params = {
                        'tools': self.tools,
                        'tool_choice': 'auto'
                    }
                    if self.json_format:
                        response = self.get_completion(**common_params,
                                                       **tools_params,
                                                        response_format={"type": "json_object"})
                    else:
                        response = self.get_completion(**common_params,
                                                       **tools_params)
                                                        
                else:
                    if  self.json_format:
                        response = self.get_completion(**common_params, 
                                                        response_format={"type": "json_object"})
                    else: 
                        response = self.get_completion(**common_params)
                # print('Response is ', response)
            except Exception as e:
                print('Exception occurred: ', e)
                print('Retrying in 5 seconds...')
                time.sleep(5)
            
    
        words = ''
        # "tool" is synonymous with "function", as that's currently the only 
        # supported type by the model provider (e.g., OpenAI) 
        tool_name = ''
        tool_arguments = ''
        tool_id = ''
        response_mode = '' # words or tool
        print('response is', response)
        for tok in response: 
            delta = tok.choices[0].delta
            if not response_mode: 
                # This code should only trigger the first 
                # time through the loop.
                # print(f'\n\nFirst tok is {tok}\n\n') # uncomment when debugging only
                if 'tool_calls' in delta and delta.tool_calls:
                    # We are in tool mode
                    response_mode = 'tool'
                    print(f'Tok is {tok}')
                    tool_name = delta.tool_calls[0].function.name
                    tool_id = delta.tool_calls[0].id
                else: 
                    response_mode = 'words'
                print('Response mode: ' + response_mode)

            # We process things differently depending on whether it is a tool or a text
            if response_mode == 'words':
                if delta.content != None: 
                    words += delta.content
                    yield delta.content 
                elif delta.content == None: # End token
                    self.message_history.append({
                            'role': 'assistant',
                            'content': words
                        })
                    break
                else: 
                    continue

            elif response_mode == 'tool':
                if 'tool_calls' not in delta: # shouldn't occur unless model provider's/LiteLLM's API is changed
                    continue
                if delta.tool_calls: # There are still tokens to be processed
                    args_str = delta.tool_calls[0].function.arguments
                    tool_arguments += args_str 
                    # yield '' # we shouldn't yield anything if it's a tool
                else: # End token
                    tool_arguments: dict[str] = self._combine_json_objects(tool_arguments)
                    
                    # "process_tool_call" will append the tool call to the message history
                    self.process_tool_call(input, tool_name, tool_arguments, tool_id) # TODO: Ask if "input" should be removed or not, as it's not used anywhere
                    
                    # now, process_message_history will call process_one_round(use_tools=False) to let the model paraphrase the 
                    # tool's output (in the message history), thus generating a final response to the user
                    break
            else:
                raise Exception("Invalid response mode: " + response_mode)


    
    def process_tool_call(self, orig_question_from_stdin, tool_name:str, tool_arguments:dict[str], tool_id:str):
        
        if tool_name not in self.tool_name_to_instance.keys():
            print('Unknown tool name: ', tool_name) 
            return
        
        print('tool_arguments are\n', tool_arguments)
        print('\n')
        query: str = tool_arguments['query']
        tool_instance: Union[SearchQuran, SearchHadith] = self.tool_name_to_instance[tool_name]
        results = tool_instance.run_as_list(query)
        # print(f'Results are {results}')
        
        if len(results) == 0:
            # corner case where the api returns no results
            results = ['No results found from Kaleemat API']
        else:
            # instruct the model to paraphrase the tool's output
            print('#num of returned results from Kaleemat API:', len(results))
            results = ["Integrate the following tool messages in your final response"] + results

        # Now we have to pass the results back in
        for result in results:   
            self.message_history.append({
                'tool_call_id': tool_id,
                'role': 'tool',
                'name': tool_name, 
                'content': result
            })
