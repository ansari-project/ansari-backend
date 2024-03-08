# Ansari

_Try Ansari now at [ansari.chat](https://ansari.chat)!_  

Ansari is an **experimental open source project** that explores the application of large language models in helping Muslims improve their practice of Islam and non-Muslims develop an accurate understanding of the teachings of Islam. 

It is not always correct and can get things wrong.  The list below includes some of the issues we’ve seen in working with Ansari. 

It uses carefully crafted prompts and several sources accessed through retrieval augmented generation. 

# How can you help? 


* Try Ansari out and let us know your experiences – mail us at feedback@ansari.chat. 
* Help us implement the feature roadmap below. 

# What can Ansari do? 

A complete list of what Ansari can do can be found [here](https://ansari.chat/docs/capabilities/).

# What is logged with Ansari?

* Only the conversations are logged. Nothing incidental about your identity is currently retained: no ip address, no  accounts etc. If you share personal details with Ansari as part of a conversation e.g. “my name is Mohammed Ali” that will be logged. 
* If you shared something that shouldn’t have been shared, drop us an e-mail at feedback@ansari.chat and we can delete any logs. 

# Getting the Ansari Backend running on your local machine 

Ansari will quite comfortably run on your local machine -- almost all heavy lifting is done using other services. The only complexities are it needs a lot of environment variables to be set and you need to run postgres. 

You can also run it on Heroku and you can use the Procfile and runtime.txt filed to deploy it directly on Heroku. 

## Set up postgres on your machine 

Follow the instructions [here](https://devcenter.heroku.com/articles/local-setup-heroku-postgres) to install postgres.

## Make sure you have Python 3 installed 

Do a `% python -V` to checck that you have python 3 installed. If you get an error or the version starts with a 2, follow the instructions [here](https://realpython.com/installing-python/). 

## Download the repository 

```bash
% git clone git@github.com:waleedkadous/ansari-backend.git
% cd ansari-backend
```

## Create a python virtual environment and activate it. 

```bash
% python -m venv .venv
% source .venv/bin/activate
```

## Install dependencies

```bash
% pip install -r requirements.txt
```

## Set the appropriate environment variables

You can have a look at .env.example, and save it as .env. 

### Required environment variables

You need at a minimum:
- `OPENAI_API_KEY` (for the language processing) 
- `KALEMAT_API_KEY` (for Qur'an and Hadith search). 

### Optional environment variables

There are two optional environment variables. 

- `LANGFUSE_SECRET_KEY` and `LANGFUSE_PUBLIC_KEY`: Langfuse is a system for logging LLM interactions. It needs two keys: the secret key and the public key. If the secret key is not defined data will not be logged to langfuse. 
- `SENDGRID_API_KEY`: Sendgrid is the system we use for sending password reset emails. If it's not set it will print the e-mails that were sent

## Time to run! 

### Running as a backend service 

We use `uvicorn` to run the service. 

```bash
% # Make sure to load environment variables: 
% source .env
% uvicorn main_api:app --reload # Reload automatically reloads python files as you edit. 
```

This starts a service on port 8000. You can check it's up by checking at [http://localhost:8000/docs](http://localhost:8000/docs) which gives you a nice interface to the API. 

### Running on the command line

If you just want to run Ansari on the command line such that it takes input from stdin and outputs on stdout (e.g. for debugging or to feed it text) you can just do: 

```bash
% python main_stdio.py
```

# The Roadmap

This roadmap is preliminary, but it gives you an idea of where Ansari is heading. Please contact us at `feedback@ansari.chat `if you’d like to help with these.  



* ~~Add feedback buttons to the UI (thumbs up, thumbs down, explanation)~~
* ~~Add “share” button to the UI that captures a conversation and gives you a URL for it to share with friends. ~~
* ~~Add “share Ansari” web site.~~ 
* ~~Improve logging of chats – move away from PromptLayer.~~
* ~~Add Hadith Search. ~~
* Improve source citation. 
* Add prayer times. 
* ~~Add login support~~
* Add personalization – remembers who you are, what scholars you turn to etc.
* ~~Separate frontend from backend in preparation for mobile app.~~
* ~~Replace Gradio interface with Flutter. ~~
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
* Iman Sadreddin: Identifying output issues. 
* Wael Hamza: Characterizing output. 

