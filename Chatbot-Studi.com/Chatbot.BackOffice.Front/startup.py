import sys
from chatbot import ChatbotFront

sys.tracebacklimit = 5

ChatbotFront.init_session()
ChatbotFront.run()