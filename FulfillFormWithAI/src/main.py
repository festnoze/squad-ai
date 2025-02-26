from form_service import FormService
from llm_service import LlmService
import asyncio

async def main_async():
    form = FormService.create_form_from_yaml_file("config/form_ex1.yaml")
    #print_form_struct(form)

    llm_service = LlmService()
    filled_form = await llm_service.query_user_to_fill_form_async(form)
    filled_form.save_form_instance_as_json("filled_form.json")

    print("Fulfilled form:")
    print(filled_form)


def print_form_struct(form):
    print("\nDescription de la structure du formulaire :\n")
    print(form)
    print("---------------------------------------------------------------------\n")

if __name__ == "__main__":
    print("Server started!")
    asyncio.run(main_async())

