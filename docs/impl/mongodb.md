# MongoDB Implementation Plan

## Schema Design

### Document Structure Hierarchy

MongoDB's document structure will follow a nested hierarchy:
- **Threads** are the top-level documents
- **Messages** are stored as embedded arrays within threads 
- **Blocks** are stored as embedded arrays within messages

This nested structure leverages MongoDB's document model for efficient retrieval of entire conversation threads with a single query.

### Collections

1. **threads**
   - `_id`: ObjectId (MongoDB default)
   - `thread_id`: UUID (Compatibility with existing system)
   - `name`: String
   - `user_id`: UUID reference to SQL users table
   - `initial_source`: String (web, whatsapp, etc.)
   - `created_at`: DateTime
   - `updated_at`: DateTime
   - `metadata`: Object (For extensibility)
   - `messages`: Array of message documents (embedded)

2. **messages** (Embedded within threads)
   - `message_id`: String
   - `user_id`: UUID reference to SQL users table
   - `role`: String (user, assistant, system)
   - `created_at`: DateTime
   - `content`: Array of content blocks (embedded)

3. **blocks** (Embedded within messages)
   - `type`: String (text, tool_use, tool_result, citation, etc.)
   - `text`: String (for text blocks)
   - `tool_calls`: Array (for tool_use blocks)
   - `citations`: Array (for citation blocks)
   - Block-specific fields depending on type

4. **shared_threads**
   - `_id`: ObjectId
   - `share_id`: String (public identifier)
   - `thread_id`: UUID reference to threads collection
   - `created_at`: DateTime
   - `expires_at`: DateTime (optional)
   - `snapshot`: Object (complete thread snapshot)

### Indexes

1. **threads**
   - `thread_id`: Unique
   - `user_id`: For filtering user's threads
   - `updated_at`: For sorting threads by recency

2. **Embedded messages**
   - Since messages are embedded within threads, no separate indexes are needed
   - Sorting by `created_at` will be handled in application code

3. **shared_threads**
   - `share_id`: Unique
   - `thread_id`: For reference back to source thread
   - `expires_at`: For cleanup of expired shares

## API Implementation

### MongoDB Connection
- Use PyMongo or Motor (async MongoDB driver) for MongoDB interactions
- Create connection pool with appropriate settings
- Implement connection retry logic
- Store connection string in environment variables
- Consider using ODM like Beanie for data validation and schema enforcement

### Authentication & Security
- Use MongoDB Atlas authentication
- Implement IP allowlist for database access
- Create dedicated service users with appropriate permissions
- Encrypt connection strings and credentials

### New API Endpoints

Implement the following FastAPI routes:

```python
@router.get("/api/v3/threads")
async def get_threads(user_id: UUID) -> List[Thread]:
    # Fetch threads from MongoDB for user_id
    # Project only thread metadata without messages for better performance

@router.post("/api/v3/threads")
async def create_thread(thread_data: ThreadCreate) -> Thread:
    # Create new thread in MongoDB with empty messages array

@router.get("/api/v3/threads/{thread_id}")
async def get_thread(thread_id: UUID) -> Thread:
    # Fetch complete thread document including embedded messages and blocks
    # All data is retrieved in a single query due to embedded structure

@router.post("/api/v3/threads/{thread_id}")
async def add_message(thread_id: UUID, message: Message) -> Message:
    # Add message to thread's messages array using $push operator
    # Update thread.updated_at timestamp

@router.delete("/api/v3/threads/{thread_id}")
async def delete_thread(thread_id: UUID) -> None:
    # Delete thread document (messages are deleted automatically as they're embedded)

@router.post("/api/v3/threads/{thread_id}/name")
async def set_thread_name(thread_id: UUID, name_data: ThreadName) -> Thread:
    # Update thread name using $set operator

@router.post("/api/v3/share/{thread_id}")
async def share_thread(thread_id: UUID) -> SharedThread:
    # Create complete snapshot in shared_threads collection
    # Generate unique share_id for public access

@router.get("/api/v3/share/{share_id}")
async def get_shared_thread(share_id: str) -> SharedThread:
    # Retrieve thread snapshot from shared_threads without authentication
```

