from enum import Enum


class ProjectStatus(str, Enum):
    DRAFTING = "drafting"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    DEVELOPING = "developing"
    DEPLOYED = "deployed"
    ACCEPTANCE = "acceptance"
    COMPLETED = "completed"
    REJECTED = "rejected"


class SessionState(str, Enum):
    IDLE = "idle"
    CHATTING = "chatting"
    CONFIRMING = "confirming"
    SCORING = "scoring"


class VWorkMsgType(int, Enum):
    TEXT = 2
    IMAGE = 14
    GIF = 29
    FILE = 15
    VIDEO = 23
    VOICE = 16
    CARD_LINK = 13
    MINI_PROGRAM = 78
    NAME_CARD = 41
    LOCATION = 6
    VIDEO_CHANNEL = 141
    MERGED = 4


class VWorkSendType(int, Enum):
    SEND_TEXT = 3000
    SEND_IMAGE = 3001
    SEND_GIF = 3002
    SEND_FILE = 3003
    SEND_VIDEO = 3004
    SEND_NAME_CARD = 3005
    SEND_MINI_PROGRAM = 3006
    SEND_VIDEO_CHANNEL = 3007
    SEND_CARD_LINK = 3008
    SEND_AT_GROUP = 3009
    SEND_LOCATION = 3010
    SEND_VOICE = 3011
