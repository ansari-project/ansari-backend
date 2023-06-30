# Ansari

_Try Ansari now at [ansari.chat](https://ansari.chat)!_  

Ansari is an **experimental open source project** that explores the application of large language models in helping Muslims improve their practice of Islam and non-Muslims develop an accurate understanding of the teachings of Islam. 

It is not always correct and can get things wrong.  The list below includes some of the issues we’ve seen in working with Ansari. 


# How can you help? 



* Try Ansari out and let us know your experiences – mail us at feedback@ansari.chat. 
* Help us implement the feature roadmap below. 


# What is Ansari good at? 



* It is **very good** at languages and you can freely switch languages between Arabic, English and many other languages. 
* It is **very good** at writing khutbahs (some people have ranked it better than many human khateebs). 
* It is **very good **in its knowledge of Islamic books and scholars (e.g. ask it for a summary of _Madaarij al Saalikeen_, or ask it about _Fath Al Bari_).  
* It is **good** at finding dua to read in particular situations. 
* It is **good** for consoling yourself in times of hardship (though it can be a bit repetitive). 
* It is **good** at identifying a topic as controversial amongst scholars (e.g. music) and will generally give an overview of all opinions. 
* It is **OK** on the topic of Qur’an. It uses “retrieval assisted generation” to enhance the prompt to increase the chances of using the Qur’an. 


# What is Ansari not good at?



* It is **not good** at Islamic dates, prayer times, etc. This could be fixed, we just haven’t built it yet. 
* While Ansari is OK at quoting hadith, sometimes the hadith it quotes do not prove the logical point being asserted (e.g. it will quote the hadith about how to do wudu and use it to say that it encourages washing the knees even though knees are not mentioned in the hadith). In some cases it will not quote Hadith correctly. **Please verify references to hadith for now. We are working on fixing this. **
* Sometimes has strange ideas (e.g. washing knees is part of wudu). 
* It is **not good** at complex calculations (e.g. edge cases of inheritance or zakat) or counting (e.g. how many ayahs of the Qur’an mention X). 


# What is logged with Ansari?



* Only the conversations are logged. Nothing incidental about your identity is currently retained: no ip address, no  accounts etc. If you share personal details with Ansari as part of a conversation e.g. “my name is Mohammed Ali” that will be logged. 
* Logs are typically only retained for 7 days. 
* If you shared something that shouldn’t have been shared, drop us an e-mail at feedback@ansari.chat and we can delete any logs. 


# The Roadmap

This roadmap is preliminary, but it gives you an idea of where Ansari is heading. Please contact us at `feedback@ansari.chat `if you’d like to help with these.  



* Add feedback buttons to the UI (thumbs up, thumbs down, explanation)
* Add “share” button to the UI that captures a conversation and gives you a URL for it to share with friends. 
* Add “share Ansari” web site. 
* Improve logging of chats – move away from PromptLayer. 
* Add Hadith Search. 
* Improve source citation. 
* Add prayer times. 
* Add login support
* Add personalization – remembers who you are, what scholars you turn to etc.
* Separate frontend from backend in preparation for mobile app. 
* Replace Gradio interface with Flutter. 
* Ship Android and iOS versions of Ansari. 
* Add notifications (e.g. around prayer times). 
* Add more sources including: 
    * Videos by prominent scholars (transcribed into English)
    * Islamic question and answer web sites. 
* Turn into a platform so different Islamic organizations can customize Ansari to their needs. 


# Acknowledgements



* Amin Ahmad: general advice on LLMs, integration with vector databases. 
* Hossam Hassan: vector database backend for Qur’an search. 
* Saifeldeen Hadid: testing and identifying issues. 