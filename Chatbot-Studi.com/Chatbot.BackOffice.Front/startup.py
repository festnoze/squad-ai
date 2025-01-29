import sys
from chatbot import ChatbotFront

sys.tracebacklimit = 3

ChatbotFront.init_session()
ChatbotFront.run()