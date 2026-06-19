from litellm import acompletion, completion
from deepeval.models.base_model import DeepEvalBaseLLM
from pydantic import BaseModel
import instructor


class DeepEvalBaseLLM(DeepEvalBaseLLM):

    def __init__(
        self,
        model: str
    ):
        self.model = model
        self.client = instructor.from_litellm(completion)

    def load_model(self):
        return self.model

    def generate(self, prompt: str, schema: BaseModel) -> BaseModel:
        messages = [{"content": prompt, "role": "user"}]
        try:
            response = self.client.chat.completions.create(
                model=self.model, messages=messages, response_model=schema
            )
        except Exception as e:
            print(e)
            response = schema.model_construct()

        return response

    async def a_generate(self, prompt: str, schema: BaseModel) -> BaseModel:
        client = instructor.from_litellm(acompletion)

        messages = [{"content": prompt, "role": "user"}]
        try:
            response = await client.chat.completions.create(
                model=self.model, messages=messages, response_model=schema
            )

        except Exception as e:
            print(e)
            response = schema.model_construct()

        return response

    def get_model_name(self):
        return "LiteLLM Model (" + str(self.model) + ")"