## Data Migration Strategy

### Historical Thread Handling
1. Create new MongoDB collections
2. Implement hybrid access strategy:
   - Check MongoDB first for thread/message
   - Fall back to SQL if not found in MongoDB
   - Return data in consistent format regardless of source

### Progressive Migration
1. New threads created in MongoDB only
2. Existing threads accessed via hybrid approach
3. Implement logging to track usage of legacy threads
4. Consider background migration of high-value threads

## Class Structure Changes

### New Classes
1. **MongoDBClient**
   - Handles all MongoDB operations
   - Implements connection pooling
   - Provides CRUD operations for threads/messages

2. **AnsariDBHybrid** (extends AnsariDB)
   - Inherits from existing AnsariDB
   - Adds MongoDB support
   - Implements source determination logic

3. **AnsariClaudeHybrid** (extends AnsariClaude)
   - Adapts message handling for new format
   - Properly processes and stores blocks
   - Manages transition between formats

### Refactoring main_api.py
1. Separate route definitions from business logic
2. Move thread/message handling to dedicated services
3. Implement proper dependency injection
4. Add middleware for cross-cutting concerns

## Error Handling

1. Define MongoDB-specific exceptions
2. Implement retry logic for transient failures
3. Create consistent error responses
4. Add detailed logging for database operations
5. Set up monitoring for database performance

## Testing Strategy

1. Unit Tests
   - Mock MongoDB client
   - Test individual components
   - Verify format conversions

2. Integration Tests
   - Use MongoDB test container
   - Test complete API flows
   - Verify hybrid access works correctly

3. Performance Tests
   - Measure response times
   - Test under load
   - Verify index effectiveness

## Performance Considerations

1. Implement appropriate MongoDB indexes on thread fields
2. Use projection to limit returned fields when listing threads
   - Exclude message content when only metadata is needed
3. Consider pagination or lazy loading for threads with many messages
   - Add optional pagination parameters to API endpoints
   - Implement cursor-based pagination for large result sets
4. Address document size limits
   - MongoDB has a 16MB document size limit
   - For very large threads, consider strategies like:
     - Message chunking (splitting into multiple documents)
     - Time-based partitioning of long conversations
5. Monitor query performance with MongoDB profiler
6. Implement application-level caching for frequently accessed threads
7. Consider read/write concerns based on consistency requirements

## Backup & Disaster Recovery

1. Configure MongoDB Atlas backups
2. Implement application-level backup procedures
3. Create disaster recovery runbook
4. Test recovery processes

## Implementation Phases

### Phase 1: Infrastructure Setup
- Set up MongoDB Atlas instance
- Configure security and network access
- Implement basic MongoDB client class
- Define schema models and validation rules
- Set up monitoring and alerts

### Phase 2: Core Functionality
- Implement core data models for threads/messages/blocks
- Create basic CRUD operations with appropriate MongoDB operations
- Develop hybrid access strategy for legacy threads
- Set up initial testing environment with MongoDB test containers
- Implement data validation and serialization

### Phase 3: API Integration
- Implement new API endpoints following the v3 specification
- Integrate with existing authentication system
- Create thread management features (CRUD operations)
- Implement sharing functionality
- Develop frontend adapters for the new API format

### Phase 4: Migration & Refinement
- Develop migration utilities for moving SQL threads to MongoDB
- Test with production data samples
- Refine error handling and implement retry logic
- Optimize performance with proper indexes and projections
- Add monitoring for MongoDB operations

### Phase 5: Testing & Documentation
- Comprehensive testing (unit, integration, performance)
- Handle edge cases and error conditions
- Documentation updates for API and internal architecture
- Developer training on MongoDB best practices
- Prepare for production deployment with rollback plans