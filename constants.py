MODEL = 'gpt-3.5-turbo'
RICH_MODEL = 'gpt-4'
MAX_LENGTH = 3500 # have to leave some space for answers or they get chopped off midway. 
RICH_MAX_LENGTH = 7500 

END = '-- END --'

CSS ="""
.contain { display: flex; flex-direction: column; }x
#component-0 { height: 100%; }
#chatbot { flex-grow: 1; }
"""

KALEMAT_BASE_URL='https://api.kalimat.dev/search'