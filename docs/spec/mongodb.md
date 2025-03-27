# MongoDB migration plan

## Purpose

Ansari was first built when the representation of messages between LLM providers and Ansari were simply text. 

Since then, the representation has become considerably richer. There are: 

- Tool use requests
- Tool results
- Documents
- References
- Thinking
- Citations

And more. The content of a message has changed from being a simple string to a list of polymorphic types. 

Thus we need to consider whether to augment our existing SQL db with supporting a set of polymorphic blocks and then
having a three level hierarchy (threads --> messages --> blocks), or switch to a document database. 

Also, this affects the frontend-backend protocol. The frontend was initially designed for the simple representation. 

But now as we try to render more advanced things, it has become a requirement to migrate to this. 

We've also committed to Claude as the backend for Ansari. 

We've chosen to migrate threads (only threads) to MongoDB. This is the plan for how to do that. 

## What needs to change

Threads, Messages and Blocks will be stored in MongoDB. 

Here is the current definition of a thread and messages (from sql/00_create_schema.sql): 

```sql
-- Threads table - integrated for both web and WhatsApp users
CREATE TABLE threads (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100),
    user_id UUID NOT NULL,
    initial_source source_type NOT NULL DEFAULT 'web',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Messages table - integrated for both web and WhatsApp users
CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    thread_id UUID NOT NULL,
    role TEXT NOT NULL, 
    tool_name TEXT,
    tool_details JSONB DEFAULT '{}'::jsonb,
    ref_list JSONB,
    content TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source source_type NOT NULL DEFAULT 'web',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE
);
```
As you can see it's pretty messy. 

Instead, we will be adopting Anthropic's representation of a message as outlined at: 

https://docs.anthropic.com/en/api/messages

Not only will we be using this for our storage representation, but we will be storing it
as our wire format and largely passing it unmodified through to the frontend. 

## How we'll do this

We will set up a MongoDB serverless instance using mongo cloud. 

We will add a new set of endpoints at /api/v3 for

- GET /threads # Get All Threads
- POST /threads # Create A Thread
- POST /threads/{thread_id} # Add a message to a thread
- GET /threads/{thread_id} # Get a thread
- DELETE /threads/{thread_id} # Delete a thread
- POST /share/{thread_id} # Snapshot a thread for sharing 
- GET /share/{thread_id} # See a shared thread
- POST /threads/{thread_id}/name # Set the name of a thread. 

We need to work out how to structure the FastAPI calls to support this. 

## Historical threads

The above methods will still hit the existing database for existing threads. 

But they will return values in the simpler format we used to use. Newly created threads
will be stored only in MongoDB. The above calls will have to do some fusion. 

## Ansari Classes that need to change

- main_api.py -- this is one of the messier files in the code base. We should take this as an opportunity to clean this up. How Ansari objects are created will also need to be modified to use the new derived classes below. 
- ansari_db.py -- Also messy. We may create a derived class from AnsariDB specifically for supporting the new use cases. We will create a new
- ansari_claude.py -- This changes the way many things work in Ansari Claude. We will create a derived class called AnsariClaudeHybrid. 
- Misc tests. 

## Long term migration

Eventually we will move all our efforts to the new service, and we will deprecate /api/v2. 




