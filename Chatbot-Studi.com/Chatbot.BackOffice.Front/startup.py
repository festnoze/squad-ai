import sys
from chatbot_front import ChatbotFront

sys.tracebacklimit = 3

ChatbotFront.init_session()
ChatbotFront.run()