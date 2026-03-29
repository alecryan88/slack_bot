import logging
from typing import List, Optional

from slack_sdk.web.slack_response import SlackResponse

logger = logging.getLogger(__name__)


def parse_conversation(conversation: SlackResponse) -> Optional[List[dict]]:
    parsed = []
    try:
        for message in conversation:
            user = message["user"]
            text = message["text"]
            parsed.append({"user": user, "text": text})
        return parsed
    except Exception as e:
        logger.error(e)
        return None
