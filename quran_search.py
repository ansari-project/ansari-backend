from kalemat_api import KalematAPI
from langchain.llms import OpenAI
from constants import MODEL

def lookup_quran(query):
    ka = KalematAPI()
    results = ka.search(query)
    #print(f'Results are {results}')
    rstring = '\n'.join([pp_ayah_ka(r) for r in results])
    return rstring
    
def pp_ayah_ka(ayah):
    ayah_num = ayah['id']
    ayah_ar = ayah['text']
    ayah_en = ayah['en_text']
    result = f'Ayah: {ayah_num}\nArabic Text: {ayah_ar}\nEnglish Text: {ayah_en}\n'
    return result

def determine_quranic(question):
        oai = OpenAI(temperature=0, model_name=MODEL)
        prompt = 'Determine if the following question is about the Qur\'an. ' \
                        'Examples: \n\n' \
                        'Question: Does the Qur\'an mention rubies?\nAnswer: Yes\n\n'  \
                        "Question: What does the Qur\'an say about the day of Judgement?\nAnswer: Yes\n\n" \
                        'Question: What does Islam say about birthdays?\nAnswer: No\n\n' \
                        'Question: I am tired.\nAnswer: No\n\n' \
                        'Question: Is washing the knees obligatory?\n Answer: No\n\n' \
                        'Question: Can I continue behind the imam in sajdah?\n Answer: No\n\n' \
                        'Question: ' + question + '\n' \
                        'Answer: '
        #print(f'Prompt is: {prompt}')
        quranic = oai.predict(prompt)
        # print(f'Result is: {quranic}')
        return quranic.startswith('Yes')
    
def quranic_results(user_message):
    oai = OpenAI(temperature=0, model_name=MODEL)
    prompt = f"""Extract the best query to use for a keyword search about the Qur\'an from the following question.

Do not include the word Qur'an.
Examples: 

Question: Does the Qur'an mention rubies?
Answer: rubies

Question: What does the Qur'an say about adultery?
Answer: Adultery

Question: {user_message} 
Answer: """ 
        
    topic = oai.predict(prompt)
    print(f'gpt-3.5-turbo recommended topic is {topic}')
    quran_results = lookup_quran(topic)
    quran_message = """Here is some context from the Qur'an.

""" + quran_results + """

Use this context to answer the next question from the user.
Do not use external sources unless you are highly confident. 
Include the Arabic text and the English translation.

Also here are some facts to consider: 
- Washing knees is definitely not part of wudu and there 
is no evidence whatsoever in the Qur'an or Sunnah that says
it is required, recommended or even optional. It would be considered 
a bid'a -- an innovation -- to suggest otherwise. 

Examples: 

Question: Does the Qur'an mention corals? 

Answer: Yes, the Qur'an mentions corals in ayah 55:22 in ayah 55:58.

Ayah: 55:22
Arabic: مِنْهُمَا يَخْرُجُ اللُّؤْلُؤُ وَالْمَرْجَانُ
English: From both of them emerge pearl and coral.

Ayah 55:58
Arabic: كَأَنَّهُنَّ ٱلْيَاقُوتُ وَٱلْمَرْجَان  
English: As if they were rubies and coral.

Question: Where in the Qur'an are elephants discussed? 

Answer: The Qur'an discusses elephants in: 

Ayah: 105:1
Arabic: أَلَمْ تَرَ كَيْفَ فَعَلَ رَبُّكَ بِأَصْحَابِ الْفِيلِ
English: Have you not seen how your Lord dealt with the companions of the elephant?

Question: """ + user_message
        
    return quran_message