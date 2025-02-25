from form_service import FormService
from llm_service import LlmService
import asyncio

async def main_async():
    form = FormService.create_form_from_yaml_file("config/form_ex1.yaml")
    print(form)
    llm_service = LlmService()
    filled_form = await llm_service.ask_questions_until_form_is_fulfilled_async(form)
    print("Fulfilled form:")
    print(filled_form)

if __name__ == "__main__":
    print("Server started!")
    asyncio.run(main_async())

