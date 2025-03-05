# Enhanced Thread Format Specification

## Current Format

The current implementation of `get_thread` returns messages with the following structure:

```json
{
  "thread_name": "Name of the thread",
  "messages": [
    {
      "role": "user" | "assistant",
      "content": string | [{"type": "text", "text": "..."}]
    },
    ...
  ]
}
```

When `filter_content=True` (default), the API filters out tool results, documents, and tool uses, keeping only text content.

## Proposed Enhanced Format

The enhanced format extends the message content structure to include additional types of content blocks, such as thinking statements and citations, while preserving the existing structure for backward compatibility.

```json
{
  "thread_name": "Name of the thread",
  "messages": [
    {
      "role": "user" | "assistant",
      "content": [
        {"type": "text", "text": "..."},
        {"type": "thinking", "content": "..."},
        {"type": "citation", "cited_text": "...", "document_title": "...", "translation": "..."},
        ...
      ]
    },
    ...
  ]
}
```

### Content Block Types

1. **Text Block** (existing):
   ```json
   {"type": "text", "text": "Main content provided by the assistant or user"}
   ```

2. **Thinking Block** (new):
   ```json
   {"type": "thinking", "content": "Assistant's reasoning process or thoughts"}
   ```

3. **Citation Block** (new - based on Anthropic's citation format used in ansari_claude.py):
   ```json
   {
     "type": "citation",
     "cited_text": "The original text being cited (typically in Arabic)",
     "document_title": "Title of the source document",
     "translation": "English translation of the cited text (if available)"
   }
   ```

   This citation format aligns with how citations are tracked in the `AnsariClaude` class, where each citation contains:
   - `cited_text`: The actual text being cited (often in Arabic)
   - `document_title`: Title of the source document
   - `translation`: An optional English translation of the text

4. **Tool Use Block** (existing - used internally but filtered out):
   ```json
   {
     "type": "tool_use",
     "id": "unique-tool-use-id",
     "name": "tool_name",
     "input": {"param1": "value1", "param2": "value2"}
   }
   ```

5. **Tool Result Block** (existing - used internally but filtered out):
   ```json
   {
     "type": "tool_result",
     "tool_use_id": "unique-tool-use-id",
     "content": "Result from the tool execution"
   }
   ```

6. **Document Block** (existing - used internally but filtered out):
   ```json
   {
     "type": "document",
     "source": {
       "type": "content",
       "content": [...]
     },
     "title": "Document Title",
     "citations": {"enabled": true}
   }
   ```

## API Parameters

The enhanced `get_thread` endpoint would include additional query parameters:

```
GET /api/v2/threads/{thread_id}?filter_content=true&include_thinking=true&include_citations=true
```

- `filter_content`: (Boolean, default: true) Controls whether to filter out tool-related content
- `include_thinking`: (Boolean, default: false) Whether to include thinking blocks
- `include_citations`: (Boolean, default: false) Whether to include citation blocks

## Implementation Requirements

To implement this enhanced format:

1. **Database Storage**: The existing database structure already supports storing complex message content through serialized JSON, so no schema changes are needed.

2. **Message Conversion**: Modify the `convert_message` and `convert_message_llm` methods in `ansari_db.py` to preserve thinking and citation blocks when converting messages for display.

3. **Filtering Logic**: Update the `filter_message_content` function in `main_api.py` to check the new parameters and include or exclude thinking and citation blocks accordingly.

4. **API Endpoint**: Modify the `get_thread` endpoint to accept and forward the new parameters to the filtering function.

5. **Citation Format**: Ensure citation blocks follow the same structure used in AnsariClaude, with `cited_text`, `document_title`, and optional `translation` fields.

## Backward Compatibility

For backward compatibility, the default behavior should remain unchanged:

1. When neither `include_thinking` nor `include_citations` is specified, the API should continue to return only text content.

2. The content filtering should continue to work as before, with the addition of the new optional content types.

3. Existing clients that expect only text blocks in the content will continue to work without modification.

## Frontend Considerations

Frontend applications consuming this API should be updated to:

1. Pass the new parameters when retrieving threads, if they want to display thinking or citations
2. Handle and display the new content block types appropriately
3. Format citations with proper styling and references