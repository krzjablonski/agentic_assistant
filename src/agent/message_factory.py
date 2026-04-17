from agent.i_agent import (
    Message,
    TextContent,
    ImageContent,
    ToolUseContent,
    ToolResultContent,
)


def _parse_content(content) -> str | list:
    if isinstance(content, str):
        return content
    blocks = []
    for block in content:
        if not isinstance(block, dict):
            blocks.append(block)  # already typed
            continue
        t = block.get("type")
        if t == "text":
            blocks.append(TextContent(text=block["text"]))
        elif t == "image":
            source = block["source"]
            blocks.append(ImageContent(data=source["data"], media_type=source["media_type"]))
        elif t == "tool_result":
            blocks.append(ToolResultContent(
                tool_use_id=block["tool_use_id"],
                content=block["content"],
                is_error=block.get("is_error", False),
            ))
        elif t == "tool_use":
            blocks.append(ToolUseContent(
                id=block["id"], name=block["name"], input=block["input"]
            ))
    return blocks


def message_from_dict(msg: dict) -> Message:
    """Convert a raw dict (e.g. from Streamlit session state) to a typed Message."""
    return Message(
        role=msg["role"],
        content=_parse_content(msg["content"]),
    )
