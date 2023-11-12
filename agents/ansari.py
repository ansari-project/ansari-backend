import time
from pydantic import BaseModel
from util.prompt_mgr import PromptMgr
from tools.search_quran import SearchQuran
from tools.search_hadith import SearchHadith
import json
import openai


MODEL = 'gpt-4' 
class Ansari: 
    def __init__(self):
        sq = SearchQuran()
        sh = SearchHadith()
        self.tools = { sq.get_fn_name(): sq, sh.get_fn_name(): sh}
        self.model = MODEL
        self.pm = PromptMgr()
        sys_msg = self.pm.bind('system_msg_fn')
        self.functions = [x.get_function_description() for x in self.tools.values()]
    
        self.message_history = [{
            'role': 'system',
            'content': sys_msg.render()
        }]
        
    def greet(self):
        self.greeting = self.pm.bind('greeting')
        return self.greeting.render()
    
    def process_input(self, user_input):
        self.message_history.append({
            'role': 'user',
            'content': user_input
        })
        return self.process_message_history()
    
    def process_message_history(self):
        # Keep processing the user input until we get something from the assistant
        while self.message_history[-1]['role'] != 'assistant':
            #print(f'Processing one round {self.message_history}')

            # This is pretty complicated so leaving a comment. 
            # We want to yield from so that we can send the sequence through the input
            yield from self.process_one_round()
        
    def process_one_round(self):
        response = None
        while not response:
            try: 
                response = openai.ChatCompletion.create(
                model = self.model,
                messages = self.message_history,
                stream = True,
                functions = self.functions, 
                temperature = 0.0, 
                )
            except Exception as e:
                print('Exception occurred: ', e)
                print('Retrying in 5 seconds...')
                time.sleep(5)
            
    
        words = ''
        function_name = ''
        function_arguments = ''
        response_mode = '' # words or fn
        for tok in response: 
            #print(f'Token received: {tok.choices[0].delta}')
            delta = tok.choices[0].delta
            if not response_mode: 
                # This code should only trigger the first 
                # time through the loop.
                if 'function_call' in delta:
                    # We are in function mode
                    response_mode = 'fn'
                    function_name = delta['function_call']['name']
                else: 
                    response_mode = 'words'
                print('Response mode: ' + response_mode)

            # We process things differently depending on whether it is a function or a 
            # text
            if response_mode == 'words':
                if not delta: # End token
                    self.message_history.append({
                            'role': 'assistant',
                            'content': words
                        })

                    break
                elif 'content' in delta:
                    if delta['content']: 
                        words += delta['content']
                        yield delta['content'] 
                else: 
                    continue
            elif response_mode == 'fn':
                if not delta: # End token
                    function_call = function_name + '(' + function_arguments + ')'
                    print(f'Function call is {function_call}')
                    # The function call below appends the function call to the message history
                    yield self.process_fn_call(input, function_name, function_arguments)
                    # 
                    break
                elif 'function_call' in delta:
                    #print(f"Function call --{delta['function_call']['arguments']}")
                    function_arguments += delta['function_call']['arguments']
                    #print(f'Function arguments are {function_arguments}')
                    yield '' # delta['function_call']['arguments'] # we shouldn't yield anything if it's a fn
                else: 
                    continue
            else:
                raise Exception("Invalid response mode: " + response_mode)


    
    def process_fn_call(self, orig_question, function_name, function_arguments):
        if function_name in self.tools.keys():
            args = json.loads(function_arguments)
            query = args['query']
            results = self.tools[function_name].run_as_list(query)
            # print(f'Results are {results}')
            # Now we have to pass the results back in
            if len(results) > 0: 
                for result in results:   
                    self.message_history.append({
                        'role': 'function',
                        'name': function_name, 
                        'content': result
                    })
            else: 
                self.message_history.append({
                    'role': 'function',
                    'name': function_name, 
                    'content': 'No results found'
                })
        else:
            print('Unknown function name: ', function_name) 
