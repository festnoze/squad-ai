import sys
from chatbot import ChatbotFront

sys.tracebacklimit = 3

ChatbotFront.initialize()
ChatbotFront.run()