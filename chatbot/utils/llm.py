from litellm import completion
from typing import List, Optional, Union
from chatbot.models.enums import LLMProvider
import os


class LLM:
    def __init__(
        self,
        model: str,
        provider: str = "",
        temperature: Optional[float] = None,
        llm_env_conf: Optional[dict] = None,
        top_p: Optional[float] = None,
        function_call: Optional[str] = None,
        tool_choice: Optional[Union[str, dict]] = None,
        aws_bedrock_runtime_endpoint: Optional[str] = "https://bedrock-runtime.us-west-2.amazonaws.com",
        max_tokens: Optional[int] = None
    ):
        if not isinstance(model, str):
            raise Exception("model name should be of type string.")

        if provider != LLMProvider.OPENAI and provider != "":
            self.model = provider + "/" + model
        else:
            self.model = model
        self.llm_env_conf = llm_env_conf
        self.temperature = temperature
        self.top_p = top_p
        self.function_call = function_call
        self.tool_choice = tool_choice
        self.aws_bedrock_runtime_endpoint = aws_bedrock_runtime_endpoint
        self.max_tokens = max_tokens

        # set the envs here
        self.aws_region_name = "us-west-2"
        self.aws_access_key_val = os.environ["AWS_ACCESS_KEY_ID"]
        self.aws_secret_access_key_val = os.environ["AWS_SECRET_ACCESS_KEY"]
        self.api_key = os.environ["OPENAI_API_KEY"]

        if llm_env_conf is None:
            return

        if llm_env_conf.get("AWS_REGION") is not None:
            self.aws_region_name = llm_env_conf["AWS_REGION"]

        if llm_env_conf.get("AWS_ACCESS_KEY_ID") is not None:
            self.aws_access_key_val = llm_env_conf["AWS_ACCESS_KEY_ID"]

        if llm_env_conf.get("AWS_SECRET_ACCESS_KEY") is not None:
            self.aws_secret_access_key_val = llm_env_conf["AWS_SECRET_ACCESS_KEY"]

        if llm_env_conf.get("OPENAI_API_KEY") is not None:
            self.api_key = llm_env_conf["OPENAI_API_KEY"]

    def prompt(
        self,
        messages: List,
        tools: Optional[List[dict]] = None,
    ):
        return completion(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            top_p=self.top_p,
            function_call=self.function_call,
            tools=tools,
            messages=messages,
            aws_bedrock_runtime_endpoint=self.aws_bedrock_runtime_endpoint,
            aws_region_name=self.aws_region_name,
            aws_access_key_id=self.aws_access_key_val,
            aws_secret_access_key=self.aws_secret_access_key_val,
            api_key=self.api_key
        )

    def load_env_to_dict(value: Optional[str]) -> dict:
        if value is None:
            return {}
        env_dict = {}
        env_lines = value.split("\n")
        for line in env_lines:
            line = line.strip()
            # Ignore empty lines and comments
            if line and not line.startswith("#"):
                key, value = line.split("=", 1)
                env_dict[key.strip()] = value.strip().strip('"').strip("'")
        return env_dict
